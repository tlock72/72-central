"""
72 Hub updater — runs on GitHub Actions every 30 minutes, uses no Claude usage.

Reads data.json, pulls live + upcoming matches for the 72 roster from the
Live Tennis API (free plan, key in the LIVETENNIS_API_KEY secret), and writes
data.json back. Free plan = 100 requests/day, so calls are kept small:
  - hourly:               1 call  (live matches for all roster players)
  - once a day per match: 1 call  (final result of any earlier match still without one)
  - every 2 hours:        1 call  (upcoming matches, next 7 days)
  - when a match ends:    1 call  (its final score)
  - once a week (Mon):    1 call per player (rankings)
  - first run only:       1 call per player (find their API ids -> players.json)
"""
import json, os, sys, time, urllib.parse, urllib.request, urllib.error
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

KEY = os.environ.get("LIVETENNIS_API_KEY", "")
BASE = "https://api.livetennisapi.com/api/public/v1"
UK = ZoneInfo("Europe/London")
NOW = datetime.now(timezone.utc)
CALLS = 0
QUOTA_HIT = False  # set when the feed says the free daily allowance is used up
MAX_CALLS = 45  # hard stop per run, protects the daily allowance

# Roster: id -> (full name used for the API search, tour)
ROSTER = {
    "deminaur": ("Alex de Minaur", "atp"), "rublev": ("Andrey Rublev", "atp"), "buse": ("Ignacio Buse", "atp"),
    "altmaier": ("Daniel Altmaier", "atp"), "monfils": ("Gael Monfils", "atp"), "coric": ("Borna Coric", "atp"),
    "schwaerzler": ("Joel Schwaerzler", "atp"), "kym": ("Jerome Kym", "atp"), "kuzuhara": ("Bruno Kuzuhara", "atp"),
    "ivanov": ("Ivan Ivanov", "atp"), "bonding": ("Oliver Bonding", "atp"), "mackenzie": ("Jamie Mackenzie", "atp"),
    "choi": ("Fu Wang Choi", "atp"), "qi": ("Hongjin Qi", "atp"), "chavez": ("Tito Chavez", "atp"),
    "mateo": ("Jorge Mateo", "atp"), "drijver": ("Laurens Drijver", "atp"), "davies": ("Fletcher Davies", "atp"),
    "tarlazzi": ("Diego Tarlazzi", "atp"), "fazekas": ("Vencel Fazekas", "atp"), "farkxodov": ("Saidaslam Farkxodov", "atp"),
    "daraban": ("Luca Daraban", "atp"),
    "svitolina": ("Elina Svitolina", "wta"), "bejlek": ("Sara Bejlek", "wta"), "starodubtseva": ("Yuliia Starodubtseva", "wta"),
    "kasatkina": ("Daria Kasatkina", "wta"), "sawangkaew": ("Mananchaya Sawangkaew", "wta"), "jones": ("Francesca Jones", "wta"),
    "jabeur": ("Ons Jabeur", "wta"), "romero": ("Leyre Romero Gormaz", "wta"), "ristic": ("Mia Ristic", "wta"),
    "rajeshwaran": ("Maaya Rajeshwaran Revathi", "wta"), "dotsenko": ("Ekaterina Dotsenko", "wta"), "newman": ("Welles Newman", "wta"),
    "lin": ("Yu Jun Lin", "wta"), "pinera": ("Paola Pinera Celorio", "wta"), "iwasa": ("Ayaka Iwasa", "wta"),
    "skryp": ("Violetta Skryp", "wta"), "kurylova": ("Nicole Kurylova", "wta"),
    "dudeney": ("Alicia Dudeney", "wta"), "mmakarova": ("Mariia Makarova", "wta"), "vmakarova": ("Varvara Makarova", "wta"),
    "momot": ("Henry Momot", "atp"), "kanabar": ("Jensi Kanabar", "wta"), "liu": ("Xichen Liu", "atp"),
}
# Players whose name is shared with others: pick the one born in this year
BORN = {"ivanov": "2008", "liu": "2015"}


