"""
72 Hub updater — runs on GitHub Actions every 30 minutes, uses no Claude usage.

Reads data.json, pulls live + upcoming matches for the 72 roster from the
Live Tennis API (free plan, key in the LIVETENNIS_API_KEY secret), and writes
data.json back. Free plan = 100 requests/day, so calls are kept small:
  - every run:            1 call  (live matches for all roster players)
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
}
# Players whose name is shared with others: pick the one born in this year
BORN = {"ivanov": "2008"}


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


# ---------------------------------------------------------------- main
def main():
    if not KEY:
        sys.exit("LIVETENNIS_API_KEY is not set")
    data = load("data.json", {})
    players = load("players.json", {})          # roster id -> {"apiId": int|None, "checked": iso}
    data.setdefault("matches", [])
    data.setdefault("rankings", {})
    data.setdefault("status", {})

    # 1) Find API ids for roster players (first run; unfound players retried weekly)
    for rid, (full, tour) in ROSTER.items():
        rec = players.get(rid)
        stale = rec and rec.get("apiId") is None and (NOW - datetime.fromisoformat(rec["checked"])) > timedelta(days=7)
        if rid in BORN and rec and not rec.get("bornChecked"):
            stale = True
        if rec and not stale:
            continue
        try:
            res = api("/players", search=full, limit=50 if rid in BORN else 10).get("data", [])
        except Exception as e:
            print("player search failed", rid, e); break
        want = norm(full).split()
        hit = next((p for p in res if not p.get("is_doubles_team") and (p.get("tour") or tour) in (tour, "itf", "challenger", "juniors")
                    and all(w in norm(p.get("name")).split() for w in want[-1:]) and norm(p.get("name"))[0] == want[0][0]
                    and (rid not in BORN or (p.get("birthday") or "").startswith(BORN[rid]))), None)
        players[rid] = {"apiId": hit["id"] if hit else None, "apiName": hit["name"] if hit else None, "checked": NOW.isoformat(), **({"bornChecked": True} if rid in BORN else {})}
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

    # 2) Live matches (every run)
    try:
        for m in api("/matches", status="live", player=ids, limit=200).get("data", []):
            new[m["id"]] = to_match(m, "live")
    except Exception as e:
        print("live fetch failed", e)

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

    # 4) Matches that were live last run but aren't now -> fetch final score
    for aid, m in old.items():
        if aid in new:
            continue
        if m["status"] == "live":
            try:
                sc = api(f"/matches/{aid}/score")
                m = dict(m, status="finished", score=score_str(sc) or m["score"], winner=winner_from(sc) or m.get("winner"),
                         points=None, server=None)
            except Exception as e:
                print("final score failed", aid, e)
                m = dict(m, status="finished", points=None, server=None, winner=m.get("winner"))
            if m.get("winner") == 2:  # page shows the winner first
                m = dict(m, p1=m["p2"], p2=m["p1"], p1Id=m["p2Id"], p2Id=m["p1Id"], winner=1,
                         score=", ".join("-".join(reversed(s.split("-"))) for s in m["score"].split(", ")) if m["score"] else "")
            new[aid] = m
        elif m["status"] == "scheduled" and not fetched_upcoming:
            new[aid] = m  # keep until the next upcoming refresh
        elif m["status"] == "finished":
            new[aid] = m

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
        if m["status"] == "scheduled" and m["date"] and m["date"] < today:
            continue  # stale schedule entry
        merged.append(m)
    data["matches"] = merged

    # roster-strip overrides only for players with nothing in the list
    busy = {m.get("p1Id") for m in merged} | {m.get("p2Id") for m in merged}
    for rid in list(data["status"]):
        if rid in busy:
            del data["status"][rid]

    # 6) Rankings once a week (Monday, first run of the day) or if never done via the API
    if not data.get("rankingsFromApi") and all(r in players for r in ROSTER):
        data["rankingsFromApi"] = True
        data["rankingsAsOf"] = today
    elif uk_now.weekday() == 0 and uk_now.hour < 9 and data.get("rankingsAsOf") != today:
        for rid, rec in players.items():
            if not rec.get("apiId"):
                continue
            try:
                p = api(f"/players/{rec['apiId']}")
                p = p.get("data", p)
            except Exception as e:
                print("ranking failed", rid, e); break
            prev = (data["rankings"].get(rid) or {}).get("rank")
            rank = p.get("ranking")
            move = (prev - rank) if (prev and rank) else None
            data["rankings"][rid] = {"rank": rank, "points": p.get("ranking_points"), "move": move,
                                     **({} if rank else {"note": "Not currently ranked"})}
        else:
            data["rankingsAsOf"] = today

    data["lastChecked"] = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    with open("data.json", "w") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"done: {len(merged)} matches, {CALLS} API calls")


if __name__ == "__main__":
    main()
