"""
72 Central - official ITF order of play for our pros' ITF World Tennis Tour matches (runs inside the
'Update scores' workflow, no Claude).

The Live Tennis API's start time for an ITF match is only its own estimate (often just when play starts on the
day), so for any of our pros' ITF matches today or tomorrow this reads the event's own order of play from the ITF
and saves the slot ("Court 1 · not before 12:00", venue local time) to itfoop.json. The website shows that slot
instead of the feed's time. About once an hour, 07:00-23:00 UK, one request every few seconds.

Never guesses: the match must be on the event found by city + level (W100...) + men/women, and on the order of play
by both players' surnames. If no slot or more than one slot fits, nothing is saved and the site keeps the feed's time.
At the ITF bot check it stops (it never tries to get past it) and keeps the previous slots.
"""
import json, re, unicodedata
from datetime import datetime, timedelta
from itf_matches import get, Blocked, slot_text, NOW, T, UK


def fold(s):
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def last_word(name):
    w = fold(name).split()
    return w[-1] if w else ""


def roster():
    """rid -> (full name, "atp"/"wta") from ROSTER in update.py (read as text, so update.py isn't run)."""
    return {m[1]: (m[2], m[3]) for m in re.finditer(r'"(\w+)": \("([^"]+)", "(atp|wta)"', open("scripts/update.py").read())}


def event_key(m, tour, events):
    """The ITF tournament key for a match, from schedule.json: same city, same level (W100), men or women,
    running on the match's date. None unless exactly one event fits."""
    lvl = (re.search(r"\b([MW]\d+)\b", m.get("category") or "") or [None, None])[1]
    if not lvl:
        return None
    name = " " + fold(m["tournament"]) + " "
    hits = set()
    for e in events:
        if e.get("tour") != ("itfw" if tour == "wta" else "itfm") or e.get("cat") != lvl:
            continue
        city = fold(re.sub(r"\s*\(.*$", "", (e.get("place") or "").split(",")[0]))
        if len(city) < 3 or " " + city + " " not in name:
            continue
        if not (e["start"] <= m["date"] <= (e.get("end") or e["start"])):
            continue
        key = (e.get("link") or "").rstrip("/").split("/")[-1]
        if key:
            hits.add(key)
    return hits.pop() if len(hits) == 1 else None


def read_oop(key, days):
    """Every slot on the event's order of play for today and tomorrow."""
    slots = []
    for d in get("/TournamentApi/GetOrderOfPlayDays", tournamentKey=key) or []:
        day = (d.get("playDate") or "")[:10]
        if day not in days:
            continue
        for court in get("/TournamentApi/GetOrderOfPlay", orderOfPlayDayId=d["orderOfPlayDayId"]) or []:
            first = None
            for x in court.get("matches") or []:
                sc = x.get("schedule") or ""
                if sc.lower().startswith("starting at") and not first:
                    first = sc[11:].strip()
                slots.append({"date": day, "slot": slot_text(court.get("courtName") or "Court", sc, first),
                              "court": court.get("courtName") or "", "txt": " " + fold(json.dumps(x, ensure_ascii=False)) + " "})
    return slots


def main():
    try:
        out = json.load(open("itfoop.json"))
    except (FileNotFoundError, json.JSONDecodeError):
        out = {}
    def ago(v):
        return NOW - datetime.fromisoformat(v.replace("Z", "+00:00")) if v else timedelta(days=99)
    hour = NOW.astimezone(UK).hour
    if hour < 7:
        return
    try:
        blocked = json.load(open("itfm.json")).get("blocked")
    except (FileNotFoundError, json.JSONDecodeError):
        blocked = None
    if ago(blocked) < timedelta(hours=3) or ago(out.get("blocked")) < timedelta(hours=3):
        print("ITF bot check was hit recently - next order-of-play check later"); return

    days = {T.isoformat(), (T + timedelta(days=1)).isoformat()}
    ros = roster()
    data = json.load(open("data.json"))
    events = json.load(open("schedule.json")).get("events") or []
    want = {}   # tournament key -> [(apiId, our surname, opponent surname)]
    for m in data.get("matches") or []:
        if not isinstance(m.get("apiId"), int) or m.get("status") != "scheduled" or m.get("date") not in days:
            continue
        rid = m.get("p1Id") if m.get("p1Id") in ros else m.get("p2Id") if m.get("p2Id") in ros else None
        if not rid:
            continue
        key = event_key(m, ros[rid][1], events)
        if not key:
            if (m.get("category") or "").startswith("ITF"):
                print("no single ITF event found for", m["tournament"], m["date"])
            continue
        opp = m["p2"] if m.get("p1Id") == rid else m["p1"]
        want.setdefault(key, []).append((str(m["apiId"]), last_word(ros[rid][0]), last_word(opp)))

    old = out.get("matches") or {}
    keep = {k: v for k, v in old.items() if v.get("date") in days}
    if not want:
        if keep != old or "matches" not in out:
            out["matches"] = keep
            json.dump(out, open("itfoop.json", "w"), ensure_ascii=False, separators=(",", ":"))
        return
    if ago(out.get("checked")) < timedelta(minutes=55):
        print("ITF order of play checked", out.get("checked"), "- next check later"); return

    found = {}
    try:
        for key, ms in want.items():
            try:
                slots = read_oop(key, days)
            except Blocked:
                raise
            except Exception as e:
                # this event couldn't be read: its matches keep the slots they had
                print("order of play failed", key, e)
                found.update({aid: keep[aid] for aid, _, _ in ms if aid in keep})
                continue
            for aid, me, op in ms:
                hits = [s for s in slots if me and op and f" {me} " in s["txt"] and f" {op} " in s["txt"]]
                if len(hits) == 1:
                    found[aid] = {k: hits[0][k] for k in ("date", "slot", "court")}
                    found[aid]["at"] = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
                elif hits:
                    print("more than one order-of-play slot fits, left out:", key, me, "v", op)
                else:
                    print("not on the order of play yet:", key, me, "v", op)
    except Blocked as e:
        print(e)
        out["blocked"] = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
        out["matches"] = keep
        json.dump(out, open("itfoop.json", "w"), ensure_ascii=False, separators=(",", ":"))
        return
    out["checked"] = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    out["matches"] = found
    json.dump(out, open("itfoop.json", "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"done: ITF order of play for {len(found)} of {sum(len(v) for v in want.values())} matches")


if __name__ == "__main__":
    main()
