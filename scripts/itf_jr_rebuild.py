"""
72 Central - past ITF junior rankings, rebuilt from the ITF's own results (runs on GitHub Actions, no Claude needed).

Why: the ITF only publishes the current junior ranking (and year-end lists); nobody keeps the weekly lists before
June 2026. But a junior ranking is just arithmetic on results, so it can be worked out again for any past Monday:
  points = best 6 singles results + 25% of the best 6 doubles results, each counting for 52 weeks
  (ITF World Tennis Tour Juniors Regulations; points tables in POINTS, Junior Finals by final place in JM_PLACE).

How:
  1. calendar: every junior event since START (TournamentApi/GetCalendar), once per month (past months never change)
  2. draws: for each finished event, its main draws (GetEventFilters + GetDrawsheet, boys/girls, singles/doubles)
     -> how far each player went and whether they won a match. Saved in itfjr_rebuild/raw/<month>.json, read once.
  3. rankings: the full boys and girls lists for every Monday, from those results.
  4. check: every rebuilt list is compared with every official list we hold (year-end 2022-2025 with exact points,
     and our weekly lists from June 2026). Only if they agree (CHECK_MIN) is anything published (itfjr_rebuilt.json
     "ok"); itf_jr_list.py then uses the rebuilt weeks for the 3-month / 12-month moves and the page shows monthly
     progression from itfjr_prog.json. Otherwise nothing is used and report_gaps.py alerts the reason.

Polite: one request every PAUSE seconds, a time budget per run (BUDGET), stops at the ITF bot check (never gets past
it) and carries on next run. A full first pass is about 16,000 requests, i.e. roughly a day of hourly runs.
"""
import json, os, re, time, urllib.parse, urllib.request
from datetime import date, datetime, timedelta, timezone

ITF = "https://www.itftennis.com/tennis/api"
UA = "72HubRankings/1.0 (+https://github.com/tlock72/72-central; past junior results, one request every few seconds)"
PAUSE = 3.5
BUDGET = float(os.environ.get("BUDGET", 25 * 60))   # seconds of requests per run (hourly runs: ~16,000 requests in ~1.5 days)
START = date(2022, 11, 1)                           # results from here make the rankings from Nov 2023 on
DIR = "itfjr_rebuild"
STATE, OUT, PROG, HIST = f"{DIR}/state.json", "itfjr_rebuilt.json", "itfjr_prog.json", "itfjr_history.json"
NOW = datetime.now(timezone.utc)
TODAY = NOW.date()
T0 = time.time()

# Ranking points (ITF World Tennis Tour Juniors Regulations). Key = the round a player LOST in (or W = won it),
# counted only if the player won at least one main-draw match (a bye is not a win; a walkover or retirement is).
POINTS = {
    "S": {"JGS": {"W": 1000, "F": 700, "SF": 490, "QF": 300, "R16": 180, "R32": 90},
          "J500": {"W": 500, "F": 350, "SF": 250, "QF": 150, "R16": 90, "R32": 45},
          "J300": {"W": 300, "F": 210, "SF": 140, "QF": 100, "R16": 60, "R32": 30},
          "J200": {"W": 200, "F": 140, "SF": 100, "QF": 60, "R16": 36, "R32": 18},
          "J100": {"W": 100, "F": 60, "SF": 36, "QF": 20, "R16": 10, "R32": 5},
          "J60": {"W": 60, "F": 36, "SF": 18, "QF": 10, "R16": 5},
          "J30": {"W": 30, "F": 18, "SF": 9, "QF": 5, "R16": 2}},
    "D": {"JGS": {"W": 750, "F": 525, "SF": 367, "QF": 225, "R16": 135},
          "J500": {"W": 375, "F": 262, "SF": 187, "QF": 112, "R16": 67},
          "J300": {"W": 225, "F": 157, "SF": 105, "QF": 75, "R16": 45},
          "J200": {"W": 150, "F": 105, "SF": 75, "QF": 45, "R16": 27},
          "J100": {"W": 75, "F": 45, "SF": 27, "QF": 15, "R16": 7},
          "J60": {"W": 45, "F": 27, "SF": 14, "QF": 7},
          "J30": {"W": 25, "F": 13, "SF": 6, "QF": 3}},
}
# Junior Finals (category JM): points by final place, read from the ITF's own points breakdown of its players
# (learn_jm); these are the 2026 values seen so far, kept as a starting point.
JM_PLACE = {1: 940, 8: 260}
TIE = ["JGS", "J500", "J300", "J200", "J100", "J60", "J30", "JM"]  # tie-break: points from the biggest events first
CHECK_MIN = 0.98   # share of players (top 500 of every official list we hold) whose rebuilt rank must be exact


