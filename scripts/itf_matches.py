"""
72 Central - ITF junior matches (runs inside the 'Update scores' workflow, no Claude).

Full check of every junior about twice a day. In between, a quick check every hour (07:00-23:00 UK)
re-reads only the juniors who have a match today (or an earlier one) still not shown as finished,
so results appear within about an hour. Juniors whose request fails keep their previous matches.

For each 72 junior with an ITF profile (itf.json) it reads their latest ITF junior singles
activity (draws and results) and, for any event running now, that event's order of play,
then writes itfm.json. The website shows these alongside the other matches:
  - opponent known, not yet played -> today's / upcoming match, with the order-of-play slot
    (venue local time) when the ITF has published it, otherwise no time
  - played -> result, dated by the order of play it appeared on
One request every few seconds. If the ITF site answers with its bot check the script stops
(it never tries to get past it) and keeps the previous data.
"""
import json, os, re, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BASE = "https://www.itftennis.com/tennis/api"
UA = "72HubRankings/1.0 (+https://github.com/tlock72/72-central; a few times a day, one request every few seconds)"
PAUSE = 5
UK = ZoneInfo("Europe/London")
NOW = datetime.now(timezone.utc)
T = NOW.astimezone(UK).date()
ROUNDS = {"1st round": "R1", "2nd round": "R2", "3rd round": "R3", "4th round": "R4",
          "quarter-final": "QF", "quarter-finals": "QF", "semi-final": "SF", "semi-finals": "SF", "final": "Final"}


class Blocked(Exception):
    pass


def get(path, **params):
    time.sleep(PAUSE)
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8", "replace")
    if not body.lstrip().startswith(("{", "[")):
        raise Blocked("ITF answered with its bot check, stopping")
    return json.loads(body)


def short(given, family):
    family = " ".join(w.capitalize() if w.isupper() else w for w in (family or "").split())
    given = (given or "").strip()
    return f"{given[0]}. {family}" if given else family


def dates_of(s):
    # "05 Oct to 11 Oct 2026" (also "28 Dec to 03 Jan 2027")
    m = re.match(r"(\d+) (\w+)(?: (\d{4}))? to (\d+) (\w+) (\d{4})", s or "")
    if not m:
        return None, None
    end = datetime.strptime(f"{m[4]} {m[5]} {m[6]}", "%d %b %Y").date()
    start = datetime.strptime(f"{m[1]} {m[2]} {m[3] or m[6]}", "%d %b %Y").date()
    if start > end:
        start = start.replace(year=start.year - 1)
    return start, end


def slot_text(court, sched, first_time):
    s = (sched or "").strip()
    low = s.lower()
    if low.startswith("starting at"):
        return f"{court} · starts {s[11:].strip()}"
    if low.startswith("not before"):
        return f"{court} · not before {s[10:].strip()}"
    if low.startswith("followed by"):
        return f"{court} · after earlier matches" + (f" (court starts {first_time})" if first_time else "")
    if "tba" in low:
        return "Court and time to be announced"
    return f"{court} · {s}" if s else court


def order_of_play(key, cache):
    """matchId -> {date, slot, court} from the event's order of play, for the days around today."""
    if key in cache:
        return cache[key]
    out = {}
    days = get("/TournamentApi/GetOrderOfPlayDays", tournamentKey=key) or []
    for d in days:
        day = (d.get("playDate") or "")[:10]
        if not day or not (T - timedelta(days=2) <= datetime.strptime(day, "%Y-%m-%d").date() <= T + timedelta(days=1)):
            continue
        for court in get("/TournamentApi/GetOrderOfPlay", orderOfPlayDayId=d["orderOfPlayDayId"]) or []:
            first = None
            for m in court.get("matches") or []:
                sc = m.get("schedule") or ""
                if sc.lower().startswith("starting at") and not first:
                    first = sc[11:].strip()
                out[m.get("matchId")] = {"date": day, "slot": slot_text(court.get("courtName") or "Court", sc, first),
                                         "court": court.get("courtName") or ""}
    cache[key] = out
    return out


def score_of(match, won):
    sets = []
    for s in match.get("scores") or []:
        a, b, tb = s.get("scoreOne"), s.get("scoreTwo"), s.get("losingScore")
        if a is None or b is None:
            continue
        w, l = (a, b) if won else (b, a)
        sets.append(f"{w}-{l}" + (f"({tb})" if tb is not None and abs(w - l) == 1 and max(w, l) >= 7 else ""))
    return ", ".join(sets)


