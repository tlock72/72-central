"""One-off look at Tennis Europe's ranking pages (read only, a handful of requests)."""
import re, sys, os, json, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import te_matches as TE
from bs4 import BeautifulSoup

def show(path, n=4000):
    page = TE.fetch(path)
    soup = BeautifulSoup(page, "html.parser")
    print(f"\n===== {path}\nTITLE:", soup.title.get_text(strip=True) if soup.title else None)
    for s in soup.find_all("select"):
        opts = [(o.get("value"), o.get_text(strip=True)) for o in s.find_all("option")]
        print("SELECT", s.get("name"), s.get("id"), len(opts), opts[:6])
    links = [(a["href"], a.get_text(" ", strip=True)) for a in soup.find_all("a", href=True) if "ranking" in a["href"].lower()]
    print("RANKING LINKS", len(links)); [print("  ", l) for l in links[:60]]
    for t in soup.find_all("table")[:3]:
        print("TABLE class", t.get("class"))
        for tr in t.find_all("tr")[:5]:
            print("  ROW", [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])])
        tr = t.find_all("tr")[1:2]
        if tr: print("  RAW", str(tr[0])[:1500])
    txt = soup.get_text(" ", strip=True)
    print("TEXT", txt[:n])
    return page

TE.consent()
page = show("/ranking/ranking.aspx?rid=79")
cats = re.findall(r'href="(/ranking/category\.aspx\?[^"]+)"', page)
print("CATS", cats[:20])
for c in cats[:2]:
    p = show(c.replace("&amp;", "&"), 1500)
    pl = re.findall(r'href="(/ranking/player\.aspx\?[^"]+)"', p)
    pages = sorted(set(re.findall(r'href="([^"]*category\.aspx[^"]*p=\d+[^"]*)"', p)))
    print("PAGING", pages[:10])
    if pl:
        show(pl[0].replace("&amp;", "&"), 2500)
        break
# ITF junior ranking list shape
req = urllib.request.Request("https://www.itftennis.com/tennis/api/PlayerRankApi/GetPlayerRankings?circuitCode=JT&playerTypeCode=B&ageCategoryCode=&juniorRankingType=itf&take=2&skip=0&isOrderAscending=true",
                             headers={"User-Agent": "72HubRankings/1.0", "Accept": "application/json"})
try:
    print("\n===== ITF", urllib.request.urlopen(req, timeout=30).read().decode()[:2500])
except Exception as e:
    print("ITF failed", e)
