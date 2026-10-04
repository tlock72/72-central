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

for p in ("q", "search", "name"):
    show(f"/players?{p}=de Minaur", get("/players", **{p: "de Minaur", "limit": 3}), 1200)
show("/matches status=live limit=1", get("/matches", status="live", limit=1), 2500)
show("/matches status=upcoming limit=1", get("/matches", status="upcoming", limit=1), 2500)
show("/matches status=completed limit=1", get("/matches", status="completed", limit=1), 1500)
