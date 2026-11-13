"""One-off check (safe to delete): does a plain request read an ITF junior draw, what does it hold, what are the
official Junior Finals points, and how big is the job. About 12 ITF requests; stops at the bot check."""
import json, time, urllib.parse, urllib.request

UA = "72HubRankings/1.0 (+https://github.com/tlock72/72-central; one-off check)"
ITF = "https://www.itftennis.com/tennis/api"


def get(path, **q):
    time.sleep(4)
    req = urllib.request.Request(f"{ITF}{path}?{urllib.parse.urlencode(q)}", headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            b = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return {"_err": f"HTTP {e.code} {e.read()[:300]}"}
    if "_Incapsula_Resource" in b:
        raise SystemExit("ITF bot check - stopping")
    try:
        return json.loads(b)
    except Exception:
        return {"_raw": b[:500]}


# 1) one draw, plain GET (J300 Porto Alegre 2024, boys singles main draw)
d = get("/TournamentApi/GetDrawsheet", drawsheetStructureCode="KO", eventClassificationCode="M", matchTypeCode="S", playerTypeCode="B",
        tourType="N", tournamentId=1100193877, weekNumber=0)
print("===== drawsheet keys:", list(d)[:20])
g = (d.get("koGroups") or [{}])[0]
print("group keys:", list(g)); rs = g.get("rounds") or []
print("rounds:", len(rs), [ (r.get("roundNumber"), r.get("roundDesc") or r.get("roundName"), len(r.get("matches") or [])) for r in rs])
m = (rs[0].get("matches") or [{}])[0] if rs else {}
print("first match:", json.dumps(m)[:1800])
fin = (rs[-1].get("matches") or [{}])[0] if rs else {}
print("final:", json.dumps(fin)[:1200])

# 2) Junior Finals 2026: event filters, and the official points of its champion (Jordan Lee) and others
ef = get("/TournamentApi/GetEventFilters", tournamentKey="J-JM-CHN-2026-001")
print("===== JM filters:", json.dumps(ef)[:1500])
for pid in (800699673, 800570117):  # Jordan Lee (won), Jamie Mackenzie (5th-8th)
    rp = get("/PlayerRankApi/GetRankingPoints", circuitCode="JT", matchTypeCode="S", playerId=pid)
    print(f"===== GetRankingPoints {pid}:", json.dumps(rp)[:2500])

# 3) year-end list: does it carry birth years?
ye = get("/PlayerRankApi/GetPlayerRankings", circuitCode="JT", playerTypeCode="B", ageCategoryCode="", juniorRankingType="year",
         juniorEndYear=2024, take=3, skip=0, isOrderAscending="true")
print("===== year-end 2024 sample:", json.dumps(ye)[:1200])

# 4) size of the job: junior events per year
for y in (2023, 2024, 2025):
    c = get("/TournamentApi/GetCalendar", circuitCode="JT", searchString="", skip=0, take=10, nationCodes="", zoneCodes="",
            dateFrom=f"{y}-01-01", dateTo=f"{y}-12-31", indoorOutdoor="", categories="", isOrderAscending="true", orderField="startDate", surfaceCodes="")
    print(f"===== calendar {y}: {c.get('totalItems')} junior events")
