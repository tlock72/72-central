"""One-off check (safe to delete): request formats for the ITF junior calendar, draws and points breakdown,
and the junior ranking rules a public project uses. About 6 ITF requests; stops at the bot check."""
import json, re, subprocess, time, urllib.parse, urllib.request

UA = "72HubRankings/1.0 (+https://github.com/tlock72/72-central; one-off check)"
ITF = "https://www.itftennis.com/tennis/api"
d = "/tmp/new"; subprocess.run(["git", "clone", "-q", "--depth", "1", "https://github.com/genaromoraes/itf-juniors-live-ranking.git", d], check=True)
o = "/tmp/old"; subprocess.run(["git", "clone", "-q", "--depth", "1", "https://github.com/genaromoraes/versaoantiga_itf-juniors-live-ranking.git", o], check=True)
sh = lambda c: subprocess.run(["bash", "-c", c], capture_output=True, text=True).stdout
print("===== rules file\n" + sh(f"cat {o}/pipeline/rules/itf-juniors-2026.json"))
print("===== draw/event/points calls in code (with context)\n" + sh(
    f"cd {d} && grep -rn -B3 -A12 'GetDrawsheet\\|GetEventFilters\\|GetRankingPoints' --include=*.mjs --include=*.js --include=*.py scripts pipeline lib 2>/dev/null | grep -v node_modules | head -150"))
print("===== old collector\n" + sh(f"grep -n -B2 -A10 'GetDrawsheet\\|GetEventFilters\\|GetCalendar' {o}/pipeline/lib/itf-weekly-collector.mjs | head -120"))
print("===== points tables / categories / qualifying / bonus mentions\n" + sh(
    f"cd {d} && grep -rn 'qualif\\|Qualif\\|bonus\\|JM\\b\\|Junior Finals\\|J-JM\\|18 years\\|age' --include=*.mjs scripts 2>/dev/null | head -40"))


def get(path, **q):
    time.sleep(4)
    req = urllib.request.Request(f"{ITF}{path}?{urllib.parse.urlencode(q)}", headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            b = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code} {e.read()[:300]}"
    if "_Incapsula_Resource" in b:
        raise SystemExit("ITF bot check - stopping")
    return b


cal = json.loads(get("/TournamentApi/GetCalendar", circuitCode="JT", searchString="", skip=0, take=100, nationCodes="", zoneCodes="",
                     dateFrom="2024-03-01", dateTo="2024-03-31", indoorOutdoor="", categories="", isOrderAscending="true", orderField="startDate", surfaceCodes=""))
print("===== calendar March 2024:", cal.get("totalItems"), "events; first:", json.dumps((cal.get("items") or [None])[0])[:900])
print("categories:", sorted({t.get("category") for t in cal.get("items") or []}))
key = next((t["tournamentKey"] for t in cal.get("items") or [] if t.get("category") == "J300"), (cal.get("items") or [{}])[0].get("tournamentKey"))
print("tournament:", key)
ef = get("/TournamentApi/GetEventFilters", tournamentKey=key)
print("===== event filters:", ef[:1500])
print("PROBE_DONE_SETUP")