class Blocked(Exception):
    pass


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")


def left():
    return BUDGET - (time.time() - T0)


def get(path, **q):
    time.sleep(PAUSE)
    req = urllib.request.Request(f"{ITF}{path}?{urllib.parse.urlencode(q)}", headers={"User-Agent": UA, "Accept": "application/json"})
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read().decode("utf-8", "replace")
            break
        except Exception as e:
            if i == 2:
                raise
            time.sleep(10 * (i + 1))
    if not body.lstrip().startswith(("{", "[")):
        raise Blocked("ITF answered with its bot check")
    return json.loads(body)


def months():
    m = START.replace(day=1)
    while m <= TODAY:
        yield m.strftime("%Y-%m")
        m = (m + timedelta(days=32)).replace(day=1)


def iso(s):
    return (s or "")[:10]


# ---------------- 1) calendar ----------------
def calendar(state):
    cal = state.setdefault("cal", {})
    this = TODAY.strftime("%Y-%m")
    for mo in months():
        old = cal.get(mo)
        # a past month is read once (and once more after it ended); the current month every run
        if old and (old.get("final") or mo == this and old.get("at", "")[:10] == TODAY.isoformat()):
            continue
        if left() < 60:
            return
        y, m = map(int, mo.split("-"))
        first = date(y, m, 1)
        last = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        evs, skip = [], 0
        while True:
            j = get("/TournamentApi/GetCalendar", circuitCode="JT", searchString="", skip=skip, take=100, nationCodes="", zoneCodes="",
                    dateFrom=first.isoformat(), dateTo=last.isoformat(), indoorOutdoor="", categories="", isOrderAscending="true",
                    orderField="startDate", surfaceCodes="")
            items = j.get("items") or []
            for t in items:
                if (t.get("tourStatusCode") or "").upper() in ("C", "X") or not t.get("tournamentKey"):
                    continue
                if iso(t.get("startDate")) < first.isoformat():  # listed again in the month it started
                    continue
                evs.append({"key": t["tournamentKey"], "cat": t.get("category") or "", "name": t.get("tournamentName") or t.get("name") or "",
                            "start": iso(t.get("startDate")), "end": iso(t.get("endDate"))})
            skip += 100
            if not items or skip >= (j.get("totalItems") or 0):
                break
        cal[mo] = {"at": NOW.isoformat(timespec="seconds"), "final": last < TODAY - timedelta(days=21), "events": evs}
        print(f"calendar {mo}: {len(evs)} junior events", flush=True)


# ---------------- 2) draws ----------------
def leaves(filters, path=()):
    """Every (playerType, matchType, classification, structure) combination in GetEventFilters' tree."""
    for f in filters or []:
        here = path + ((f.get("dataName"), f.get("valueCode")),)
        if f.get("subFilter"):
            yield from leaves(f["subFilter"], here)
        else:
            yield dict(here)


def team_ids(team):
    return [p["playerId"] for p in (team or {}).get("players") or [] if p and p.get("playerId")]


def matches_in(node):
    """Every match anywhere inside a draw (a dict with two 'teams'), for round-robin groups whose layout varies."""
    if isinstance(node, dict):
        if isinstance(node.get("teams"), list) and len(node["teams"]) == 2 and "playStatusCode" in node:
            yield node
        for v in node.values():
            yield from matches_in(v)
    elif isinstance(node, list):
        for v in node:
            yield from matches_in(v)


