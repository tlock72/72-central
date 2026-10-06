"""One-off check of past Tennis Europe ranking pages (reads only, saves nothing)."""
import os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import te_matches as TE
import prospects as P


def flat(page):
    page = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S)
    return re.sub(r"\s*\|\s*(\|\s*)+", " | ", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", page)))


TE.consent()
for path in ("/ranking/player.aspx?id=54125&player=5583629", "/ranking/player.aspx?id=53991&player=5583629",
             "/ranking/player.aspx?id=52562&player=5583629"):
    page = TE.fetch(path)
    t = flat(page)
    i = t.find("Ranking of")
    print(f"\n===== {path}\n", t[max(0, i - 400):i + 900])
    m = re.search(r"Ranking of.*?</table>", page, re.S)
    print("RAW:", re.sub(r"\s+", " ", m[0])[:2500] if m else None)
    print("parsed:", P.te_past(path.split("id=")[1].split("&")[0], "5583629", "Giulia Luchetti"))
# the ranking list page for a past week, to find how it links to each player
page = TE.fetch("/ranking/category.aspx?id=53991&category=526")
print("\n===== past week category page\n", flat(page)[:1500])
print("player links:", re.findall(r'href="[^"]*player\.aspx\?id=\d+&(?:amp;)?player=\d+"', page)[:5])
i = page.find("Luchetti")
print("Luchetti on page:", re.sub(r"\s+", " ", page[max(0, i - 600):i + 100]) if i >= 0 else "not on first page")
