"""
One-off test: how quickly does ESPN's free feed update live tennis scores?
Checks the ATP and WTA scoreboards every 20 seconds for MINUTES minutes and records every change to each live
singles match (games, tiebreaks, status text, and any point-level fields), with the time it was seen.
Run by .github/workflows/espn-live-probe.yml on the test branch only. Changes nothing on the site.
"""
import json, os, sys, time, urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from espn_probe import comps, who  # same match finder and roster matching as the first test

SITE = "https://site.api.espn.com/apis/site/v2/sports/tennis"
MINUTES = float(os.environ.get("MINUTES", "20"))
os.makedirs("probe", exist_ok=True)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (72Central feed test)", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def sig(c):
    """Everything about a match that changes during play."""
    parts = []
    for p in c["competitors"]:
        sets = [f'{int(l.get("value", 0))}' + (f'({l["tiebreak"]})' if l.get("tiebreak") not in (None, "") else "") for l in p.get("linescores") or []]
        extra = {k: p[k] for k in ("score", "possession", "serving", "points", "currentPoints", "gameScore") if k in p}
        parts.append(",".join(sets) + (json.dumps(extra, sort_keys=True) if extra else ""))
    st = c.get("status") or {}
    extra = {k: c[k] for k in ("situation", "serving", "points") if k in c}
    return " | ".join(parts) + f' [{(st.get("type") or {}).get("detail")}] ' + (json.dumps(extra, sort_keys=True) if extra else "")


start = time.time()
seen, log, polls, saved, errors = {}, [], 0, False, []
while time.time() - start < MINUTES * 60:
    now = datetime.now(timezone.utc).strftime("%H:%M:%S")
    for lg in ("atp", "wta"):
        try:
            js = get(f"{SITE}/{lg}/scoreboard")
        except Exception as e:
            errors.append(f"{now} {lg} {e}")
            continue
        for c, path in comps(js):
            if (c.get("type") or {}).get("slug", "").endswith("doubles"):
                continue
            if ((c.get("status") or {}).get("type") or {}).get("state") != "in" and c["id"] not in seen:
                continue
            names = " v ".join((p.get("athlete") or {}).get("displayName", "?") for p in c["competitors"])
            s = sig(c)
            if seen.get(c["id"]) != s:
                ours = [r for r in (who((p.get("athlete") or {}).get("displayName")) for p in c["competitors"]) if r]
                log.append({"t": now, "id": c["id"], "match": names, "ours": ours, "sig": s})
                print(now, "72" if ours else "  ", names, "|", s, flush=True)
                seen[c["id"]] = s
            if not saved:
                json.dump(c, open("probe/live_sample.json", "w"), indent=1)
                saved = True
    polls += 1
    time.sleep(20)

# per match: how many changes, and the gaps between them
per = {}
for e in log:
    per.setdefault(e["id"], {"match": e["match"], "ours": e["ours"], "times": []})["times"].append(e["t"])
def secs(t): h, m, s = map(int, t.split(":")); return h * 3600 + m * 60 + s
for v in per.values():
    ts = [secs(t) for t in v["times"]]
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    v["changes"] = len(ts) - 1
    v["medianGapSeconds"] = sorted(gaps)[len(gaps) // 2] if gaps else None
json.dump({"ran": datetime.now(timezone.utc).isoformat(timespec="seconds"), "minutes": MINUTES, "polls": polls,
           "errors": errors, "matches": per, "log": log}, open("probe/live_report.json", "w"), indent=1, ensure_ascii=False)
print("SUMMARY", polls, "polls,", len(per), "live matches,", len(errors), "errors")
for v in per.values():
    print("  ", v["match"], v["ours"], "changes:", v["changes"], "median gap (s):", v["medianGapSeconds"])