def parse_ko(sheet):
    """[[ids, stage, wins]] for a knock-out draw: stage = the round lost in (1 = first round), rounds + 1 = champion;
    wins = matches won (a bye is not a win; a walkover or retirement is)."""
    groups = sheet.get("koGroups") or []
    if not groups:
        return None, 0
    rounds = groups[0].get("rounds") or []
    n = len(rounds)
    seen = {}  # ids -> [last round played or advanced through, lost there?, wins]
    for k, rd in enumerate(rounds, 1):
        for m in rd.get("matches") or []:
            teams = (m.get("teams") or []) + [None, None]
            a, b = tuple(team_ids(teams[0])), tuple(team_ids(teams[1]))
            if not a and not b:
                continue
            bye = not a or not b
            for i, ids in enumerate((a, b)):
                if not ids:
                    continue
                won = bye or bool((teams[i] or {}).get("isWinner"))
                rec = seen.setdefault(ids, [0, False, 0])
                rec[0], rec[1] = k, not won
                if won and not bye:
                    rec[2] += 1
    out = []
    for ids, (k, lost, wins) in seen.items():
        if lost:
            stage = k
        elif k == n:
            stage = n + 1   # won the final
        else:
            stage = k + 1   # draw not finished: counts as reaching the next round
        out.append([list(ids), stage, wins])
    return out, n


def parse_rr(sheet):
    """[[ids, 0, wins]] for a round-robin draw (Junior Finals groups): matches won per player."""
    wins = {}
    for m in matches_in(sheet.get("rrGroups") or sheet):
        played = (m.get("playStatusCode") or "").upper() not in ("", "NP", "TBP")
        for t in (m.get("teams") or [])[:2]:
            ids = tuple(team_ids(t))
            if not ids:
                continue
            rec = wins.setdefault(ids, [list(ids), 0, 0])
            if played and t.get("isWinner"):
                rec[2] += 1
    return list(wins.values()), 0


def draws(state):
    cal = state.get("cal", {})
    done = state.setdefault("done", {})       # tournament key -> UK date read (or "skip")
    tries = state.setdefault("tries", {})
    for mo in sorted(cal, reverse=True):  # newest first: the last 12 months (checkable against our weekly lists) come in first
        raw_path = f"{DIR}/raw/{mo}.json"
        raw = None
        for ev in cal[mo]["events"]:
            k = ev["key"]
            if k in done or not ev["end"] or ev["end"] >= (TODAY - timedelta(days=2)).isoformat() or tries.get(k, 0) >= 3:
                continue
            if left() < 30:
                if raw is not None:
                    save(raw_path, raw)
                return False
            raw = raw if raw is not None else load(raw_path, {})
            try:
                f = get("/TournamentApi/GetEventFilters", tournamentKey=k)
                tid, tt = f.get("tournamentId"), f.get("tourType") or "N"
                got = []
                for leaf in leaves(f.get("filters")):
                    cls = leaf.get("eventClassificationCode") or ""
                    if cls == "Q":
                        continue  # qualifying earns no junior ranking points
                    if cls != "M" and not cls.startswith("PP"):
                        continue
                    s = get("/TournamentApi/GetDrawsheet", drawsheetStructureCode=leaf.get("drawsheetStructureCode") or "KO",
                            eventClassificationCode=cls, matchTypeCode=leaf.get("matchTypeCode"), playerTypeCode=leaf.get("playerTypeCode"),
                            tourType=tt, tournamentId=tid, weekNumber=0)
                    d = {"p": leaf.get("playerTypeCode"), "m": leaf.get("matchTypeCode"), "c": cls, "s": leaf.get("drawsheetStructureCode")}
                    d["r"], d["n"] = parse_ko(s) if d["s"] == "KO" else parse_rr(s)
                    got.append(d)
                raw[k] = {**{x: ev[x] for x in ("cat", "name", "start", "end")}, "d": got}
                done[k] = TODAY.isoformat()
            except Blocked:
                save(raw_path, raw)
                raise
            except Exception as e:
                tries[k] = tries.get(k, 0) + 1
                print("  failed", k, e)
        if raw is not None:
            save(raw_path, raw)
            print(f"draws {mo}: {sum(1 for e in cal[mo]['events'] if e['key'] in done)}/{len(cal[mo]['events'])} events read", flush=True)
    return True


