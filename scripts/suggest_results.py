"""
72 Central - last 12 months of results for Scouting Corner's "Computerised suggestions" (run in prospects.yml
after prospects.py; free sources only, no Claude, no Live Tennis API).

The suggestions themselves are picked by the page (sgPick in index.html). This script picks the same way from
scouting.json / terank.json / best.json, takes the top SHOW of each list (a few more than the page shows, because
the page also leaves out 72 players and the watch list), and reads each one's singles matches of the last 12 months:
  - ATP/WTA lists: the ITF player found by name + nationality (exactly one, else left blank, never a
    guess; itf_id), then ITF GetPlayerActivity on the men's / women's circuit (which includes ATP/WTA events), plus
    junior matches for anyone 18 or under;
  - Tennis Europe U14 lists: the Tennis Europe profile linked in terank.json, its tournaments pages.
Writes suggest.json: players{"atp:<name words sorted>"} = {results, w, l, day, ...}. Each player is refreshed at most
once a day, within a time budget (the next run carries on). Bot check = that site left alone 3 hours.
"""
import json, math, os, re, sys, time
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prospects as P  # ITF / Tennis Europe readers and the 12-month match parsing (same as the watch list)

OUT = "suggest.json"
SHOW = 18
P.BUDGET = timedelta(minutes=15)
P.STARTED = time.monotonic()
T, NOW = P.T, P.NOW

# the same lists and limits as SG_LISTS in index.html
LISTS = [
    {"k": "atp", "src": "scouting.json", "g": "M", "maxAge": 21, "maxRank": 1000},
    {"k": "wta", "src": "scouting.json", "g": "F", "maxAge": 21, "maxRank": 1000},
    {"k": "atp", "src": "scouting.json", "g": "M", "maxAge": 30, "maxRank": 350, "over": True},
    {"k": "wta", "src": "scouting.json", "g": "F", "maxAge": 30, "maxRank": 350, "over": True},
    {"k": "b14", "src": "terank.json", "g": "M", "maxAge": 14, "maxRank": 300},
    {"k": "g14", "src": "terank.json", "g": "F", "maxAge": 14, "maxRank": 300},
]
SG_TOP = 35
# a player wrongly linked to an ITF player on the closest name: add their name here (as on the site), e.g. {"Daniel Merida Aguilar"}
NO_ITF_LINK = set()


def key(tour, name):
    """Same as the page's tour + ":" + cnSorted(name): accents off, lower case, hyphens as spaces, words sorted."""
    s = P.unicodedata.normalize("NFD", name or "")
    s = "".join(c for c in s if not P.unicodedata.combining(c)).lower().replace("-", " ")
    return tour + ":" + " ".join(sorted(re.sub(r"[^a-z ]", "", s).split()))


def pick(L, files, best):
    """The page's sgPick, without the 72-player / watch-list filter (that is done on the page)."""
    T_ = (files[L["src"]] or {}).get(L["k"]) or {}
    rows = T_.get("players") or []
    if not rows:
        return []
    pro = L["src"] == "scouting.json"
    yr = int((T_.get("week") or "")[:4] or T.year)
    n, out = len(rows), []
    for r in rows:
        rank, name, nat, born, w, m3, m12, url = r[:8]
        age = yr - born if born else 99
        if age > L["maxAge"] or rank > L["maxRank"] or (pro and rank <= SG_TOP) or (age <= 21 if L.get("over") else pro and age > 21):
            continue
        if not pro and len(r) > 8 and r[8]:
            continue  # 72 player
        gain = lambda p: None if p == -1 else math.log((min(n, rank * 3) if p is None else p) / rank)  # -1 = not tracked, None = not ranked then
        g3, g12 = gain(m3), gain(m12)
        if g3 is None and g12 is None:
            continue
        if m3 is None and m12 is None:
            continue
        if (g12 or 0) < 0 or (g3 or 0) < -math.log(1.1):
            continue
        if w and w > 0 and rank - w > max(10, w * 0.1):
            continue
        if L.get("over"):
            if not (m12 and m12 > 0) or m12 / rank < 2:
                continue
            old = ((best.get(L["k"]) or {}).get("old") or {}).get(name, "missing")
            if old == "missing" or (old and old[0] <= rank * 1.25):
                continue
        score = ((g12 or 0) + 1.5 * (g3 or 0)) * (1 if L.get("over") else 1 + 0.08 * (L["maxAge"] - age))
        if score >= 0.4:
            out.append((score, {"tour": L["k"], "g": L["g"], "name": name, "nat": nat, "born": born, "url": url, "age": age, "rank": rank, "w": w}))
    return [x for _, x in sorted(out, key=lambda x: -x[0])[:SHOW]]


