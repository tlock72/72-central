"""One-off (round 3): raw page layout of live-tennis.eu and Tick Tock Tennis."""
import re, json, urllib.request
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=40).read().decode("utf-8", "replace")

t = get("https://live-tennis.eu/en/atp-schedule")
i = t.find('id="u868"')
print("TABLE START:\n", t[i - 300:i + 6000])
for n in ["Minaur", "Kym", "Ivanov", "Bonding", "Kuzuhara", "rzler", "Mackenzie"]:
    j = t.find(n)
    if j > 0:
        s = t.rfind("<tr", 0, j)
        print(f"\nROW {n}:\n", t[s:t.find("</tr>", j) + 5])
k = t.rfind("</table>", 0, len(t))
print("\nTABLE END / FOOTER:\n", t[t.rfind("<tr", 0, k) - 3000:k + 3000])

a = get("https://www.ticktocktennis.com/atp")
print("\n\nTICKTOCK atpData assignments:")
for m in re.finditer(r"atpData(\.\w+|\[[^\]]+\])?\s*=", a):
    print(m.start(), a[m.start():m.start() + 1500].replace("\n", " "))
print("\nscript srcs:", re.findall(r'<script[^>]*src="([^"]+)"', a))
j = a.find("Schwaerzler") if "Schwaerzler" in a else a.find("rzler")
print("\nAround Schwaerzler:", a[max(0, j - 1500): j + 300] if j > 0 else "not found")
for m in list(re.finditer(r"week\d\s*[:=]", a))[:12]:
    print("WEEK:", a[m.start():m.start() + 300].replace("\n", " "))

p = get("https://entries.ticktocktennis.com/players.html")
m = re.search(r"const data = (\{.*?\});\s*const weeks", p, re.S)
if m:
    d = json.loads(m.group(1))
    print("\nPLAYERS keys:", list(d.keys()), "weeks:", d.get("weeks"))
    for r in d.get("atp_players", [])[:3] + [r for r in d.get("atp_players", []) if any(x in r[1] for x in ["Kym", "Altmaier", "Schw", "Ivanov", "Buse"])]:
        print("  ", r)
    print("rows:", len(d.get("atp_players", [])))
