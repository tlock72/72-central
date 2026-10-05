"""One-off: can GitHub Actions reach sites that publish ATP / Challenger entry lists?"""
import re, html, urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
URLS = [
    "https://entries.ticktocktennis.com/",
    "https://entries.ticktocktennis.com/robots.txt",
    "https://www.ticktocktennis.com/atp",
    "https://www.dartsrankings.com/tennis/",
    "https://www.dartsrankings.com/tennis/olbia",
    "https://www.dartsrankings.com/robots.txt",
    "https://www.spaziotennis.com/trn/ent/entry-list-atp-challenger-2026-week-41-olbia-jinan-roanne-maia-santa-cruz-catania/143312",
    "https://www.tennisteen.it/entry-list.html",
    "https://www.crushrushnews.com/atp-challenger-circuit-entry-lists/",
    "https://www.protennislive.com/posting/2026/5014/mds.pdf",
    "https://www.protennislive.com/posting/2026/5014/",
    "https://www.atptour.com/en/news/shanghai-2026-entry-list",
]

def get(u):
    r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA, "Accept": "*/*"}), timeout=30)
    return r.status, r.headers.get("Content-Type", ""), r.geturl(), r.read()

for u in URLS:
    print("\n" + "=" * 100 + "\n" + u)
    try:
        st, ct, final, b = get(u)
    except Exception as e:
        print("FAILED:", repr(e)[:300]); continue
    print("status", st, "| type", ct, "| bytes", len(b), "| final", final)
    if "pdf" in ct:
        print(b[:200]); continue
    t = b.decode("utf-8", "replace")
    if u.endswith("robots.txt"):
        print(t[:1500]); continue
    links = sorted(set(re.findall(r'href="([^"]+)"', t)))
    print("links:", len(links))
    for l in links[:120]:
        print("  ", l)
    js = sorted(set(re.findall(r'(?:src|href)="([^"]+\.(?:js|json)[^"]*)"', t)))
    print("scripts/json:", js[:30])
    txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"(?s)<(script|style).*?</\1>|<[^>]+>", " ", t)))
    print("text:", txt[:4000])
