"""One-off check of ranking sources for Scouting HQ: prints response shapes (never the key)."""
import json, os, urllib.request, urllib.parse

KEY = os.environ.get("LIVETENNIS_API_KEY", "")
BASE = "https://api.livetennisapi.com/api/public/v1"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def fetch(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/html", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, repr(e)


def show(label, url, headers=None, n=900):
    st, body = fetch(url, headers)
    print(f"\n===== {label} -> HTTP {st}, {len(body)} chars\n{body[:n]}")
    return st, body


lt = {"X-API-Key": KEY}
for q in ("tour=atp&limit=100&sort=ranking", "tour=wta&limit=100&page=2", "tour=atp&limit=100&offset=100&order=ranking",
          "ranking_status=ranked&tour=wta&limit=50"):
    st, body = show(f"LT /players?{q}", f"{BASE}/players?{q}", lt, 500)
    try:
        d = json.loads(body)
        rows = d.get("data", [])
        print("keys:", [k for k in d if k != "data"], {k: d[k] for k in d if k != "data"})
        print("rows:", len(rows), [(p.get("name"), p.get("ranking"), p.get("birthday")) for p in rows[:6]])
    except Exception:
        pass
show("LT /rankings", f"{BASE}/rankings?tour=atp&limit=5", lt, 600)

show("WTA api (old date)", "https://api.wtatennis.com/tennis/players/ranked?page=0&pageSize=3&type=rankSingles&sort=asc&metric=SINGLES&at=2025-10-06", n=1500)
show("WTA api (page 9 of 100)", "https://api.wtatennis.com/tennis/players/ranked?page=9&pageSize=100&type=rankSingles&sort=asc&metric=SINGLES", n=300)
show("ATP gateway", "https://app.atptour.com/api/gateway/rankings.ranksglrollrange?fromRank=1&toRank=3", n=600)
show("ATP rankings page (old date)", "https://www.atptour.com/en/rankings/singles?rankRange=0-100&rankDate=2025-10-06", n=300)
show("ATP rankings page (1000)", "https://www.atptour.com/en/rankings/singles?rankRange=1-1000", n=300)
show("ATP player bio", "https://www.atptour.com/en/-/www/players/hero/d0gn?v=1", n=600)
show("live-tennis.eu ATP U21", "https://live-tennis.eu/en/atp-ranking-under-21", n=300)
