"""
One-off test: could ESPN's free public feed be the main source for ATP and WTA scores?
Run by .github/workflows/espn-probe.yml. Changes nothing on the site; writes its findings to probe/.
Checks: which league names answer, how far back and ahead the scoreboard goes, whether our ATP/WTA players'
matches are there (qualifying included), and whether ESPN's finished scores agree with the results in data.json.
"""
import json, os, re, sys, time, unicodedata, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
from update import ROSTER  # roster names and tours, so the test always uses the current roster

SITE = "https://site.api.espn.com/apis/site/v2/sports/tennis"
OUT = "probe"
NOW = datetime.now(timezone.utc)
os.makedirs(OUT, exist_ok=True)
report = {"ran": NOW.isoformat(timespec="seconds"), "leagues": {}, "days": {}, "ours": [], "compare": [], "notes": []}


def get(url):
    t = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (72Central feed test)", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            return r.status, json.loads(body), round(time.time() - t, 2), len(body)
    except urllib.error.HTTPError as e:
        return e.code, None, round(time.time() - t, 2), 0
    except Exception as e:
        return str(e)[:80], None, round(time.time() - t, 2), 0


def key(s):
    s = unicodedata.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode()
    s = re.sub(r"(?<=[a-z])(ae|oe|ue)", lambda m: m.group(1)[0], s)
    return " ".join(sorted(re.findall(r"[a-z]+", s)))


ours = {key(n): (rid, t) for rid, (n, t) in ROSTER.items() if t in ("atp", "wta")}
# surname + first initial, for feeds that shorten names ("A. de Minaur")
ours_short = {}
for rid, (n, t) in ROSTER.items():
    if t in ("atp", "wta"):
        w = key(n).split()
        ours_short.setdefault(n.split()[-1].lower(), []).append((rid, n.split()[0][0].lower()))


def who(name):
    if key(name) in ours:
        return ours[key(name)][0]
    parts = (name or "").replace(".", " ").split()
    if parts:
        for rid, ini in ours_short.get(unicodedata.normalize("NFKD", parts[-1].lower()).encode("ascii", "ignore").decode(), []):
            if parts[0][:1].lower() == ini:
                return rid
    return None


def comps(node, path=()):
    """Every match ('competition' with competitors) anywhere in the response, with the event/grouping it sits in."""
    if isinstance(node, dict):
        if isinstance(node.get("competitors"), list) and node.get("competitors"):
            yield node, path
            return
        for k, v in node.items():
            nxt = path + ((node.get("name") or node.get("shortName") or ""),) if k in ("groupings", "competitions") else path
            yield from comps(v, nxt)
    elif isinstance(node, list):
        for v in node:
            yield from comps(v, path)


def describe(c, league, path):
    ps = []
    for p in c["competitors"]:
        a = p.get("athlete") or {}
        name = a.get("displayName") or a.get("fullName") or (p.get("roster") or {}).get("displayName") or p.get("displayName") or ""
        sets = []
        for ls in p.get("linescores") or []:
            v = ls.get("value")
            tb = ls.get("tiebreak")
            sets.append(f"{int(v) if isinstance(v, (int, float)) else v}" + (f"({tb})" if tb not in (None, "") else ""))
        ps.append({"name": name, "winner": p.get("winner"), "sets": sets, "order": p.get("order")})
    st = (c.get("status") or {}).get("type") or {}
    return {"league": league, "event": " / ".join(x for x in path if x), "date": c.get("date") or c.get("startDate"),
            "round": (c.get("round") or {}).get("displayName") or (c.get("type") or {}).get("text") or c.get("note"),
            "state": st.get("state"), "detail": st.get("detail") or st.get("shortDetail"), "completed": st.get("completed"),
            "players": ps, "ours": [r for r in (who(p["name"]) for p in ps) if r]}