def api(path, **params):
    global CALLS, QUOTA_HIT
    if QUOTA_HIT:
        raise RuntimeError("daily allowance used up")
    if CALLS >= MAX_CALLS:
        raise RuntimeError("per-run call limit reached")
    CALLS += 1
    time.sleep(2.1)  # free plan allows 30 calls a minute
    q = urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(f"{BASE}{path}" + (f"?{q}" if q else ""),
                                 headers={"X-API-Key": KEY, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            QUOTA_HIT = True
        raise


def norm(s):
    import unicodedata
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()
    return " ".join("".join(c if c.isalpha() else " " for c in s).split())


def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def short(name):
    parts = (name or "").split()
    if len(parts) < 2:
        return name or ""
    return f"{parts[0][0]}. {' '.join(parts[1:])}"


def uk(iso):
    if not iso:
        return "", ""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(UK)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")


def category(m):
    tier = (m.get("tier") or "").lower()
    tour = (m.get("tour") or "").lower()
    if tier.startswith("itf"):
        return "ITF " + tier.split("_", 1)[-1].upper() if "_" in tier else ("ITF Women" if tour == "wta" else "ITF")
    if "challenger" in tier or tour == "challenger":
        num = "".join(c for c in tier if c.isdigit())
        return f"Challenger {num}".strip()
    for t in ("atp", "wta"):
        if tier.startswith(t):
            num = "".join(c for c in tier if c.isdigit())
            return f"{t.upper()} {num}".strip()
    return (tour or "").upper()


ROUND = {"F": "Final", "SF": "SF", "QF": "QF", "R16": "R16", "R32": "R32", "R64": "R64", "R128": "R128"}


def score_str(score):
    games = (score or {}).get("games")
    if not games or len(games) != 2:
        return ""
    return ", ".join(f"{a}-{b}" for a, b in zip(games[0], games[1]))


def winner_from(score):
    sets = (score or {}).get("sets") or []
    if len(sets) == 2 and sets[0] != sets[1]:
        return 1 if sets[0] > sets[1] else 2
    return None


def flip(m):
    """The page shows the winner first: swap sides when player 2 won."""
    if m.get("winner") != 2:
        return m
    sc = m.get("score") or ""
    ret = sc.endswith(" ret.")
    core = sc[:-5] if ret else sc
    core = ", ".join("-".join(reversed(x.split("-"))) for x in core.split(", ")) if core else ""
    return dict(m, p1=m["p2"], p2=m["p1"], p1Id=m["p2Id"], p2Id=m["p1Id"], winner=1, score=core + (" ret." if ret else ""))


def poll(aid, m):
    """Look up one of today's matches: finished/cancelled, 'live' only if the feed says it is under way,
    the match with its new start time if the feed has moved it, or None if nothing has changed."""
    d = api(f"/matches/{aid}")
    d = d.get("data", d) if isinstance(d, dict) else {}
    if (d.get("status") or "").lower() in ("live", "in_progress", "inprogress", "started", "playing"):
        return dict(m, status="live")
    done = settle(aid, m, d)
    if done is None and d.get("scheduled_time"):
        date, t = uk(d["scheduled_time"])
        if date and (date, t) != (m.get("date"), m.get("time")):
            print(f"start time moved: {m.get('p1')} v {m.get('p2')} now {date} {t}")
            return dict(m, date=date, time=t)
    return done


def settle(aid, m, d=None):
    """Look the match up once (free endpoint) and return it finished/cancelled, or None if not settled yet."""
    if d is None:
        d = api(f"/matches/{aid}")
        d = d.get("data", d) if isinstance(d, dict) else {}
    status, outcome, w = d.get("status"), d.get("outcome"), d.get("winner")
    if status == "completed" and w in (1, 2):
        score = score_str(d.get("score"))
        rnd = m.get("round") or ""
        if outcome == "walkover":
            score, rnd = "", (rnd + " (walkover)").strip()
        elif outcome in ("retired", "default") and score:
            score += " ret."
        done = dict(m, status="finished", score=score, winner=w, round=rnd, points=None, server=None)
        done.pop("checked", None)
        return flip(done)
    if status == "cancelled" or outcome == "abandoned":
        return dict(m, status="cancelled", points=None, server=None)
    return None


# ---------------------------------------------------------------- main
def main():
    if not KEY:
        sys.exit("LIVETENNIS_API_KEY is not set")
    data = load("data.json", {})
    # Two timers can start this job (GitHub's own schedule and the backup timer). If a timed run
    # happened in the last 20 minutes, skip so the free daily allowance isn't used twice.
    if os.environ.get("SOURCE") == "timer" and data.get("lastChecked"):
        last = datetime.fromisoformat(data["lastChecked"].replace("Z", "+00:00"))
        if NOW - last < timedelta(minutes=20):
            print("ran", int((NOW - last).total_seconds() // 60), "min ago - skipping"); return
    players = load("players.json", {})          # roster id -> {"apiId": int|None, "checked": iso}
    data.setdefault("matches", [])
    data.setdefault("rankings", {})
    data.setdefault("status", {})

    # 1) Find API ids for roster players (first run; unfound players retried weekly).
    #    The feed sometimes holds the same player twice (e.g. "Josef Schwaerzler Joel" with the ranking and
    #    matches, plus an unverified "Joel Schwaerzler"), so names match in any word order and a ranked
    #    record always wins over an unverified duplicate.
    MATCH_V = 2
    searched = 0
    # Calls already spent today (UK date), across all runs. Player searches only run while plenty of the day's
    # 100 calls are left, so a batch of searches can never use up the calls that keep live scores going.
    uk_today = NOW.astimezone(UK).strftime("%Y-%m-%d")
    spent = data.get("callsDay", {}).get("n", 0) if data.get("callsDay", {}).get("date") == uk_today else 0
    for rid, (full, tour) in ROSTER.items():
        rec = players.get(rid)
        stale = rec and rec.get("apiId") is None and (NOW - datetime.fromisoformat(rec["checked"])) > timedelta(days=7)
        if rid in BORN and rec and not rec.get("bornChecked"):
            stale = True
        if rec and rec.get("v") != MATCH_V:
            stale = True
        if rec and not stale:
            continue
        if searched >= 3 or CALLS >= MAX_CALLS - 12 or spent + CALLS >= 40 or os.environ.get("RANKINGS") == "1":
            break  # finish the rest next run (the Monday rankings run keeps its calls for the rankings)
        searched += 1
        try:
            res = api("/players", search=full, limit=50 if rid in BORN else 20).get("data", [])
        except Exception as e:
            print("player search failed", rid, e); break
        want = norm(full).split()
        def same_person(p):
            have = norm(p.get("name")).split()
            return want[-1] in have and any(h[:1] == want[0][:1] for h in have if h != want[-1])
        cands = [p for p in res if not p.get("is_doubles_team") and (p.get("tour") or tour) in (tour, "itf", "challenger", "juniors")
                 and same_person(p) and (rid not in BORN or (p.get("birthday") or "").startswith(BORN[rid]))]
        cands.sort(key=lambda p: (p.get("ranking_status") != "ranked", p.get("ranking") is None, not p.get("birthday")))
        hit = cands[0] if cands else None
        players[rid] = {"apiId": hit["id"] if hit else None, "apiName": hit["name"] if hit else None, "checked": NOW.isoformat(),
                        "v": MATCH_V, **({"bornChecked": True} if rid in BORN else {})}
        if rid in BORN:  # drop any ranking that belonged to a namesake
            data["rankings"].pop(rid, None)
        if hit and hit.get("ranking"):  # the search result already carries the ranking
            prev = (data["rankings"].get(rid) or {}).get("rank")
            data["rankings"][rid] = {"rank": hit["ranking"], "points": hit.get("ranking_points"),
                                     "move": (prev - hit["ranking"]) if prev else None}
        print(f"id {rid}: {players[rid]['apiName']} ({players[rid]['apiId']})")
    with open("players.json", "w") as f:
        json.dump(players, f, indent=1, ensure_ascii=False)

    id2rid = {v["apiId"]: k for k, v in players.items() if v.get("apiId")}
    ids = list(id2rid)
    if not ids:
        print("no players resolved"); return

    def to_match(m, status):
        p1, p2 = m["players"]["p1"], m["players"]["p2"]
        date, t = uk(m.get("scheduled_time") or m.get("live_at"))
        sc = m.get("score")
        return {
            "apiId": m["id"], "date": date, "time": t, "tournament": m.get("tournament") or "",
            "category": category(m), "round": ROUND.get(m.get("round_code") or "", m.get("round_code") or ""),
            "p1": short(p1.get("name")), "p1Id": id2rid.get(p1.get("id")),
            "p2": short(p2.get("name")), "p2Id": id2rid.get(p2.get("id")),
            "status": status, "score": score_str(sc) if status != "scheduled" else "",
            "points": (sc or {}).get("points") if status == "live" else None,
            "server": (sc or {}).get("server") if status == "live" else None,
            "winner": winner_from(sc) if status == "finished" else None,
        }

    old = {m["apiId"]: m for m in data["matches"] if m.get("apiId")}
    new = {}

    # How long since a check last ran. The hourly and 2-hourly checks go by this, not by the clock minute:
    # GitHub often starts its scheduled runs 20-45 minutes late, and the backup timer's run then skips
    # (site updated under 20 minutes ago), so a "first half of the hour only" rule could miss them all day.
    def due(key, minutes):
        last = data.get(key)
        return not last or NOW - datetime.fromisoformat(last.replace("Z", "+00:00")) >= timedelta(minutes=minutes)

    # 2) Live matches (about hourly; the runs in between only do the cheap checks below, to stay well inside
    #    the free plan's 100 calls a day). Live matches aren't shown on the site; this just spots finished ones.
    live_run = due("liveChecked", 50)
    fresh_live = set()
    if live_run:
        try:
            for m in api("/matches", status="live", player=ids, limit=200).get("data", []):
                new[m["id"]] = dict(to_match(m, "live"), seenLive=NOW.strftime("%Y-%m-%dT%H:%M:%SZ"))
                fresh_live.add(m["id"])
            data["liveChecked"] = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception as e:
            print("live fetch failed", e); live_run = False

    # 3) Upcoming matches (about every 2 hours, or if we have none)
    uk_now = NOW.astimezone(UK)
    if due("upcomingChecked", 110) or not any(m["status"] == "scheduled" for m in old.values()):
        try:
            for m in api("/matches", status="upcoming", player=ids, limit=200,
                         **{"from": NOW.strftime("%Y-%m-%d"), "to": (NOW + timedelta(days=7)).strftime("%Y-%m-%d")}).get("data", []):
                new.setdefault(m["id"], to_match(m, "scheduled"))
            data["upcomingChecked"] = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception as e:
            print("upcoming fetch failed", e)
        fetched_upcoming = True
    else:
        fetched_upcoming = False

    # 4) Carry over matches not in this run's feed. A match that was live and has gone, or that left the
    #    upcoming list, is looked up once with the free match-detail endpoint (never guessed from a live score).
    today_s = uk_now.strftime("%Y-%m-%d")
    settled = 0
    cap = 4 if os.environ.get("RANKINGS") == "1" else 18  # the Monday rankings run saves its calls for the rankings
    for aid, m in old.items():
        if aid in new or m["status"] in ("cancelled",):
            continue
        gone_live = m["status"] == "live" and live_run
        left_upcoming = m["status"] == "scheduled" and fetched_upcoming and m["date"] <= today_s
        if m["status"] == "scheduled" and fetched_upcoming and m["date"] > today_s:
            continue  # no longer in the upcoming list: cancelled or moved (a moved match comes back under the same id)
        if (gone_live or left_upcoming) and settled < min(10, cap):
            settled += 1
            try:
                done = settle(aid, m)
            except Exception as e:
                print("result lookup failed", aid, e); done = None
            new[aid] = done or m
        else:
            new[aid] = m

    # 4b) Daily results check: every match of ours from a previous day that still has no result is
    #     looked up once a day (this is what makes results reliable without anyone checking by hand)
    for aid, m in list(new.items()):
        if settled >= cap:
            break
        if m["status"] not in ("scheduled", "live") or not m.get("date") or m["date"] >= today_s or m.get("checked") == today_s:
            continue
        settled += 1
        try:
            done = settle(aid, m)
        except Exception as e:
            print("result check failed", aid, e); done = None
        new[aid] = done or dict(m, checked=today_s)

    # 4c) Today's matches, about once an hour: any match whose start time has passed, or that is in
    #     progress, is looked up, so the page shows "In progress" and then the
    #     final score the same day. At most 5 lookups a run to protect the free daily allowance.
    if live_run and os.environ.get("RANKINGS") != "1":
        now_hm = uk_now.strftime("%H:%M")
        polled = 0
        for aid, m in list(new.items()):
            if polled >= 5:
                break
            if m.get("date") != today_s or m["status"] not in ("scheduled", "live") or m.get("polled") == uk_now.strftime("%H"):
                continue
            if m["status"] == "scheduled" and (not m.get("time") or m["time"] > now_hm):
                continue
            if m["status"] == "live" and aid not in fresh_live and aid in old and old[aid]["status"] == "live":
                continue  # just left the live list: already looked up in step 4
            polled += 1
            try:
                got = poll(aid, m)
            except Exception as e:
                print("today's match lookup failed", aid, e); got = None
            if got and got["status"] == "live":
                got = dict(got, seenLive=NOW.strftime("%Y-%m-%dT%H:%M:%SZ"))
            new[aid] = dict(got or m, polled=uk_now.strftime("%H")) if not got or got["status"] in ("live", "scheduled") else got

    # 5) Merge: keep hand-entered matches (no apiId) unless the API now has the same match
    def key(m):
        return (m["date"], tuple(sorted(norm(m["p1"]).split()[-1:] + norm(m["p2"]).split()[-1:])))
    api_keys = {key(m) for m in new.values()}
    manual = [m for m in data["matches"] if not m.get("apiId") and key(m) not in api_keys]
    cutoff = (NOW - timedelta(days=7)).astimezone(UK).strftime("%Y-%m-%d")
    today = uk_now.strftime("%Y-%m-%d")
    merged = []
    for m in manual + list(new.values()):
        if m["status"] == "finished" and m["date"] < cutoff:
            continue
        if m["status"] == "cancelled":
            continue
        if m["status"] == "scheduled" and m["date"] and m["date"] < (uk_now - timedelta(days=2)).strftime("%Y-%m-%d"):
            continue  # result never arrived; shown as 'result pending' for 2 days, then dropped
        merged.append(m)
    data["matches"] = merged

    # roster-strip overrides only for players with nothing in the list
    busy = {m.get("p1Id") for m in merged} | {m.get("p2Id") for m in merged}
    for rid in list(data["status"]):
        if rid in busy:
            del data["status"][rid]

    # 6) Rankings, once per official ranking week, each tour on its own.
    #    No guessing from the day of the week: Scouting HQ (scouting.py, free sources, no feed calls) already
    #    reads the official ranking week - ATP from Tennis Abstract, WTA from the WTA's own feed. Only when a
    #    tour's official week is newer than the one on the site are any feed calls spent. The feed itself can
    #    lag the official release by hours, so it is probed first (3 calls): if none of the top roster
    #    players' points have changed yet, the feed is still on last week - try again in 2 hours. Weeks with
    #    no new ranking (the middle Monday of two-week events) therefore cost nothing.
    #    All of a tour's players are fetched into a holding area and put on the site in one go.
    sq = load("scouting.json", {})
    official = {t: (sq.get(t) or {}).get("week") for t in ("atp", "wta")}
    # one-off start-up: on 5 Oct 2026 the old Monday logic saved the 28 Sep numbers as "week of 5 Oct"
    tw = data.setdefault("rankingsTourWeek", {"atp": "2026-09-28", "wta": "2026-09-28"})
    tries = data.setdefault("rankingsTry", {})
    nxt_all = data.get("rankingsNext") if isinstance(data.get("rankingsNext"), dict) else {}
    nxt_all = {t: v for t, v in nxt_all.items() if t in ("atp", "wta") and isinstance(v, dict)}

    def fetch_rank(rid, week):
        p = api(f"/players/{players[rid]['apiId']}")
        p = p.get("data", p)
        prev = (data["rankings"].get(rid) or {}).get("rank")
        rank = p.get("ranking")
        return {"rank": rank, "points": p.get("ranking_points"), "move": (prev - rank) if (prev and rank) else None,
                "week": week, **({} if rank else {"note": "Not currently ranked"})}

    for tour in ("atp", "wta"):
        week = official.get(tour)
        if not week or week <= (tw.get(tour) or ""):
            nxt_all.pop(tour, None)
            continue  # no new official week for this tour - nothing to spend
        ids_t = [rid for rid, rec in players.items() if rec.get("apiId") and ROSTER.get(rid, ("", ""))[1] == tour]
        nxt = nxt_all.get(tour) if (nxt_all.get(tour) or {}).get("_week") == week else {"_week": week}
        last_try = tries.get(tour)
        if len(nxt) == 1 and last_try and NOW - datetime.fromisoformat(last_try) < timedelta(hours=2):
            continue  # probed recently and the feed was still on last week
        out_since = (uk_now.date() - date.fromisoformat(week)).days  # days since the official Monday
        if len(nxt) == 1:  # probe: the three best-ranked roster players of this tour
            tries[tour] = NOW.isoformat()
            probe = sorted(ids_t, key=lambda r: (data["rankings"].get(r) or {}).get("rank") or 99999)[:3]
            moved = False
            for rid in probe:
                if CALLS >= MAX_CALLS - 2:
                    break
                try:
                    rec = fetch_rank(rid, week)
                except Exception as e:
                    print("ranking probe failed", rid, e); break
                nxt[rid] = rec
                if rec.get("points") != (data["rankings"].get(rid) or {}).get("points"):
                    moved = True
            if not moved and out_since < 2:  # from Wednesday on, accept it anyway (points can genuinely stand still)
                print(f"{tour.upper()} week {week} is out officially, but the feed hasn't caught up yet - retry in 2 hours")
                nxt_all.pop(tour, None)
                continue
        for rid in ids_t:
            if rid in nxt:
                continue
            if CALLS >= MAX_CALLS - 2:
                break
            try:
                nxt[rid] = fetch_rank(rid, week)
            except Exception as e:
                print("ranking failed", rid, e); break
        if all(rid in nxt for rid in ids_t):
            nxt.pop("_week")
            data["rankings"].update(nxt)
            tw[tour] = week
            tries.pop(tour, None)
            nxt_all.pop(tour, None)
            data["rankingsAsOf"] = today
            print(f"{tour.upper()} rankings published for week of {week}")
        else:
            nxt_all[tour] = nxt
            print(f"{tour.upper()} rankings: {len(nxt) - 1}/{len(ids_t)} fetched, publishing when all are done")
    if nxt_all:
        data["rankingsNext"] = nxt_all
    else:
        data.pop("rankingsNext", None)
    data["rankingsWeek"] = max(w for w in tw.values() if w)

    if QUOTA_HIT:
        data["quotaHit"] = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    data["callsDay"] = {"date": uk_today, "n": spent + CALLS}
    data["lastChecked"] = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    with open("data.json", "w") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"done: {len(merged)} matches, {CALLS} API calls")


if __name__ == "__main__":
    main()
