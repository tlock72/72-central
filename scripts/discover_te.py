"""One-off look at Tennis Europe's ranking pages (read only, a handful of requests)."""
import re, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import te_matches as TE
from bs4 import BeautifulSoup

TE.consent()
page = TE.fetch("/ranking/ranking.aspx?id=54125")
soup = BeautifulSoup(page, "html.parser")
for a in soup.find_all("a", href=True):
    if a.get_text(strip=True) == "More" or "category" in a["href"].lower():
        print("LINK", a["href"], "|", a.find_previous(["th", "td", "h3", "h4"]).get_text(" ", strip=True)[:60] if a.find_previous(["th","td"]) else "")
for th in soup.find_all(["th", "h3", "h4", "caption"]):
    t = th.get_text(" ", strip=True)
    if "Under" in t: print("HEAD", t, th.find("a")["href"] if th.find("a") else "")
cats = [a["href"] for a in soup.find_all("a", href=True) if a.get_text(strip=True) == "More"]
u14 = [h for h in cats]
print("MORE", u14)
for h in u14[:4]:
    print(h)
for h in u14[2:3] or u14[:1]:
    url = h if h.startswith("/") else "/ranking/" + h
    p = TE.fetch(url.replace("&amp;", "&"))
    s = BeautifulSoup(p, "html.parser")
    print("\n=====", url, s.title.get_text(strip=True) if s.title else None)
    print("TEXT", s.get_text(" ", strip=True)[:600])
    t = s.find("table", class_="ruler")
    rows = t.find_all("tr") if t else []
    print("ROWS", len(rows))
    for tr in rows[:6] + rows[-3:]:
        print("  ROW", [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])][:12])
    if len(rows) > 3: print("  RAW", str(rows[3])[:1500])
    print("PAGING", sorted(set(a["href"] for a in s.find_all("a", href=True) if re.search(r"[?&]p=\d", a["href"])))[:15])
    print("PAGER", [x.get_text(" ", strip=True) for x in s.select(".pagination, .page_navigation, .paging")][:3])
    # same category, a past week
    m = re.search(r"id=(\d+)", url)
    old = url.replace(m.group(0), "id=53991")
    p2 = TE.fetch(old.replace("&amp;", "&"))
    s2 = BeautifulSoup(p2, "html.parser")
    t2 = s2.find("table", class_="ruler")
    print("\n===== PAST", old, s2.get_text(" ", strip=True)[:300])
    for tr in (t2.find_all("tr") if t2 else [])[:5]:
        print("  ROW", [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])][:12])
