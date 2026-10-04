"""One-off check of the Live Tennis API: prints response shapes (never the key)."""
import json, os, urllib.request, urllib.parse

KEY = os.environ["LIVETENNIS_API_KEY"]
BASE = "https://api.livetennisapi.com/api/public/v1"

def get(path, **params):
    url = f"{BASE}{path}" + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
    req = urllib.request.Request(url, headers={"X-API-Key": KEY, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]

def show(label, res, n=1500):
    status, body = res
    print(f"\n===== {label} -> HTTP {status}")
    print((json.dumps(body, indent=1) if not isinstance(body, str) else body)[:n])

# Why has Joel Schwaerzler no ranking? List every matching player record and its detail.
seen = set()
for term in ("Schwaerzler", "Schwarzler", "Joel Josef", "Schw\u00e4rzler"):
    st, body = get("/players", search=term, limit=20)
    rows = body.get("data", []) if isinstance(body, dict) else []
    print(f"\n===== search '{term}' -> HTTP {st}, {len(rows)} results")
    for p in rows:
        print(" ", p.get("id"), "|", p.get("name"), "| tour", p.get("tour"), "| rank", p.get("ranking"), "| pts", p.get("ranking_points"), "| born", p.get("birthday"), "| doubles", p.get("is_doubles_team"))
        if "schw" in (p.get("name") or "").lower() and p.get("id") not in seen:
            seen.add(p.get("id"))
for pid in seen:
    show(f"/players/{pid}", get(f"/players/{pid}"), 1500)
st, body = get("/matches", status="upcoming", player=list(seen), limit=10)
print("\n===== upcoming for those ids ->", st)
for m in (body.get("data", []) if isinstance(body, dict) else []):
    pl = m.get("players", {})
    print(" ", m.get("id"), m.get("tournament"), m.get("scheduled_time"), "|", (pl.get("p1") or {}).get("id"), (pl.get("p1") or {}).get("name"), "vs", (pl.get("p2") or {}).get("id"), (pl.get("p2") or {}).get("name"))
