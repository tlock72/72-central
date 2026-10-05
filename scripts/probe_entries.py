"""One-off (round 2): look inside the entry-list sources that GitHub Actions can reach."""
import re, html, json, sys, urllib.request
sys.path.insert(0, "scripts")
from update import ROSTER

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
MEN = [v[0] for v in ROSTER.values() if v[1] == "atp"]

def get(u):
    r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA, "Accept": "*/*"}), timeout=40)
    return r.read().decode("utf-8", "replace")

def text(t):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"(?s)<(script|style).*?</\1>|<[^>]+>", " ", t)))

def hits(t, label):
    low = t.lower()
    found = [n for n in MEN if n.split()[-1].lower() in low]
    print(f"[{label}] 72 surnames found:", found)

def show(u, n=2500, raw=False):
    print("\n" + "=" * 100 + "\n" + u)
    try:
        t = get(u)
    except Exception as e:
        print("FAILED:", repr(e)[:300]); return ""
    print("bytes", len(t))
    print((t if raw else text(t))[:n])
    return t

# 1. live-tennis.eu schedule (one page, top ~1000 players and their next events)
t = show("https://live-tennis.eu/en/atp-schedule", 1500)
if t:
    rows = re.findall(r"(?s)<tr[^>]*>(.*?)</tr>", t)
    print("rows:", len(rows))
    for r in rows:
        if any(n.split()[-1] in r for n in MEN):
            print("  ROW:", text(r)[:400])
    hits(t, "live-tennis")
show("https://live-tennis.eu/robots.txt", 800, raw=True)

# 2. Tick Tock Tennis: data is embedded in the page script
for u in ["https://www.ticktocktennis.com/atp", "https://entries.ticktocktennis.com/players.html"]:
    t = show(u, 300)
    if t:
        for k in ["mainPdf", "qualPdf", "protennislive", "const ", "fetch(", ".json"]:
            for m in list(re.finditer(re.escape(k), t))[:4]:
                print(f"  ...{k}...", t[max(0, m.start() - 200): m.start() + 400].replace("\n", " "))
        print("pdf urls:", sorted(set(re.findall(r"https?://[^\"' ]+\.pdf", t)))[:40])
        hits(t, u)

# 3. Darts Rankings: a current Challenger page and the schedules page
for u in ["https://www.dartsrankings.com/tennis/maia", "https://www.dartsrankings.com/tennis/schedules/"]:
    t = show(u, 2500)
    if t: hits(t, u)

# 4. Spazio Tennis: WordPress API, to find each week's entry-list post automatically
show("https://www.spaziotennis.com/wp-json/wp/v2/categories?search=entry&per_page=20", 1500, raw=True)
t = show("https://www.spaziotennis.com/wp-json/wp/v2/posts?search=entry%20list%20challenger&per_page=5&_fields=id,date,modified,link,title", 2500, raw=True)
t = show("https://www.spaziotennis.com/trn/ent/entry-list-atp-challenger-2026-week-42-lisbona-guangzhou-fort-worth-cali-firenze/143713", 300)
if t: hits(t, "spazio wk42")
show("https://www.spaziotennis.com/robots.txt", 800, raw=True)

# 5. Tennis Teen latest ATP post
t = show("https://www.tennisteen.it/entry-list/atp.html", 200)
if t:
    links = sorted(set(re.findall(r'href="(/entry-list/atp/[^"]+)"', t)))
    print(links[:10])
    if links:
        t2 = show("https://www.tennisteen.it" + links[-1], 2500)
        if t2:
            hits(t2, "tennisteen")
            print("pdfs:", sorted(set(re.findall(r'href="([^"]+\.pdf)"', t2)))[:20])
