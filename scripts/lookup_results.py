"""
72 Central - last 12 months of results for anyone on Filtered Rankings, on request (free sources only, no Claude,
no Live Tennis API). Run by results.yml: started by the Google Sheet when someone presses "12 months" on a
Filtered Rankings row (scripts/visit_log.gs, kind "results"), and every 30 minutes in case that start was missed.

The Sheet lists the requests of the last 3 days (?kind=lookups). Each player asked for is looked up on the list the
request came from (scouting.json, itfjr.json or terank.json), never from what the page sent, and read the same way as
the watch list and the suggestions (prospects.py / suggest_results.py):
  - ATP/WTA: the ITF player found by name + nationality (exactly one, else no results, never a guess), then ITF
    GetPlayerActivity on the men's / women's circuit, plus junior matches for anyone 18 or under;
  - ITF juniors: the ITF id in the ranking list's link: junior and pro (men's / women's circuit) matches;
  - Tennis Europe U14: the profile in the ranking list's link, its tournaments pages.
Each player is saved to results/<tour>-<name words sorted>.json (the page reads that file). Kept up to date without
anyone pressing the button: every 72 player (on the list the page's rs72() uses) and everyone ever asked for (a file
in results/) is re-read once a day, and a 72 player who has just finished a match (data.json, itfm.json, te.json:
today or yesterday) every 3 hours, so a new result shows the same day. New requests go first, then 72 players, then
the rest, oldest first. Files are never deleted. Bot check = that site left alone 3 hours (results/status.json,
so the page can say so).
"""
import json, os, re, sys, time, urllib.request
from datetime import timedelta, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prospects as P
import suggest_results as S
import update as U  # ROSTER: the 72 players (name, tour)

DIR = "results"
STATUS = os.path.join(DIR, "status.json")
INDEX_NAME = "index.json"  # every file with at least one result: the page turns those players' "12 months" buttons gold
P.BUDGET = timedelta(minutes=12)
P.STARTED = time.monotonic()
T, NOW = P.T, P.NOW
LISTS = {"atp": ("scouting.json", "atp", "M"), "wta": ("scouting.json", "wta", "F"), "itfb": ("itfjr.json", "b", "M"),
         "itfg": ("itfjr.json", "g", "F"), "teb14": ("terank.json", "b14", "M"), "teg14": ("terank.json", "g14", "F")}


def sorted_words(name):
    return S.key("", name)[1:]


def path_of(tour, name):
    """Same as the page's rsFile(): results/<tour>-<name words sorted, joined by hyphens>.json"""
    return os.path.join(DIR, f"{tour}-{sorted_words(name).replace(' ', '-')}.json")


