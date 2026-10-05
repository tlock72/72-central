"""
72 Central - ITF World Tennis Tour singles titles (runs inside the 'Update scores' workflow, once a day, no Claude).

For every roster player it reads their ITF singles results from the ITF's own site and saves each
main-draw final they won in titles.json, with the tournament and its week:
  - once per player, their whole career (ITF World Tennis Tour M/W15-M/W100, and before 2019 the
    men's Futures and the ITF Women's Circuit), then every day just the current year;
  - once a ranking week (from Tuesday), their career-high ATP/WTA ranking ("best"), shown on the
    player pages and used to leave ITF titles out of the totals of anyone who is or has been top 100.
The home page counts this year's ITF World Tennis Tour titles and the player pages show the career
ITF titles, so both always match the ITF's records: doubles never count, and two titles at the
same venue are two titles.
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
TAKE = 50
VERSION = 3  # bump to make every player be re-checked on the next run
ITF_TYPES = ("ITF World Tennis Tour", "Futures", "ITF Womens Circuit")  # the last two: before 2019
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


def tier_of(t):
    # "W15 Monastir" -> W15, "$25,000 Tunis" -> $25K, an old men's Futures event -> Futures
    name = t.get("tournamentName") or ""
    m = re.match(r"([MW]\d{2,3})\b", name)
    if m:
        return m[1]
    m = re.match(r"\$([\d,]+)", name)
    if m:
        return f"${int(m[1].replace(',', '')) // 1000}K"
    return "Futures" if t.get("tournamentType") == "Futures" else "ITF"


def titles_of(rid, pid, year=None):
    """ITF singles titles won: in `year`, or the whole career when year is None."""
    # the ITF files men under "MT" and women under "WT"; the activity also lists Grand Slam, ATP/WTA,
    # Challenger and team events, so only ITF tournaments count
    circuit = "MT" if ROSTER[rid][1] == "atp" else "WT"
    out, skip = [], 0
    while True:
        act = get("/PlayerApi/GetPlayerActivity", circuitCode=circuit, matchTypeCode="S", playerId=pid, skip=skip, take=TAKE)
        items = act.get("items") or []
        for t in items:
            end = end_of(t.get("dates"))
            if not end or (year and end.year != year) or t.get("tournamentType") not in ITF_TYPES:
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
                    out.append({"id": rid, "tournament": t.get("tournamentName") or "", "tier": tier_of(t),
                                "type": t.get("tournamentType"), "week": t.get("dates") or "", "end": end.isoformat(),
                                "link": "https://www.itftennis.com" + (t.get("tournamentLink") or "")})
        skip += len(items)
        ends = [e for e in (end_of(t.get("dates")) for t in items) if e]
        if not items or skip >= (act.get("totalItems") or 0) or (year and ends and min(ends).year < year):
            return out


def best_of(rid, pid):
    """Career-high ATP/WTA singles ranking from the ITF player overview (None if never ranked)."""
    ov = get("/PlayerApi/GetPlayerOverview", circuitCode="MT" if ROSTER[rid][1] == "atp" else "WT", matchTypeCode="S", playerId=pid)
    # only "ATP Singles Ranking" / "WTA Singles Ranking": the overview also lists the ITF's own
    # "World Tennis Singles Ranking" (and junior rankings), which are a different scale
    ranks = [r.get("rank") for r in ov.get("careerHighRankings") or []
             if re.match(r"(ATP|WTA) Singles", r.get("name") or "") and r.get("rank")]
    return min(ranks) if ranks else None


def main():
    try:
        data = json.load(open("titles.json"))
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    uk = NOW.astimezone(UK)
    today = uk.strftime("%Y-%m-%d")
    tried = data.get("tried")
    recent = tried and NOW - datetime.fromisoformat(tried.replace("Z", "+00:00")) < timedelta(hours=2)
    if data.get("v") != VERSION:
        # version 3 adds whole careers and career highs: keep this year's titles (they stay correct) and
        # load each player's career over the next runs
        data = {k: v for k, v in data.items() if k in ("ids", "notFound", "titles", "checked")}
        data.update(v=VERSION, full=[], best={})
    if data.get("bestV") != 2:  # career highs read before the ATP/WTA-only fix: read them all again
        data.update(best={}, bestV=2)
    full, best = data.setdefault("full", []), data.setdefault("best", {})
    daily = data.get("checked") != today or (data.get("pending") and not recent)
    need_full = [r for r in ROSTER if r not in full or r not in best]  # career or career high not loaded yet
    if data.get("todo"):
        order, mode = data["todo"], data.get("todoMode", "daily")  # finish the players the last run didn't reach
    elif daily and uk.hour >= 7:
        order, mode = list(ROSTER), "daily"
    elif need_full and not (data.get("pending") and recent):
        order, mode = need_full, "career"  # whole careers not loaded yet
    else:
        print("ITF titles already checked today"); return
    data["tried"] = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    juniors = (json.load(open("itf.json")).get("players") or {})
    ids, missing = data.setdefault("ids", {}), data.setdefault("notFound", {})
    titles = data.setdefault("titles", {})
    year = uk.year
    # career highs are re-read once per ranking week, from the Tuesday (the tours publish on Monday)
    tue = uk.date() - timedelta(days=(uk.weekday() - 1) % 7)
    week_ago = (tue - timedelta(days=1)).isoformat()
    pending, todo, blocked = [], [], False
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
            if (best.get(rid) or {}).get("checked", "") <= week_ago:
                best[rid] = {"rank": best_of(rid, pid), "checked": today}
            career = rid not in full
            got = titles_of(rid, pid, None if career else year)
            # replace this player's saved titles: every year after a career load, else just this year
            for y in list(titles) if career else [str(year)]:
                titles[y] = [t for t in titles.get(y, []) if t["id"] != rid]
            for t in got:
                titles.setdefault(t["end"][:4], []).append(t)
            if career:
                full.append(rid)
                print(f"{name}: career loaded, {len(got)} ITF singles title(s)")
            elif got:
                print(f"{name}: {len(got)} ITF singles title(s) in {year}")
        except Blocked as e:
            print(e); blocked = True; pending.append(rid)
        except Exception as e:  # network hiccup or a final that can't be read: keep the old data, retry later
            print("failed", name, e); pending.append(rid)

    # players no longer on the roster drop out; each year newest first
    for y in list(titles):
        titles[y] = sorted((t for t in titles[y] if t["id"] in ROSTER), key=lambda t: t["end"], reverse=True)
        if not titles[y]:
            del titles[y]
    data["full"] = [r for r in full if r in ROSTER]
    data["pending"], data["todo"], data["todoMode"] = pending, todo, mode
    if not todo and mode == "daily":
        data["checked"] = today
    data["source"] = "ITF singles results (itftennis.com)"
    with open("titles.json", "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"done: {len(titles.get(str(year), []))} titles in {year}, {len(data['full'])} careers loaded, "
          f"{len(pending)} pending, {len(todo)} for the next run")


if __name__ == "__main__":
    main()
