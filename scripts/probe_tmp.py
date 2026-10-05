"""Temporary probe 4 (deleted after use)."""
import json, re, time, urllib.parse, urllib.request
H = {"User-Agent": "72CentralSchedule/1.0 (+https://github.com/tlock72/72-central; weekly)", "Accept": "application/json"}
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=40) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return getattr(e, "code", "ERR"), str(e)[:200]
for page in ("2026_ATP_Tour", "2026_ATP_Challenger_Tour", "2026_WTA_Tour", "2026_WTA_125_tournaments"):
    st, b = get("https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({"action": "parse", "page": page, "prop": "wikitext", "format": "json", "formatversion": 2}))
    print("\n=====", page, st, len(b))
    if st != 200: print(b[:300]); continue
    w = json.loads(b)["parse"]["wikitext"]
    i = w.find("October"); print(w[i:i+3500] if i >= 0 else w[:2000])
    time.sleep(1)