def when(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def requests_list():
    req = urllib.request.Request(P.SHEET_URL + "?kind=lookups", headers={"User-Agent": P.UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8")).get("lookups") or []


def find_row(tour, name, url, files):
    f, k, _ = LISTS[tour]
    rows = ((files[f] or {}).get(k) or {}).get("players") or []
    want = sorted_words(name)
    by_url = [r for r in rows if url and r[7] == url]
    by_name = [r for r in rows if sorted_words(r[1]) == want]
    hit = by_url if len(by_url) == 1 else by_name if len(by_name) == 1 else []
    return hit[0] if hit else None, ((files[f] or {}).get(k) or {}).get("week")


def rk_key(s):
    """Same as the page's rkKey(): letters only, accents off, ae/oe/ue as a/o/u."""
    s = P.unicodedata.normalize("NFD", s or "").lower()
    return re.sub(r"[^a-z]", "", s).replace("ae", "a").replace("oe", "o").replace("ue", "u")


def roster_rows(files):
    """{roster id: (tour, row)} on the list the page's rs72() uses: juniors on Tennis Europe U14 (by roster id), else the
    ITF junior list, else ATP/WTA; pros on ATP/WTA by name (same name, else the one name that starts the same)."""
    try:
        m = re.search(r"const JUNIOR_PROFILES = \[(.*?)\n\];", open("index.html", encoding="utf-8").read(), re.S)
        juniors = set(re.findall(r'\{ id:"([a-z0-9]+)"', m[1])) if m else set()
    except OSError:
        juniors = set()
    rows = lambda f, k: ((files[f] or {}).get(k) or {}).get("players") or []
    out = {}
    for rid, (name, tour) in U.ROSTER.items():
        g = "b" if tour == "atp" else "g"
        hit = None
        if rid in juniors:
            for t, f, k in ((f"te{g}14", "terank.json", g + "14"), (f"itf{g}", "itfjr.json", g)):
                r = next((r for r in rows(f, k) if len(r) > 8 and r[8] == rid), None)
                if r:
                    hit = (t, r); break
        if not hit:
            want, pro = rk_key(name), rows("scouting.json", tour)
            same = [r for r in pro if rk_key(r[1]) == want]
            near = [r for r in pro if rk_key(r[1]).startswith(want) or want.startswith(rk_key(r[1]))]
            r = same[0] if same else near[0] if len(near) == 1 else None
            if r:
                hit = (tour, r)
        if hit:
            out[rid] = hit
    return out


def just_played():
    """Roster ids with a finished match today or yesterday (UK) in the score files."""
    since = (T - timedelta(days=1)).isoformat()
    ids = set()
    for f in ("data.json", "itfm.json", "te.json"):
        for m in P.load(f, {}).get("matches") or []:
            if m.get("status") == "finished" and (m.get("date") or "") >= since:
                ids.update(x for x in (m.get("p1Id"), m.get("p2Id")) if x)
    return ids


def main():
    os.makedirs(DIR, exist_ok=True)
    status = P.load(STATUS, {})
    blocked = status.setdefault("blocked", {})
    for s, t in (P.load(P.OUT, {}).get("blocked") or {}).items():  # a bot check the other scripts hit counts too
        if P.ago(t) < P.ago(blocked.get(s)):
            blocked[s] = t
    off = {s: P.ago(blocked.get(s)) < timedelta(hours=3) for s in ("itf", "te")}
    try:
        asks = requests_list()
        status.pop("sheet", None)
    except Exception as e:
        # e.g. "72 Central" back instead of the list: the Sheet is running an older copy of visit_log.gs (alerted)
        print("The Sheet's list couldn't be read:", e)
        if not status.get("sheet"):
            status["sheet"] = P.iso(NOW)
        if json.dumps(status, sort_keys=True) != json.dumps(P.load(STATUS, {}), sort_keys=True):
            json.dump(status, open(STATUS, "w"), separators=(",", ":"))
        return
    files = {f: P.load(f, {}) for f in ("scouting.json", "itfjr.json", "terank.json")}
    suggest = P.load(S.OUT, {}).get("players") or {}
    itf_ids = P.load("titles.json", {}).get("ids") or {}  # roster id -> ITF id (itf_titles.py)
    today = T.isoformat()
    todo, seen = [], set()

    def add(tour, name, url, rid=None, why=""):
        k = (tour, sorted_words(name))
        if tour not in LISTS or not name or k in seen:
            return
        seen.add(k)
        todo.append((tour, name, url, P.load(path_of(tour, name), {}), rid, why))

    # 1) new requests, newest first (skipped if already read today after the request was made)
    for a in sorted(asks, key=lambda a: a.get("at") or "", reverse=True):
        tour, name = a.get("tour"), (a.get("name") or "").strip()
        if tour not in LISTS or not name:
            continue
        old = P.load(path_of(tour, name), {})
        asked = when(a.get("at"))
        if old.get("day") == today and (not asked or (when(old.get("updated")) or asked) >= asked):
            seen.add((tour, sorted_words(name)))
            continue
        add(tour, name, a.get("url") or "", why="asked")
    # 2) 72 players: daily, and every 3 hours after a match they've just finished
    played = just_played()
    for rid, (tour, row) in roster_rows(files).items():
        old = P.load(path_of(tour, row[1]), {})
        if old.get("day") != today:
            add(tour, row[1], row[7] if len(row) > 7 else "", rid, "daily")
        elif rid in played and P.ago(old.get("updated")) > timedelta(hours=3):
            add(tour, row[1], row[7] if len(row) > 7 else "", rid, "just played")
        else:
            seen.add((tour, sorted_words(row[1])))
    # 3) everyone asked for before: daily, the longest waiting first
    kept = []
    for f in os.listdir(DIR):
        if f not in ("status.json", INDEX_NAME) and f.endswith(".json"):
            old = P.load(os.path.join(DIR, f), {})
            if isinstance(old, dict) and old.get("tour") in LISTS and old.get("name") and old.get("day") != today:
                kept.append(old)
    for old in sorted(kept, key=lambda o: o.get("updated") or ""):
        add(old["tour"], old["name"], old.get("url") or "", why="daily")
    print(f"{len(asks)} requests, {len(todo)} to look up:", ", ".join(f"{t[1]} ({t[5]})" for t in todo[:60]))
    te_ok, changed = False, False
    for tour, name, url, old, rid, why in todo:
        if P.out_of_time():
            print("time budget used - the next run carries on"); break
        site = "te" if tour.startswith("te") else "itf"
        if off[site]:
            continue
        row, week = find_row(tour, name, url, files)
        rec = {"tour": tour, "name": name, "day": today, "updated": P.iso(NOW)}
        if not row:
            if old.get("results"):  # off the list now: the results already read stay, checked again tomorrow
                rec = dict(old, day=today)
            else:
                rec["note"] = "This player isn't on the latest ranking list any more."
            json.dump(rec, open(path_of(tour, name), "w"), ensure_ascii=False, separators=(",", ":")); changed = True
            continue
        rank, rname, nat, born, w = row[:5]
        rurl = row[7] if len(row) > 7 else ""
        rec["url"] = rurl
        g = LISTS[tour][2]
        print("-", tour, rname, f"({why})")
        try:
            if site == "te":
                m = re.search(r"player-profile/([0-9A-Fa-f-]{36})", rurl or "")
                if not m:
                    rec["note"] = "No Tennis Europe profile is linked on the ranking list."
                    res = None
                else:
                    if not te_ok:
                        P.TE.consent(); te_ok = True
                    res = P.te_results(m[1].upper(), rname)
                    if rid and itf_ids.get(rid) and not off["itf"]:
                        # a 72 junior also playing ITF pro events (Futures): their ITF results too, so update.py's
                        # itf_missed() can show a result the score feed never listed
                        try:
                            res += P.itf_results(str(itf_ids[rid]), "MT" if g == "M" else "WT", "itf-pro")
                            rec["itf"] = str(itf_ids[rid])
                        except P.Blocked as e:
                            print(" ", e, "- ITF left alone for 3 hours")
                            off["itf"] = True
                            blocked["itf"] = P.iso(NOW)
                        except Exception as e:
                            print("  ITF results failed:", e)
            elif tour in ("itfb", "itfg"):
                m = re.search(r"/players/[^/]+/(\d+)/", rurl or "")
                if not m:
                    rec["note"] = "No ITF profile is linked on the ranking list."
                    res = None
                else:
                    rec["itf"] = m[1]
                    res = P.itf_results(m[1], "JT", "itf-jr") + P.itf_results(m[1], "MT" if g == "M" else "WT", "itf-pro")
            else:
                # the ITF id: kept from an earlier look-up or the suggestions, else found by name + nationality (never a guess)
                sg = suggest.get(f"{tour}:{sorted_words(rname)}") or {}
                pid, how, itf_name = (str(itf_ids[rid]), "72 roster", rname) if rid and itf_ids.get(rid) else \
                    (old.get("itf"), old.get("how"), old.get("itfName")) if old.get("itf") else \
                    (sg.get("itf"), sg.get("how"), sg.get("itfName")) if sg.get("itf") else (None, None, None)
                if not pid and rname not in S.NO_ITF_LINK:
                    pid, how, itf_name = S.itf_id({"name": rname, "nat": nat, "g": g, "born": born, "rank": rank, "w": w})
                if not pid:
                    rec["note"] = "No single ITF player matches this name and nation, so no results are shown (never a guess)."
                    res = None
                else:
                    rec.update({"itf": pid, "how": how, "itfName": itf_name})
                    res = P.itf_results(pid, "MT" if g == "M" else "WT", "itf-pro")
                    if born and int((week or "")[:4] or T.year) - born <= 18:
                        res += P.itf_results(pid, "JT", "itf-jr")
        except (P.Blocked, P.TE.Stop) as e:
            print(" ", e, "- left alone for 3 hours")
            off[site] = True
            blocked[site] = P.iso(NOW)
            continue
        except Exception as e:
            print("  failed:", e); continue
        if res is not None:
            res.sort(key=lambda r: (r["end"], r["start"]), reverse=True)
            rec.update({"results": res, "w": sum(r["res"] == "W" for r in res), "l": sum(r["res"] == "L" for r in res)})
        rec["name"] = rname
        json.dump(rec, open(path_of(tour, name), "w"), ensure_ascii=False, separators=(",", ":"))
        changed = True
    have = sorted(f[:-5] for f in os.listdir(DIR) if f.endswith(".json") and f not in ("status.json", INDEX_NAME)
                  and (P.load(os.path.join(DIR, f), {}) or {}).get("results"))
    index = os.path.join(DIR, INDEX_NAME)
    if have != P.load(index, None):
        json.dump(have, open(index, "w"), separators=(",", ":"))
    for s in ("itf", "te"):
        if not off[s]:
            blocked.pop(s, None)
    new = json.dumps(status, sort_keys=True)
    if changed or new != json.dumps(P.load(STATUS, {}), sort_keys=True):
        json.dump(status, open(STATUS, "w"), separators=(",", ":"))
    print("done")


if __name__ == "__main__":
    main()
