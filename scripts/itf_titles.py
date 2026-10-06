"""
72 Central - ITF World Tennis Tour singles titles (runs inside the 'Update scores' workflow, once a day, no Claude).

For every roster player it reads their ITF singles results from the ITF's own site and saves each
main-draw final they won in titles.json, with the tournament and its week:
  - once per player, their whole career (ITF World Tennis Tour M/W15-M/W100, and before 2019 the
    men's Futures and the ITF Women's Circuit), then every day just the current year;
  - after each new official ranking week (and at least weekly), their career-high ATP/WTA ranking
    ("best"), shown on the player pages and used to leave ITF titles out of the totals of anyone who is
    or has been top 100. It is only shown if it fits the ranks seen in the official weekly lists
    (scouting.json, kept as "seen") and the career high typed into the profile in index.html; otherwise
    it is left blank ("issue") and Tobey is alerted.
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
    """Career-high ATP/WTA singles ranking from the ITF player overview, as (rank, problem).
    The overview can list more than one singles career high (e.g. the ITF's own old World Tennis Tour
    ranking next to the WTA one), so only the tour's own entry counts, never simply the lowest number.
    (None, "") = never ranked; (None, text) = can't tell which entry is the tour's."""
    tour = ROSTER[rid][1]
    ov = get("/PlayerApi/GetPlayerOverview", circuitCode="MT" if tour == "atp" else "WT", matchTypeCode="S", playerId=pid)
    rows = [r for r in ov.get("careerHighRankings") or [] if r.get("rank")]
    singles = [r for r in rows if "singles" in (r.get("name") or "").lower() and "junior" not in (r.get("name") or "").lower()]
    named = [r for r in singles if tour in (r.get("name") or "").lower()]
    pick = named or [r for r in singles if "itf" not in (r.get("name") or "").lower()]
    ranks = {r["rank"] for r in pick}
    if len(ranks) == 1:
        return ranks.pop(), ""
    if not singles:
        return None, ""
    return None, "the ITF profile lists " + ", ".join(f'{r.get("name")} {r["rank"]}' for r in rows)


def norm_key(name):
    return re.sub(r"[^a-z]", "", norm(name))


def seen_ranks(rid, scout):
    """Official ranks this player has held in the weekly lists in scouting.json (this week, 1 week, 3 and 12 months ago)."""
    name, tour = ROSTER[rid]
    rows = (scout.get(tour) or {}).get("players") or []
    k = norm_key(name.split("|")[0])
    hit = [r for r in rows if norm_key(r[1]) == k]
    if not hit:
        hit = [r for r in rows if norm_key(r[1]).startswith(k) or k.startswith(norm_key(r[1]))]  # "Leyre Romero Gormaz"
    if len(hit) != 1:
        return []
    return [x for x in [hit[0][0]] + list(hit[0][4:7]) if isinstance(x, int) and x > 0]


def typed_highs():
    """Career highs typed into the player profiles in index.html (high:123), checked by Tobey."""
    try:
        page = open("index.html", encoding="utf-8").read()
    except OSError:
        return {}
    return {m.group(1): int(m.group(2)) for m in re.finditer(r'\{ id:"(\w+)",[^\n]*?\bhigh:(\d+)', page)}


def check_best(rid, itf, why, typed, seen, label):
    """Decide which career high to show. Returns (rank or None, problem text or "")."""
    name = ROSTER[rid][0].split("|")[0]
    if why:
        return None, f"Career high for {name}: can't tell which ranking is the {label} one ({why})."
    if itf is None:
        if seen:
            return None, (f"Career high for {name}: the ITF profile shows no {label} career high, but they have been No. {seen} "
                          f"in the official {label} rankings. Their profile's 'high' in index.html is shown instead, if set.")
        return None, ""
    if seen and itf > seen:
        return None, (f"Career high for {name}: the ITF says {label} No. {itf}, but they were No. {seen} in the official "
                      f"{label} rankings, so the ITF figure is wrong. Not shown until it is fixed.")
    if typed and itf > typed:
        return None, (f"Career high for {name}: the ITF says {label} No. {itf}, but their profile says No. {typed}. "
                      f"Showing No. {typed}; check it and fix 'high' in index.html if needed.")
    if typed and itf < typed and itf != seen:
        return None, (f"Career high for {name}: the ITF says {label} No. {itf}, but their profile says No. {typed}. "
                      f"Showing No. {typed}; if No. {itf} is right, change 'high' in index.html to {itf}.")
    return itf, ""


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
    full, best = data.setdefault("full", []), data.setdefault("best", {})
    daily = data.get("checked") != today or (data.get("pending") and not recent)
    need_full = [r for r in ROSTER if r not in full]
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
    # career highs are re-read after each new official ranking week (scouting.json, which runs just before this),
    # and at least once a week, then checked against the ranks seen in the official lists and the typed profiles
    try:
        scout = json.load(open("scouting.json"))
    except (FileNotFoundError, json.JSONDecodeError):
        scout = {}
    typed = typed_highs()
    week_ago = (uk.date() - timedelta(days=7)).isoformat()
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
            old = best.get(rid) or {}
            tour = ROSTER[rid][1]
            week = (scout.get(tour) or {}).get("week")
            seen = min([x for x in seen_ranks(rid, scout) + [old.get("seen")] if x] or [None])
            if old.get("checked", "") <= week_ago or (week and old.get("week") != week):
                itf, why = best_of(rid, pid)
                rank, issue = check_best(rid, itf, why, typed.get(rid), seen, tour.upper())
                best[rid] = {k: v for k, v in {"rank": rank, "itf": itf, "seen": seen, "issue": issue,
                                               "week": week, "checked": today}.items() if v is not None and v != ""}
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
    data["best"] = {r: b for r, b in best.items() if r in ROSTER}
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
