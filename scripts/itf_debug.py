"""One-off: print what the ITF returns for the Junior Finals (Makarova / Mackenzie), to see why results are missing."""
import json, time, urllib.parse, urllib.request
BASE = "https://www.itftennis.com/tennis/api"
UA = "72HubRankings/1.0 (+https://github.com/tlock72/72-central; one-off check)"
KEY = "j-jm-chn-2026-001"

def get(path, **p):
    time.sleep(5)
    url = f"{BASE}{path}?{urllib.parse.urlencode(p)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
    except Exception as e:
        body = f"ERROR {e}"
    print(f"\n=== {path} {p}\n{body[:6000]}")
    return body

for pid in (800644962, 800570117):
    b = get("/PlayerApi/GetPlayerActivity", circuitCode="JT", matchTypeCode="S", playerId=pid, skip=0, take=1)
days = get("/TournamentApi/GetOrderOfPlayDays", tournamentKey=KEY)
try:
    for d in json.loads(days) or []:
        get("/TournamentApi/GetOrderOfPlay", orderOfPlayDayId=d["orderOfPlayDayId"])
except Exception as e:
    print("days not JSON", e)
get("/TournamentApi/GetEventFilters", tournamentKey=KEY)
get("/TournamentApi/GetDrawsheet", tournamentKey=KEY, round=1, matchTypeCode="S", eventClassificationCode="G")