def one(d):
    """(id, how, ITF name) when exactly one fits, else nothing."""
    if len(d) != 1:
        return None, None, None
    k, (how, name) = next(iter(d.items()))
    return k, how, name


def itf_id(c):
    """(ITF id, how, ITF name): exactly one ITF player with this nationality (and the right circuit) that fits, else None.
    1) the same name; 2) not found: each surname word is searched, and a name with extra or fewer words is accepted
    ("Daniel Merida" for "Daniel Merida Aguilar") if at least two words match; 3) still nothing: the closest names
    (sharing a word, or one letter out) are linked only if the ATP/WTA ranking the ITF shows for them matches this
    player's official ranking (same rank, last week's, or within 20%) and the birth year, when the ITF gives one, agrees."""
    def fits(x):
        circ = {v.get("value") for v in x.get("playedCircuits") or []}
        return (x.get("playerNationalityCode") or "").upper() == (c["nat"] or "").upper() and ("WT" if c["g"] == "M" else "MT") not in circ

    hits = {x["playerId"]: ("exact name", P.itf_name(x)) for x in P.itf("/PlayerApi/GetPlayerSearch", searchString=c["name"]).get("players") or []
            if fits(x) and P.same_name(P.itf_name(x), c["name"])}
    if hits:
        return one(hits)
    mine, near = set(P.norm(c["name"]).split()), {}
    words = P.norm(c["name"]).split()
    for word in [w for w in words[1:][::-1] + words[:1] if len(w) >= 3][:3]:  # surname words first, then the first name
        for x in P.itf("/PlayerApi/GetPlayerSearch", searchString=word).get("players") or []:
            theirs = set(P.norm(P.itf_name(x)).split())
            if not fits(x):
                continue
            if len(mine & theirs) >= 2 and (mine <= theirs or theirs <= mine):
                hits[x["playerId"]] = ("name words + nationality", P.itf_name(x))
            elif mine & theirs or P.close(P.itf_name(x), c["name"]):
                near[x["playerId"]] = P.itf_name(x)
    if hits:
        return one(hits)
    # 3) closest name, checked against the official ranking (and birth year)
    circ, ok = "MT" if c["g"] == "M" else "WT", {}
    rank, w = c.get("rank"), c.get("w")
    last = set(P.norm(c["name"]).split()[1:])
    # surname shared or one letter out first; at most 6 looked at (each costs a request)
    for pid, name in sorted(near.items(), key=lambda x: not (last & set(P.norm(x[1]).split()) or P.close(x[1], c["name"])))[:6]:
        r = P.itf_overview(pid, circ).get("rank")
        if not r or not rank or not (r in (rank, w) or abs(r - rank) <= max(5, 0.2 * rank)):
            continue
        if c.get("born"):
            try:
                y = P.itf_born(pid, [circ])
            except P.Blocked:
                raise
            except Exception:
                y = None
            if y and y != c["born"]:
                continue
        ok[pid] = (f"closest name ({name}) + nationality + ranking (ITF shows No. {r})", name)
    return one(ok)