def learn_jm(state, raw_all):
    """Junior Finals points by final place ("1st".."8th" in the ITF's points breakdown), from the latest Finals still
    inside its players' 52 weeks. Read once per edition (about 16 requests)."""
    jms = sorted((ev["start"], k) for k, ev in raw_all.items() if ev["cat"] == "JM" and ev["start"] > (TODAY - timedelta(days=350)).isoformat())
    if not jms or state.get("jmFrom") == jms[-1][1]:
        return
    k = jms[-1][1]
    ids = {pid for d in raw_all[k]["d"] if d.get("m") == "S" for ids, _, _ in d.get("r") or [] for pid in ids}
    table = dict(state.get("jm") or {})
    for pid in sorted(ids):
        if left() < 20:
            return
        bd = get("/PlayerRankApi/GetRankingPoints", circuitCode="JT", matchTypeCode="S", playerId=pid)
        for sec in bd.get("countable") or []:
            for part in ("countablePoints", "nonCountablePoints"):
                for r in ((sec.get(part) or {}).get("pointsBreakdown") or []):
                    m = re.match(r"(\d+)", str(r.get("round") or ""))
                    if r.get("category") == "JM" and m and r.get("points") is not None:
                        table[m.group(1)] = r["points"]
    state["jm"], state["jmFrom"] = table, k
    print("Junior Finals points by place:", table)


# ---------------- 3) rankings ----------------
def stage_key(stage, n):
    """The points-table key for losing in round `stage` of an `n`-round draw (n+1 = champion)."""
    if stage == n + 1:
        return "W"
    left_ = n - stage + 1  # 1 = final, 2 = semi-final...
    return {1: "F", 2: "SF", 3: "QF", 4: "R16", 5: "R32", 6: "R64"}.get(left_)


def results(raw_all, jm_place):
    """{(gender, id): [(start, end, series, cat, match type, points)]} from every saved draw."""
    res = {}
    for k, ev in raw_all.items():
        cat, series = ev["cat"], re.sub(r"-20\d\d-", "-", k)
        if cat == "JM":  # Junior Finals: place from the play-offs, points by place, only for a player who won a match
            place, wins = {}, {}
            for d in ev["d"]:
                if d.get("c") == "M":  # only wins in the round-robin groups unlock points, not play-off wins
                    for ids, stage, w in d.get("r") or []:
                        wins[tuple(ids)] = wins.get(tuple(ids), 0) + w
                m = re.match(r"PP(\d+)-(\d+)", d.get("c") or "")
                if m and d.get("n"):
                    lo = int(m.group(1))
                    for ids, stage, w in d["r"]:
                        if stage == d["n"] + 1:
                            place[tuple(ids)] = lo
                        elif stage == d["n"]:
                            place[tuple(ids)] = min(place.get(tuple(ids), 99), lo + 1)
            for d in ev["d"]:
                if d.get("c") != "M":
                    continue
                for ids, _, _ in d.get("r") or []:
                    p = place.get(tuple(ids))
                    pts = jm_place.get(str(p), 0) if p and wins.get(tuple(ids)) else 0
                    for pid in ids:
                        res.setdefault((d["p"], pid), []).append((ev["start"], ev["end"], series, cat, d["m"], pts or 0))
            continue
        for d in ev["d"]:
            if d.get("c") != "M" or d.get("s") != "KO" or not d.get("r"):
                continue
            table = POINTS.get(d["m"], {}).get(cat)
            if not table:
                continue
            for ids, stage, w in d["r"]:
                pts = table.get(stage_key(stage, d["n"]), 0) if w else 0
                for pid in ids:
                    res.setdefault((d["p"], pid), []).append((ev["start"], ev["end"], series, cat, d["m"], pts))
    return res


