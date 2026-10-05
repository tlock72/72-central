"""Temporary probe 2 (deleted after use)."""
import json, re, sys, time, urllib.parse, urllib.request
sys.path.insert(0, "scripts")
UA = {"User-Agent": "72HubRankings/1.0 (+https://github.com/tlock72/72-central; calendar check)", "Accept": "application/json,text/html"}
def get(u, h=UA):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=h), timeout=40) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return getattr(e, "code", "ERR"), str(e)[:150]
def show(lbl, u, n=700):
    st, b = get(u); print(f"\n===== {lbl} -> {st} {len(b)}\n{u}\n{b[:n]}"); time.sleep(1); return st, b
st, b = get("https://www.tennisexplorer.com/calendar/atp-men/2026/")
trs = re.findall(r"<tr[^>]*>.*?</tr>", b, re.S)
print("TE rows", len(trs))
for r in [r for r in trs if "Shanghai" in r or "Villena" in r or "Vienna" in r or "Basel" in r or "Brest" in r or "Davis" in r][:6]:
    print("RAW", re.sub(r"\s+", " ", r)[:1500])
print("CLASSES", sorted(set(re.findall(r'class="([^"]+)"', b)))[:120])
st, b = get("https://www.tennisexplorer.com/calendar/wta-women/2026/")
print("TE WTA", st, len(b))
st, b = get("https://www.tennisexplorer.com/calendar/itf-men/2026/"); print("TE ITF men", st, len(b))
W = "https://api.wtatennis.com/tennis"
for ep in ("players", "entries", "entrylist", "playerlist", "player-list", "acceptance"):
    show("WTA " + ep, f"{W}/tournaments/1075/2026/{ep}", 400)
show("WTA tournament", f"{W}/tournaments/1075/2026", 1500)
for u in ("https://www.protennislive.com/posting/2026/5014/mds.pdf", "https://www.atptour.com/en/scores/current/shanghai/5014/draws",
          "https://www.tennisexplorer.com/shanghai/2026/atp-men/"):
    st, b = get(u); print("\n=====", u, st, len(b)); 
    if "tennisexplorer" in u and st == 200: print(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", b[b.find("<h1"):b.find("<h1")+1500])))
import te_matches as T
T.consent()
h = T.fetch("/find/tournament?StartDate=2026-10-05&EndDate=2026-12-31")
for f in re.findall(r"<form[^>]*>", h): print("FORM", f[:300])
print("NAMES", sorted(set(re.findall(r'name="([^"]+)"', h)))[:80])
print("DATAURL", sorted(set(re.findall(r'data-(?:url|href|action)="([^"]+)"', h)))[:40])
i = h.find("Load more"); print("LOADMORE", re.sub(r"\s+", " ", h[i-1500:i+200]))
for m in re.findall(r'<li[^>]*class="[^"]*list__item[^"]*"[^>]*>(.*?)</li>', h, re.S)[:5]:
    print("ITEM", re.sub(r"\s+", " ", m)[:1200])
print("HREFS", sorted(set(re.findall(r'href="(/(?:sport/)?tournament[^"]*)"', h)))[:15])
h = T.fetch(f"/player-profile/{T.KNOWN['momot']}/tournaments")
for m in re.findall(r'<li[^>]*class="[^"]*list__item[^"]*"[^>]*>(.*?)</li>', h, re.S)[:3]:
    print("PITEM", re.sub(r"\s+", " ", m)[:1500])