def main():
    files = {f: P.load(f, {}) for f in ("scouting.json", "terank.json")}
    best = P.load("best.json", {})
    data = P.load(OUT, {})
    before = json.dumps({k: v for k, v in data.items() if k != "checked"}, sort_keys=True)
    players = data.setdefault("players", {})
    blocked = data.setdefault("blocked", {})
    # also respect a bot check prospects.py hit in this same run
    for s, t in (P.load(P.OUT, {}).get("blocked") or {}).items():
        if P.ago(t) < P.ago(blocked.get(s)):
            blocked[s] = t
    off = {s: P.ago(blocked.get(s)) < timedelta(hours=3) for s in ("itf", "te")}
    want = {}
    for L in LISTS:
        for c in pick(L, files, best):
            want.setdefault(key(c["tour"], c["name"]), c)
    for k in [k for k in players if k not in want and P.ago(players[k].get("updated")) > timedelta(days=21)]:
        del players[k]  # off the lists for 3 weeks
    todo = sorted((k for k in want if (players.get(k) or {}).get("day") != T.isoformat()), key=lambda k: (k in players, (players.get(k) or {}).get("day") or ""))
    print(f"Suggestions: {len(want)} players, {len(todo)} to refresh")
    te_ok = False
    for k in todo:
        if P.out_of_time():
            print("time budget used - the next run carries on"); break
        c, rec = want[k], players.setdefault(k, {})
        te = c["tour"] in ("b14", "g14")
        if off["te" if te else "itf"]:
            continue
        print("-", c["name"])
        try:
            if te:
                m = re.search(r"player-profile/([0-9A-Fa-f-]{36})", c.get("url") or "")
                if not m:
                    continue
                if not te_ok:
                    P.TE.consent(); te_ok = True
                res = P.te_results(m[1].upper(), c["name"])
            else:
                if c["name"] in NO_ITF_LINK:
                    rec.pop("itf", None); rec.pop("results", None)
                    rec.update({"name": c["name"], "itfName": None, "how": "left unlinked by hand", "day": T.isoformat(), "updated": P.iso(NOW)})
                    continue
                if not rec.get("itf") and (P.ago(rec.get("tried")) > P.RECHECK or "itfName" not in rec):
                    rec["tried"] = P.iso(NOW)
                    rec["itf"], rec["how"], rec["itfName"] = itf_id(c)
                if not rec.get("itf"):
                    rec.update({"name": c["name"], "day": T.isoformat(), "updated": P.iso(NOW)})
                    continue  # no single ITF player with this name and nationality: no results shown
                res = P.itf_results(rec["itf"], "MT" if c["g"] == "M" else "WT", "itf-pro")
                if c["age"] <= 18:
                    res += P.itf_results(rec["itf"], "JT", "itf-jr")
        except (P.Blocked, P.TE.Stop) as e:
            print(" ", e, "- left alone for 3 hours")
            s = "te" if te else "itf"
            off[s] = True
            blocked[s] = P.iso(NOW)
            continue
        except Exception as e:
            print("  failed:", e); continue
        res.sort(key=lambda r: (r["end"], r["start"]), reverse=True)
        rec.update({"name": c["name"], "results": res, "w": sum(r["res"] == "W" for r in res), "l": sum(r["res"] == "L" for r in res),
                    "day": T.isoformat(), "updated": P.iso(NOW)})
    # links made on the closest name are alerted once each (report_gaps.py), so a wrong one can be spotted
    data["checks"] = [f"Suggestions: {r['name']} linked to the ITF player {r['itfName']} (id {r['itf']}) by {r['how']}. "
                      f"If that's the wrong player, add their name to NO_ITF_LINK in scripts/suggest_results.py."
                      for k, r in players.items() if k in want and r.get("itf") and (r.get("how") or "").startswith("closest")]
    for s in ("itf", "te"):
        if not off[s]:
            blocked.pop(s, None)
    if json.dumps({k: v for k, v in data.items() if k != "checked"}, sort_keys=True) == before:
        print("nothing new"); return
    data["checked"] = P.iso(NOW)
    with open(OUT, "w") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"done: {sum(1 for r in players.values() if r.get('day') == T.isoformat())} of {len(want)} refreshed today")


if __name__ == "__main__":
    main()