def rank_on(day, res, gender, born):
    """The full ranking list for a Monday: [(id, rank, total)]."""
    d = day.isoformat()
    lo = (day - timedelta(days=364)).isoformat()   # a result counts until 52 weeks after the event started
    rows = []
    for (g, pid), rs in res.items():
        if g != gender:
            continue
        by = born.get(pid)
        if by and by < day.year - 18:
            continue  # juniors stay ranked until the end of the year they turn 18
        cur = [r for r in rs if r[1] < d and r[0] > lo and r[5] > 0]
        if not cur:
            continue
        tot, vec = 0.0, {}
        for mt, w in (("S", 1.0), ("D", 0.25)):
            best = {}
            for r in cur:
                if r[4] != mt:
                    continue
                key = r[2] if r[3] not in ("J60", "J30") else r  # J100+: only the best of 2 editions of one event
                if key not in best or r[5] > best[key][5]:
                    best[key] = r
            top = sorted(best.values(), key=lambda r: -r[5])[:6]
            tot += w * sum(r[5] for r in top)
            for r in top:
                vec[(mt, r[3])] = vec.get((mt, r[3]), 0) + r[5]
        if tot > 0:
            rows.append((pid, tot, tuple(-vec.get((mt, c), 0) for mt in "SD" for c in TIE)))
    rows.sort(key=lambda x: (-x[1], x[2]))
    out, prev = [], None
    for i, (pid, tot, v) in enumerate(rows, 1):
        rk = out[-1][1] if prev == (tot, v) else i
        out.append((pid, rk, tot))
        prev = (tot, v)
    return out


def mondays(a, b):
    a = a + timedelta(days=(7 - a.weekday()) % 7)
    while a <= b:
        yield a
        a += timedelta(days=7)


# ---------------- 4) check against every official list we hold ----------------
def check(res, born, hist):
    report, ok = [], True
    for key, g in (("b", "B"), ("g", "G")):
        # year-end lists: exact points per player; the ranking date is the last Monday of the year
        for y, ye in sorted(((hist.get("ye") or {}).get(key) or {}).items()):
            day = max(mondays(date(int(y), 12, 20), date(int(y), 12, 31)))
            mine = {pid: (rk, tot) for pid, rk, tot in rank_on(day, res, g, born)}
            off = ye["ranks"]
            pts = ye.get("points") or {}
            top = [(pid, r) for pid, r in off.items() if r <= 500]
            same = sum(1 for pid, r in top if mine.get(int(pid), (0,))[0] == r)
            psame = sum(1 for pid, p in pts.items() if abs(mine.get(int(pid), (0, -1))[1] - p) < 0.01)
            share = same / max(1, len(top))
            report.append({"list": f"{key} end {y}", "top500": round(share, 4), "points": round(psame / max(1, len(pts)), 4) if pts else None})
            ok &= share >= CHECK_MIN
        # our weekly lists (official), top 500
        for wk in sorted(w for w in hist.get(key, {}) if w >= "2026-06-01"):
            mine = {pid: rk for pid, rk, _ in rank_on(date.fromisoformat(wk), res, g, born)}
            top = [(pid, r) for pid, r in hist[key][wk].items() if r <= 500]
            same = sum(1 for pid, r in top if mine.get(int(pid)) == r)
            share = same / max(1, len(top))
            report.append({"list": f"{key} {wk}", "top500": round(share, 4)})
            ok &= share >= CHECK_MIN
    return ok, report


