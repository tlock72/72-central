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
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

KEY = os.environ.get("LIVETENNIS_API_KEY", "")
BASE = "https://api.livetennisapi.com/api/public/v1"
UK = ZoneInfo("Europe/London")
NOW = datetime.now(timezone.utc)
CALLS = 0
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
    global CALLS
    if CALLS >= MAX_CALLS:
        raise RuntimeError("per-run call limit reached")
    CALLS += 1
    time.sleep(2.1)  # free plan allows 30 calls a minute
    q = urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(f"{BASE}{path}" + (f"?{q}" if q else ""),
                                 headers={"X-API-Key": KEY, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


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


def settle(aid, m):
    """Look the match up once (free endpoint) and return it finished/cancelled, or None if not settled yet."""
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
    for rid, (full, tour) in ROSTER.items():
        rec = players.get(rid)
        stale = rec and rec.get("apiId") is None and (NOW - datetime.fromisoformat(rec["checked"])) > timedelta(days=7)
        if rid in BORN and rec and not rec.get("bornChecked"):
            stale = True
        if rec and rec.get("v") != MATCH_V:
            stale = True
        if rec and not stale:
            continue
        if CALLS >= MAX_CALLS - 12 or os.environ.get("RANKINGS") == "1":
            break  # finish the rest next run (the Monday rankings run keeps its calls for the rankings)
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

    # 2) Live matches (hourly - the :13 run; the :43 run only does the cheap checks below, to stay well inside
    #    the free plan's 100 calls a day). Live matches aren't shown on the site; this just spots finished ones.
    live_run = NOW.minute < 30
    if live_run:
        try:
            for m in api("/matches", status="live", player=ids, limit=200).get("data", []):
                new[m["id"]] = to_match(m, "live")
        except Exception as e:
            print("live fetch failed", e); live_run = False

    # 3) Upcoming matches (every 2 hours, or if we have none)
    uk_now = NOW.astimezone(UK)
    if uk_now.hour % 2 == 1 and uk_now.minute < 30 or not any(m["status"] == "scheduled" for m in old.values()):
        try:
            for m in api("/matches", status="upcoming", player=ids, limit=200,
                         **{"from": NOW.strftime("%Y-%m-%d"), "to": (NOW + timedelta(days=7)).strftime("%Y-%m-%d")}).get("data", []):
                new.setdefault(m["id"], to_match(m, "scheduled"))
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

    # 6) Rankings once a week, all at once. The Monday 07:00 UK run (RANKINGS=1, started by the timer together
    #    with the ITF junior rankings) fetches every player's ranking into a holding area and only puts them on
    #    the site when every player is done, so the whole table changes in one go. If that run is missed or cut
    #    short, later runs finish it from 09:00 - and the switch still happens all at once.
    week = (uk_now - timedelta(days=uk_now.weekday())).strftime("%Y-%m-%d")  # this week's Monday
    nxt = data.get("rankingsNext") or {}
    if nxt.get("_week") != week:
        nxt = {"_week": week}
    with_id = [rid for rid, rec in players.items() if rec.get("apiId")]

    def fetch_rank(rid):
        p = api(f"/players/{players[rid]['apiId']}")
        p = p.get("data", p)
        prev = (data["rankings"].get(rid) or {}).get("rank")
        rank = p.get("ranking")
        return {"rank": rank, "points": p.get("ranking_points"), "move": (prev - rank) if (prev and rank) else None,
                "week": week, **({} if rank else {"note": "Not currently ranked"})}

    if data.get("rankingsWeek") != week:
        if os.environ.get("RANKINGS") == "1" or len(nxt) > 1 or uk_now.weekday() > 0 or uk_now.hour >= 9:
            for rid in with_id:
                if rid in nxt:
                    continue
                if CALLS >= MAX_CALLS - 2:
                    break
                try:
                    nxt[rid] = fetch_rank(rid)
                except Exception as e:
                    print("ranking failed", rid, e); break
            if all(rid in nxt for rid in with_id):
                nxt.pop("_week")
                data["rankings"].update(nxt)
                data["rankingsWeek"] = week
                data["rankingsAsOf"] = today
                data.pop("rankingsNext", None)
                print("rankings published for week of", week)
            else:
                data["rankingsNext"] = nxt
                print(f"rankings: {len(nxt) - 1}/{len(with_id)} fetched, publishing when all are done")
    else:  # a player whose feed record was re-matched mid-week: refresh just them
        for rid in with_id:
            if (data["rankings"].get(rid) or {}).get("week") != week and CALLS < MAX_CALLS - 2:
                try:
                    data["rankings"][rid] = fetch_rank(rid)
                except Exception as e:
                    print("ranking failed", rid, e); break

    data["lastChecked"] = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    with open("data.json", "w") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"done: {len(merged)} matches, {CALLS} API calls")


if __name__ == "__main__":
    main()
