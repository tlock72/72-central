"""One-off shape check for Scouting Corner linking: ITF player search/overview and Tennis Europe profile.
No Live Tennis API calls. Prints response shapes only."""
import json, time, urllib.parse, urllib.request, re

UA = "72HubRankings/1.0 (+https://github.com/tlock72/72-central; one-off check)"
ITF = "https://www.itftennis.com/tennis/api"

def get(url, accept="application/json"):
    time.sleep(5)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")

def itf(path, **p):
    return get(f"{ITF}{path}?{urllib.parse.urlencode(p)}")

for name in ["Jamie Mackenzie", "Alex de Minaur"]:
    try:
        b = itf("/PlayerApi/GetPlayerSearch", searchString=name)
        print("SEARCH", name, b[:1500])
    except Exception as e:
        print("search failed", e)
for circ, pid in [("JT", 800570117), ("MT", 800351626)]:
    try:
        b = itf("/PlayerApi/GetPlayerOverview", circuitCode=circ, matchTypeCode="S", playerId=pid)
        d = json.loads(b)
        print("OVERVIEW", circ, {k: (v if not isinstance(v, (list, dict)) else str(v)[:300]) for k, v in d.items()})
    except Exception as e:
        print("overview failed", e, b[:200] if 'b' in dir() else "")
    try:
        b = itf("/PlayerApi/GetPlayerActivity", circuitCode=circ, matchTypeCode="S", playerId=pid, skip=0, take=1)
        print("ACTIVITY", circ, b[:2500])
    except Exception as e:
        print("activity failed", e)
for path in ["/PlayerApi/GetPlayerDetails", "/PlayerApi/GetPlayerProfile", "/PlayerApi/GetPlayerBio"]:
    try:
        print("TRY", path, itf(path, playerId=800570117)[:800])
    except Exception as e:
        print("TRY", path, "failed", e)

# Tennis Europe: profile page header (birth year, nationality, ranking)
SITE = "https://te.tournamentsoftware.com"
from http.cookiejar import CookieJar
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
def te(path, data=None):
    time.sleep(5)
    req = urllib.request.Request(SITE + path, data=data, headers={"User-Agent": "", "Accept": "text/html"})
    with op.open(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")
try:
    te("/cookiewall/Save", urllib.parse.urlencode({"ReturnUrl": "/", "SettingsOpen": "true", "CookiePurposes": "1"}).encode())
    page = te("/find/player?q=" + urllib.parse.quote("Laurens Drijver"))
    i = page.find("player-profile/")
    print("TE FIND", re.sub(r"\s+", " ", page[max(0, i - 1500):i + 1500]))
    page = te("/player-profile/C9E08DE0-4F90-40F9-8E98-9FEA8ACEA8BB")
    i = page.find("Drijver")
    print("TE PROFILE", re.sub(r"\s+", " ", page[max(0, i - 500):i + 4000]))
    page = te("/player-profile/C9E08DE0-4F90-40F9-8E98-9FEA8ACEA8BB/ranking")
    i = page.find("anking")
    print("TE RANKING", re.sub(r"\s+", " ", re.sub(r"<script.*?</script>", "", page, flags=re.S))[:200], "...", re.sub(r"\s+", " ", page[i:i + 4000]))
except Exception as e:
    print("TE failed", e)