# 1) Which league names answer (Challenger / ITF slugs are guesses; ESPN only documents atp and wta)
for slug in ("atp", "wta", "atp-challenger", "challenger", "itf", "itf-men", "itf-women", "wta-125"):
    code, js, secs, size = get(f"{SITE}/{slug}/scoreboard")
    n = sum(1 for _ in comps(js)) if js else 0
    report["leagues"][slug] = {"http": code, "seconds": secs, "bytes": size, "matches": n}
    if js and slug in ("atp", "wta"):
        with open(f"{OUT}/raw_{slug}_today.json", "w") as f:
            json.dump(js, f, indent=1)

# 2) Day by day, 10 days back to 3 ahead, for ATP and WTA
seen = {}
for slug in ("atp", "wta"):
    for d in range(-10, 4):
        day = (NOW + timedelta(days=d)).strftime("%Y%m%d")
        code, js, secs, size = get(f"{SITE}/{slug}/scoreboard?dates={day}")
        ms = [describe(c, slug, p) for c, p in comps(js)] if js else []
        evs = sorted({m["event"].split(" / ")[0] for m in ms})
        report["days"][f"{slug} {day}"] = {"http": code, "seconds": secs, "matches": len(ms), "events": evs[:12],
                                           "rounds": sorted({str(m["round"]) for m in ms})[:15]}
        for m in ms:
            if m["ours"]:
                k = (slug, m["date"], tuple(sorted(p["name"] for p in m["players"])))
                seen[k] = m
        time.sleep(1)
report["ours"] = sorted(seen.values(), key=lambda m: (m["date"] or ""))

# 3) Compare with what the current feed recorded in data.json (ATP and WTA tour-level matches)
data = json.load(open("data.json"))
def surname(s):
    return key((s or "").split()[-1]) if s else ""
for m in data.get("matches", []):
    cat = m.get("category") or ""
    if not re.match(r"(ATP|WTA|Grand)", cat):
        continue
    want = {surname(m["p1"]), surname(m["p2"])}
    hit = None
    for e in seen.values():
        names = {surname(p["name"]) for p in e["players"]}
        if want <= names and (e["date"] or "")[:10] >= (datetime.fromisoformat(m["date"]) - timedelta(days=1)).strftime("%Y-%m-%d") \
                and (e["date"] or "")[:10] <= (datetime.fromisoformat(m["date"]) + timedelta(days=1)).strftime("%Y-%m-%d"):
            hit = e
            break
    row = {"date": m["date"], "event": m["tournament"], "cat": cat, "match": f'{m["p1"]} v {m["p2"]}', "ours": m["score"], "oursStatus": m["status"]}
    if hit:
        w = next((p for p in hit["players"] if p["winner"]), None)
        l = next((p for p in hit["players"] if p is not w), None) if w else None
        espn = ", ".join(f"{a}-{b}" for a, b in zip(w["sets"], l["sets"])) if w and l else " / ".join(",".join(p["sets"]) for p in hit["players"])
        row.update(espn=espn, espnWinner=w["name"] if w else None, espnState=hit["state"], espnDetail=hit["detail"], espnRound=hit["round"])
    else:
        row["espn"] = "NOT FOUND"
    report["compare"].append(row)

with open(f"{OUT}/espn_report.json", "w") as f:
    json.dump(report, f, indent=1, ensure_ascii=False)

# short readable summary in the job log
print("LEAGUES", json.dumps(report["leagues"]))
for k, v in report["days"].items():
    print("DAY", k, v["http"], v["matches"], "matches", v["events"][:6], v["rounds"][:8])
print("OUR MATCHES FOUND ON ESPN:", len(report["ours"]))
for m in report["ours"]:
    print("  ", m["league"], (m["date"] or "")[:16], m["event"][:40], m["round"], m["state"], "|", " v ".join(f'{p["name"]} {",".join(p["sets"])}{" W" if p["winner"] else ""}' for p in m["players"]))
print("COMPARE WITH data.json:")
for r in report["compare"]:
    print("  ", r["date"], r["event"], r["match"], "| ours:", r["ours"], r["oursStatus"], "| espn:", r.get("espn"), r.get("espnState") or "", r.get("espnRound") or "")
