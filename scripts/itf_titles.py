"""
72 Central - ITF World Tennis Tour singles titles (runs inside the 'Update scores' workflow, once a day, no Claude).

For every roster player it reads their ITF World Tennis Tour (M/W15 to M/W100) singles results from the
ITF's own site and saves each main-draw final they won this year in titles.json, with the tournament and
its week. The home page counts these, so the figure always matches the ITF's records: doubles never
count, and two titles at the same venue are two titles.
One request every few seconds. If the ITF site answers with its bot check the script stops (it never
tries to get past it) and keeps the previous data. A final it can't read clearly is not guessed: the
player is listed under 'pending' and Tobey is alerted.
"""
import json, os, re, sys, time, unicodedata, urllib.parse, urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from update import ROSTER  # roster id -> (name, tour)

BASE = "https://www.itftennis.com/tennis/api"
UA = "72HubRankings/1.0 (+https://github.com/tlock72/72-central; once a day, one request every few seconds)"
PAUSE = 4
TAKE = 10
BUDGET = timedelta(minutes=7)  # players not reached in time are picked up by the next run
UK = ZoneInfo("Europe/London")
NOW = datetime.now(timezone.utc)


class Blocked(Exception):
    pass


class Unclear(Exception):
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


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).lower().replace("-", " ").split())


def find_id(names):
    for name in names.split("|"):
        res = get("/PlayerApi/GetPlayerSearch", searchString=name)
        want = set(norm(name).split())
        for p in res.get("players") or []:
            have = set(norm(f'{p.get("givenName")} {p.get("familyName")}').split())
            if want <= have or (len(have) >= 2 and have <= want):
                return p["playerId"]
    return None


def end_of(s):
    # "21 Sep to 27 Sep 2026" -> 2026-09-27
    m = re.search(r"to (\d+) (\w+) (\d{4})", s or "")
    return datetime.strptime(f"{m[1]} {m[2]} {m[3]}", "%d %b %Y").date() if m else None


def titles_of(rid, pid, year):
    out, skip = [], 0
    while True:
        act = get("/PlayerApi/GetPlayerActivity", circuitCode="WT", matchTypeCode="S", playerId=pid, skip=skip, take=TAKE)
        items = act.get("items") or []
        for t in items:
            end = end_of(t.get("dates"))
            if not end or end.year != year:
                continue
            for ev in t.get("events") or []:
                if (ev.get("matchType") or "").lower() != "singles" or "main" not in (ev.get("drawType") or "").lower():
                    continue
                for m in ev.get("matches") or []:
                    if ((m.get("roundGroup") or {}).get("Value") or "").lower() != "final":
                        continue
                    rc = (m.get("resultCode") or "").upper()
                    if rc in ("", "L"):
                        continue  # final not played yet, or lost
                    if rc not in ("W", "O"):  # W = won, O = won by walkover
                        raise Unclear(f"final at {t.get('tournamentName')} has result code {rc!r}")
                    out.append({"id": rid, "tournament": t.get("tournamentName") or "", "week": t.get("dates") or "",
                                "end": end.isoformat(), "link": "https://www.itftennis.com" + (t.get("tournamentLink") or "")})
        skip += len(items)
        ends = [e for e in (end_of(t.get("dates")) for t in items) if e]
        if len(items) < TAKE or skip >= (act.get("totalItems") or 0) or (ends and min(ends).year < year):
            return out


def main():
    try:
        data = json.load(open("titles.json"))
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    uk = NOW.astimezone(UK)
    today = uk.strftime("%Y-%m-%d")
    tried = data.get("tried")
    recent = tried and NOW - datetime.fromisoformat(tried.replace("Z", "+00:00")) < timedelta(hours=2)
    if data.get("todo"):
        pass  # finish the players the last run didn't reach
    elif data.get("checked") == today and (not data.get("pending") or recent):
        print("ITF titles already checked today"); return
    elif uk.hour < 7:
        return
    data["tried"] = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    juniors = (json.load(open("itf.json")).get("players") or {})
    ids, missing = data.setdefault("ids", {}), data.setdefault("notFound", {})
    year = uk.year
    order = data.get("todo") or list(ROSTER)
    found, pending, todo, blocked = {}, [], [], False
    for rid in order:
        if rid not in ROSTER:
            continue
        if blocked or datetime.now(timezone.utc) - NOW > BUDGET:
            (pending if blocked else todo).append(rid); continue
        name = ROSTER[rid][0]
        try:
            pid = (juniors.get(rid) or {}).get("itfId") or ids.get(rid)
            if not pid:
                if missing.get(rid, "") > (uk.date() - timedelta(days=30)).isoformat():
                    continue  # not on the ITF site last time, looked for again monthly
                pid = find_id(name)
                if not pid:
                    print("not found on ITF:", name); missing[rid] = today; continue
                missing.pop(rid, None)
            ids[rid] = pid
            found[rid] = titles_of(rid, pid, year)
            if found[rid]:
                print(f"{name}: {len(found[rid])} ITF singles title(s) in {year}")
        except Blocked as e:
            print(e); blocked = True; pending.append(rid)
        except Exception as e:  # network hiccup or a final that can't be read: keep the old data, retry later
            print("failed", name, e); pending.append(rid)

    # players that couldn't be re-checked keep the titles saved for them before
    titles = data.setdefault("titles", {})
    keep = [t for t in titles.get(str(year), []) if t["id"] not in found and t["id"] in ROSTER]
    titles[str(year)] = sorted(keep + [t for v in found.values() for t in v], key=lambda t: t["end"], reverse=True)
    data["pending"], data["todo"] = pending, todo
    if not todo:
        data["checked"] = today
    data["source"] = "ITF World Tennis Tour singles results (itftennis.com)"
    with open("titles.json", "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"done: {len(titles[str(year)])} titles in {year}, {len(pending)} pending, {len(todo)} for the next run")


if __name__ == "__main__":
    main()
