"""One-off shape check (Scouting Corner): Tennis Europe profile text and ITF search with several hits. No Live Tennis API calls."""
import json, re, time, urllib.parse, urllib.request, html
from http.cookiejar import CookieJar
UA = "72HubRankings/1.0 (+https://github.com/tlock72/72-central; one-off check)"
def itf(path, **p):
    time.sleep(5)
    req = urllib.request.Request(f"https://www.itftennis.com/tennis/api{path}?{urllib.parse.urlencode(p)}", headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")
try:
    d = json.loads(itf("/PlayerApi/GetPlayerSearch", searchString="Ivan Ivanov"))
    print("ITF MULTI", [(p["playerId"], p["givenName"], p["familyName"], p["playerNationalityCode"], [c["value"] for c in p.get("playedCircuits") or []]) for p in d.get("players") or []][:15])
    d = json.loads(itf("/PlayerApi/GetPlayerActivity", circuitCode="JT", matchTypeCode="S", playerId=800570117, skip=0, take=20))
    print("ITF ACT DATES", d.get("totalItems"), [(t.get("dates"), t.get("tourCode"), t.get("tournamentType")) for t in d.get("items") or []])
except Exception as e:
    print("ITF failed", e)
SITE = "https://te.tournamentsoftware.com"
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
def te(path, data=None):
    time.sleep(5)
    req = urllib.request.Request(SITE + path, data=data, headers={"User-Agent": "", "Accept": "text/html"})
    with op.open(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")
def text(page):
    page = re.sub(r"<(script|style|svg)[^>]*>.*?</\1>", " ", page, flags=re.S)
    page = re.sub(r"<[^>]+>", " ", page)
    return re.sub(r"\s+", " ", html.unescape(page))
try:
    te("/cookiewall/Save", urllib.parse.urlencode({"ReturnUrl": "/", "SettingsOpen": "true", "CookiePurposes": "1"}).encode())
    pid = "C9E08DE0-4F90-40F9-8E98-9FEA8ACEA8BB"
    for sub in ["", "/ranking", "/statistics"]:
        t = text(te(f"/player-profile/{pid}{sub}"))
        i = t.find("Laurens Drijver")
        print("TE", sub or "/", t[i:i + 2500])
    p = te(f"/player-profile/{pid}/ranking")
    print("TE RANK LINKS", sorted(set(re.findall(r'href="(/ranking[^"]*)"', p)))[:20])
    p = te("/find/player?q=" + urllib.parse.quote("Maria Ivanova"))
    print("TE MULTI", re.findall(r'player-profile/([0-9A-Fa-f-]{36})"[^>]*>\s*<span class="nav-link__value">([^<]+)', p)[:10])
    print("TE MULTI SUBINFO", text(p)[:1500])
except Exception as e:
    print("TE failed", e)
