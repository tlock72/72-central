"""Temporary probe 3 (deleted after use). Uses at most 4 Live Tennis API calls; never prints the key."""
import json, os, time, urllib.parse, urllib.request
KEY = os.environ.get("LIVETENNIS_API_KEY", "")
B = "https://api.livetennisapi.com/api/public/v1"
def lt(path, **p):
    u = f"{B}{path}?" + urllib.parse.urlencode(p)
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"X-API-Key": KEY, "Accept": "application/json"}), timeout=30) as r:
            return r.status, r.read().decode()
    except Exception as e:
        return getattr(e, "code", "ERR"), (e.read().decode()[:300] if hasattr(e, "read") else str(e))
for path, p in (("/tournaments", {"limit": 3}), ("/tournaments", {"tour": "atp", "year": 2026, "limit": 100}),
                ("/tournaments", {"tour": "challenger", "limit": 3})):
    st, b = lt(path, **p); print("\n=====", path, p, st, len(b)); print(b[:3000])
    if st == 404: break
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as r:
            return r.status, r.read()
    except Exception as e:
        return getattr(e, "code", "ERR"), b""
for f in ("mda.pdf", "acceptance.pdf", "acc.pdf", "accept.pdf", "mdsaccept.pdf", "entrylist.pdf", "ent.pdf", "mdslist.pdf", "qs.pdf"):
    st, b = get(f"https://www.protennislive.com/posting/2026/5014/{f}"); print("PTL", f, st, len(b)); time.sleep(1)
