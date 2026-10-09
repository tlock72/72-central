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
Each player is saved to results/<tour>-<name words sorted>.json (the page reads that file) and refreshed at most once
a day. Files nobody has asked for in 60 days are deleted. Bot check = that site left alone 3 hours (results/status.json,
so the page can say so).
"""
import json, os, re, sys, time, urllib.request
from datetime import timedelta, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prospects as P
import suggest_results as S

DIR = "results"
STATUS = os.path.join(DIR, "status.json")
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
    except Exception as e:
        print("The Sheet's list couldn't be read:", e); return
    files = {f: P.load(f, {}) for f in ("scouting.json", "itfjr.json", "terank.json")}
    suggest = P.load(S.OUT, {}).get("players") or {}
    todo, seen = [], set()
    for a in sorted(asks, key=lambda a: a.get("at") or "", reverse=True):  # newest first
        tour, name = a.get("tour"), (a.get("name") or "").strip()
        if tour not in LISTS or not name or (tour, sorted_words(name)) in seen:
            continue
        seen.add((tour, sorted_words(name)))
        old = P.load(path_of(tour, name), {})
        asked = when(a.get("at"))
        # done already: refreshed today, and after this request was made
        if old.get("day") == T.isoformat() and (not asked or (when(old.get("updated")) or asked) >= asked):
            continue
        todo.append((tour, name, a.get("url") or "", old))
    print(f"{len(asks)} requests, {len(todo)} to look up")
    te_ok, changed = False, False
    for tour, name, url, old in todo:
        if P.out_of_time():
            print("time budget used - the next run carries on"); break
        site = "te" if tour.startswith("te") else "itf"
        if off[site]:
            continue
        row, week = find_row(tour, name, url, files)
        rec = {"tour": tour, "name": name, "day": T.isoformat(), "updated": P.iso(NOW)}
        if not row:
            rec["note"] = "This player isn't on the latest ranking list any more."
            json.dump(rec, open(path_of(tour, name), "w"), ensure_ascii=False, separators=(",", ":")); changed = True
            continue
        rank, rname, nat, born, w = row[:5]
        rurl = row[7] if len(row) > 7 else ""
        g = LISTS[tour][2]
        print("-", tour, rname)
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
                pid, how, itf_name = (old.get("itf"), old.get("how"), old.get("itfName")) if old.get("itf") else \
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
    # nobody asked in 60 days: deleted
    for f in os.listdir(DIR):
        p = os.path.join(DIR, f)
        if f != "status.json" and f.endswith(".json") and P.ago(P.load(p, {}).get("updated")) > timedelta(days=60):
            os.remove(p); changed = True
    for s in ("itf", "te"):
        if not off[s]:
            blocked.pop(s, None)
    new = json.dumps(status, sort_keys=True)
    if changed or new != json.dumps(P.load(STATUS, {}), sort_keys=True):
        json.dump(status, open(STATUS, "w"), separators=(",", ":"))
    print("done")


if __name__ == "__main__":
    main()