def main():
    try:
        out = json.load(open("itfm.json"))
    except (FileNotFoundError, json.JSONDecodeError):
        out = {}
    def ago(k):
        v = out.get(k)
        return NOW - datetime.fromisoformat(v.replace("Z", "+00:00")) if v else timedelta(days=99)
    force = os.environ.get("SOURCE") == "manual"
    previous = {m["matchId"]: m for m in out.get("matches") or []}
    # juniors with a match today or earlier that isn't shown as finished yet
    waiting = {m.get("p1Id") or m.get("p2Id") for m in previous.values()
               if m["status"] != "finished" and m["date"] <= T.isoformat()}
    if not force and NOW.astimezone(UK).hour < 7:
        return
    if not force and ago("blocked") < timedelta(hours=3):
        print("ITF bot check was hit recently - next check later"); return
    if force or ago("tried") >= timedelta(hours=11):
        only = None   # full check
    elif waiting and ago("quick") >= timedelta(minutes=55):
        only = waiting
        out["quick"] = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
        print("quick check for", ", ".join(sorted(waiting)))
    else:
        print("ITF matches checked", out.get("tried"), "- next check later"); return
    if only is None:
        out["tried"] = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    itf = json.load(open("itf.json"))
    found, cache, blocked, done = {}, {}, False, set()

    for rid, rec in itf.get("players", {}).items():
        pid = rec.get("itfId")
        if not pid or rec.get("noItf") or (only is not None and rid not in only):
            continue
        try:
            act = get("/PlayerApi/GetPlayerActivity", circuitCode="JT", matchTypeCode="S", playerId=pid, skip=0, take=3)
        except Blocked as e:
            print(e); blocked = True; break
        except Exception as e:
            print("activity failed", rid, e); continue
        me = rid
        done.add(rid)
        for t in act.get("items") or []:
            start, end = dates_of(t.get("dates"))
            if not start or end < T - timedelta(days=2) or start > T + timedelta(days=2):
                continue
            key = (t.get("tournamentLink") or "").rstrip("/").split("/")[-1]
            name = re.sub(r"\s*\(.*\)\s*$", "", t.get("tournamentName") or "")
            try:
                oop = order_of_play(key, cache) if key else {}
            except Blocked as e:
                print(e); blocked = True; break
            except Exception as e:
                print("order of play failed", key, e); oop = {}
            for ev in t.get("events") or []:
                qual = "qual" in (ev.get("drawType") or "").lower()
                for m in ev.get("matches") or []:
                    opp = (m.get("opponents") or [None])[0]
                    if not opp or not opp.get("familyName"):
                        continue  # bye or opponent not decided yet
                    mid = m.get("matchId")
                    rnd = ROUNDS.get(((m.get("roundGroup") or {}).get("Value") or "").lower(), (m.get("roundGroup") or {}).get("Value") or "")
                    if qual:
                        rnd = "Q-" + rnd if rnd else "Qualifying"
                    oname = short(opp.get("givenName"), opp.get("familyName"))
                    o = oop.get(mid) or {}
                    rc = (m.get("resultCode") or "").upper()
                    status_code = (m.get("resultStatusCode") or "").upper()
                    base = {"matchId": mid, "source": "itf", "tournament": name, "category": f"ITF Juniors · {t.get('tourCode') or ''}".strip(" ·"),
                            "link": "https://www.itftennis.com" + (t.get("tournamentLink") or ""), "time": ""}
                    if rc in ("W", "L"):
                        prev = previous.get(mid) or {}
                        date = o.get("date") or (None if prev.get("tbc") else prev.get("date"))
                        if not date:
                            continue  # can't tell which day it was played, so leave it out rather than guess
                        won = rc == "W"
                        sc = score_of(m, won)
                        if "RET" in status_code or "DEF" in status_code:
                            sc += " ret."
                        if "W" in status_code and "O" in status_code:
                            rnd += " (walkover)"
                        # winner listed first, as with every other result on the site
                        sides = dict(p1="", p1Id=me, p2=oname, p2Id=None) if won else dict(p1=oname, p1Id=None, p2="", p2Id=me)
                        found[mid] = dict(base, date=date, round=rnd, status="finished", score=sc, winner=1, **sides)
                        court = o.get("court") or (previous.get(mid) or {}).get("court")
                        if court:
                            found[mid]["court"] = court   # shown on the result tile
                    elif not rc:
                        tbc = False
                        if o.get("date"):
                            date, slot = o["date"], o["slot"]
                        elif start <= T <= end:
                            # draw is out but no order of play yet: the site shows it under "Coming up" as "Day TBC"
                            # (today's date is kept so the hourly quick check keeps looking for its order of play)
                            date, slot, tbc = T.isoformat(), "", T < end
                        elif start > T:
                            date, slot, tbc = start.isoformat(), "", True
                        else:
                            continue
                        found[mid] = dict(base, date=date, round=rnd, status="scheduled", score="", winner=None,
                                          p1="", p1Id=me, p2=oname, p2Id=None, slot=slot)
                        if tbc:
                            found[mid]["tbc"] = True
                        if o.get("court"):
                            found[mid]["court"] = o["court"]
        if blocked:
            break

    if blocked or not done:
        # keep what we had; try again later
        if blocked:
            out["blocked"] = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
        with open("itfm.json", "w") as f:
            json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
        return

    keep_from = (T - timedelta(days=7)).isoformat()
    merged = dict(found)
    for mid, m in previous.items():
        if mid in merged or (m["status"] == "finished" and m["date"] < keep_from):
            continue
        if m["status"] == "finished" or (m.get("p1Id") or m.get("p2Id")) not in done:
            # recent results stay for the 48-hour list and the congratulations banner;
            # juniors not re-read this time (quick check, or their request failed) keep their matches
            merged[mid] = m
    out["matches"] = sorted(merged.values(), key=lambda m: (m["date"], m["tournament"]))
    if only is None:
        out["checked"] = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    with open("itfm.json", "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"done: {len(out['matches'])} ITF junior matches")


if __name__ == "__main__":
    main()
