"""One-off check: can past Tennis Europe ranking weeks be read for one player? Prints what the site returns."""
import os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import te_matches as TE
import prospects as P

TE_ID = "2F65EB7D-F034-4088-A2F5-86292F475429"  # Giulia Luchetti (TE U14 #8, Race U14 #6)


def flat(page):
    page = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S)
    return re.sub(r"\s*\|\s*(\|\s*)+", " | ", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", page)))


def show(path, n=3500):
    try:
        page = TE.fetch(path)
    except Exception as e:
        print("\n=====", path, "failed:", e); return ""
    print(f"\n===== {path}: {len(page)} chars")
    t = flat(page)
    i = t.find("Category")
    print(t[max(0, i - 800):i + n] if i >= 0 else t[:n])
    print("links:", sorted(set(re.findall(r'href="([^"]*(?:player\.aspx|category\.aspx|week)[^"]*)"', page, flags=re.I)))[:30])
    sel = re.search(r"<select[^>]*dlPublication.*?</select>", page, flags=re.S)
    if sel:
        print("weeks:", re.findall(r'value="(\d+)"[^>]*>([^<]+)<', sel[0])[:60])
    return page


TE.consent()
# 1) what the site reads today (which table: Tennis Europe Ranking or the Race?)
page = TE.fetch(f"/player-profile/{TE_ID}/ranking")
for tbl in re.findall(r"<table.*?</table>", page, flags=re.S):
    print("\n----- table:", flat(tbl)[:400])
print("\nsite reads:", P.te_ranking(TE_ID))

# 2) the per-week ranking pages linked from the profile
links = sorted(set(re.findall(r'href="(/ranking/player\.aspx\?id=\d+&(?:amp;)?player=\d+)"', page)))
print("profile links:", links)
weeks = {}
for l in links:
    p = show(l.replace("&amp;", "&"))
    sel = re.search(r"<select[^>]*dlPublication.*?</select>", p, flags=re.S)
    if sel:
        weeks[l] = re.findall(r'value="(\d+)"[^>]*>([^<]+)<', sel[0])

# 3) the same player in a past week (about 3 and 12 months ago), using that ranking's own week list
for l, ws in weeks.items():
    pid = re.search(r"player=(\d+)", l)[1]
    for want in ("28-2026", "41-2025"):
        hit = next((v for v, w in ws if w.strip() == want), None)
        if hit:
            show(f"/ranking/player.aspx?id={hit}&player={pid}", 1500)
