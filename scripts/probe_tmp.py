"""Temporary probe of free tournament-calendar and entry-list sources (deleted after use)."""
import json, re, sys, time, urllib.parse, urllib.request
sys.path.insert(0, "scripts")
UA = {"User-Agent": "72HubRankings/1.0 (+https://github.com/tlock72/72-central; calendar check)", "Accept": "application/json,text/html"}
def get(u, h=UA):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=h), timeout=40) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return getattr(e, "code", "ERR"), str(e)[:150]
def show(lbl, u, n=900):
    st, b = get(u); print(f"\n===== {lbl} -> {st} {len(b)}\n{u}\n{b[:n]}"); time.sleep(2); return st, b
I = "https://www.itftennis.com/tennis/api"
keys = {}
for c in ("JT", "MT", "WT"):
    q = dict(circuitCode=c, searchString="", skip=0, take=3, nationCodes="", zoneCodes="", dateFrom="2026-10-05", dateTo="2026-12-31",
             indoorOutdoor="", categories="", isOrderAscending="true", orderField="startDate", surfaceCodes="")
    st, b = show("ITF calendar " + c, f"{I}/TournamentApi/GetCalendar?" + urllib.parse.urlencode(q), 2500)
    try:
        j = json.loads(b); keys[c] = j["items"][0]["tournamentKey"]; print("TOTAL", j.get("totalItems"))
    except Exception as e: print("parse", e)
for c, k in keys.items():
    for ep in ("GetAcceptanceList", "GetEntryList", "GetPlayerList", "GetTournamentAcceptanceList", "GetEventFilters"):
        show(f"ITF {ep} {c}", f"{I}/TournamentApi/{ep}?tournamentKey={k}&circuitCode={c}", 600)
W = "https://api.wtatennis.com/tennis"
show("WTA tournaments A", f"{W}/tournaments/?page=0&pageSize=5&excludeLevels=ITF&from=2026-10-05&to=2026-12-31", 2500)
show("WTA tournaments B", f"{W}/tournaments/calendar?from=2026-10-05&to=2026-12-31", 1500)
show("TE ATP calendar", "https://www.tennisexplorer.com/calendar/atp-men/2026/", 300)
st, b = get("https://www.tennisexplorer.com/calendar/atp-men/2026/")
if st == 200:
    rows = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", r)) for r in re.findall(r"<tr[^>]*>(.*?)</tr>", b, re.S)]
    rows = [r for r in rows if "2026" in r or "." in r][:5] + [r for r in rows if "Oct" in r or "10." in r][:15]
    for r in rows: print("  ROW", r[:300])
    print("  links", re.findall(r'href="(/[a-z-]+/2026/atp-men/)"', b)[:5])
show("ATP calendar json", "https://www.atptour.com/en/-/tournaments/calendar/tour", 300)
show("Tennis Europe calendar", "https://www.tenniseurope.org/calendar", 600)
import te_matches as T
try:
    T.consent()
    h = T.fetch(f"/player-profile/{T.KNOWN['momot']}/tournaments")
    print("\n===== TE player tournaments", len(h))
    for m in re.findall(r'<h4[^>]*>(.*?)</h4>', h, re.S)[:12]: print("  H4", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m))[:200])
    i = h.find("Upcoming"); print("  UPCOMING idx", i, re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h[i:i+1500])) if i >= 0 else "")
    st, f = 0, T.fetch("/find/tournament?StartDate=2026-10-05&EndDate=2026-12-31&page=1")
    print("\n===== TE find tournaments", len(f)); print(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", f))[:2500])
except Exception as e:
    print("TE error", e)