def main():
    os.makedirs(f"{DIR}/raw", exist_ok=True)
    state = load(STATE, {})
    errors = {}
    finished = False
    b = state.get("blockedAt")
    if b and NOW - datetime.fromisoformat(b) < timedelta(hours=3):
        print("the ITF showed its bot check less than 3 hours ago: leaving it alone"); return
    try:
        calendar(state)
        finished = draws(state)
    except Blocked as e:
        state["blockedAt"] = NOW.isoformat(timespec="seconds")  # wait 3 hours, so the live ITF updates aren't disturbed
        print(e)
    state["checked"] = NOW.isoformat(timespec="seconds")
    save(STATE, state)
    cal = state.get("cal", {})
    todo = sum(1 for mo in cal for ev in cal[mo]["events"] if ev["key"] not in state.get("done", {}) and ev["end"] and ev["end"] < (TODAY - timedelta(days=2)).isoformat())
    print(f"events still to read: {todo}")
    out = load(OUT, {})
    out.update({"checked": state["checked"], "todo": todo, "errors": errors})
    if todo > 20 or not finished or os.environ.get("COLLECT_ONLY") == "1":  # COLLECT_ONLY: read draws, decide nothing
        out.setdefault("ok", False)
        save(OUT, out)
        return
    # every draw is in: rebuild, check, publish
    raw_all = {}
    for mo in sorted(cal):
        raw_all.update(load(f"{DIR}/raw/{mo}.json", {}))
    hist = load(HIST, {})
    born = {}
    for key in ("b", "g"):
        for y, ye in ((hist.get("ye") or {}).get(key) or {}).items():
            for pid, by in (ye.get("born") or {}).items():
                born[int(pid)] = by
        for row in (load("itfjr.json", {}).get(key) or {}).get("players") or []:
            m = re.search(r"/(\d{6,})/", row[7] or "")
            if m and row[3]:
                born[int(m.group(1))] = row[3]
    try:
        learn_jm(state, raw_all)
        save(STATE, state)
    except Blocked as e:
        print(e)
    jm = {**{str(k): v for k, v in JM_PLACE.items()}, **(state.get("jm") or {})}
    res = results(raw_all, jm)
    ok, report = check(res, born, hist)
    for r in report:
        print("check", r)
    out.update({"ok": ok, "check": report, "built": NOW.isoformat(timespec="seconds")})
    if not ok:
        errors["check"] = {"at": NOW.isoformat(timespec="seconds"), "msg": "the rebuilt rankings don't match the official lists closely enough, nothing used"}
        save(OUT, out)
        return
    # weekly lists for the year before our own history starts (for the 3-month / 12-month moves), monthly before that
    weeks = {}
    first_own = min((w for k in ("b", "g") for w in hist.get(k, {})), default=TODAY.isoformat())
    for day in mondays(date(START.year + 1, START.month, 1), TODAY):
        if day.isoformat() >= first_own:
            break
        recent = day >= TODAY - timedelta(days=400)
        if not recent and day.day > 7:
            continue  # older than a year: the first Monday of each month only
        for key, g in (("b", "B"), ("g", "G")):
            weeks.setdefault(key, {})[day.isoformat()] = {str(pid): rk for pid, rk, _ in rank_on(day, res, g, born)}
    out["weeks"] = weeks
    save(OUT, out)
    # progression file for the page: every player's rank on the first Monday of each month (rebuilt, then official)
    dates = sorted({d for k in weeks for d in weeks[k] if date.fromisoformat(d).day <= 7})
    own = sorted(w for w in hist.get("b", {}) if date.fromisoformat(w).day <= 7)
    prog = {"dates": dates + own, "rebuiltTo": dates[-1] if dates else None}
    for key in ("b", "g"):
        ids = {re.search(r"/(\d{6,})/", row[7] or "").group(1) for row in (load("itfjr.json", {}).get(key) or {}).get("players") or []
               if re.search(r"/(\d{6,})/", row[7] or "")}
        cols = [weeks[key][d] for d in dates] + [hist[key].get(w, {}) for w in own]
        prog[key] = {pid: [c.get(pid) for c in cols] for pid in ids}
    save(PROG, prog)
    print(f"published: {len(dates)} months rebuilt")


if __name__ == "__main__":
    main()
