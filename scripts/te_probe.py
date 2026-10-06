"""One-off: see where Tennis Europe publishes entry/acceptance lists for coming events (read-only, prints to the log)."""
import json, re, sys, time
from datetime import date, timedelta
sys.path.insert(0, "scripts")
import te_matches as TE

TE.consent()
s = json.load(open("schedule.json"))
t = date.today()
evs = [e for e in s["events"] if e["tour"] == "te" and e["start"] > t.isoformat() and e["start"] <= (t + timedelta(days=28)).isoformat()]
print(len(evs), "Tennis Europe events in the next 4 weeks")


def show(path, label):
    try:
        b = TE.fetch(path)
    except Exception as x:
        print(f"  {label}: FAILED {x}")
        return ""
    links = sorted(set(re.findall(r'href="([^"]+)"', b)))
    print(f"  {label}: {len(b)} chars, /player links: {sum('player' in l.lower() for l in links)}")
    return b


for e in sorted(evs, key=lambda e: e["start"])[:4]:
    tid = e["link"].split("id=")[-1]
    print("\n==", e["name"], e["start"], e["cat"], tid)
    b = show(f"/sport/tournament?id={tid}", "tournament page")
    for l in sorted(set(re.findall(r'href="([^"]+)"', b))):
        if tid.lower() in l.lower() or re.search(r"player|entr|accept|draw|event", l, re.I):
            print("    link:", l)
    for p in (f"/tournament/{tid}/players", f"/sport/players.aspx?id={tid}", f"/tournament/{tid}/events",
              f"/sport/tournament/players?id={tid}"):
        pb = show(p, p)
        if pb:
            names = re.findall(r'href="(/(?:tournament/[^"]*/)?player[^"]*)"[^>]*>(.*?)</a>', pb, re.S)
            print("    sample player links:", [(h, re.sub("<[^>]+>", "", n).strip()) for h, n in names[:6]])
            m = re.search(r"<main.*?</main>", pb, re.S)
            txt = re.sub(r"\s+", " ", re.sub("<[^>]+>", " ", m.group(0) if m else pb))
            print("    text:", txt[:1500])

print("\n== 72 junior profiles: tournaments listed (look for future dates)")
for rid, pid in json.load(open("te.json"))["profiles"].items():
    if ":" in rid:
        continue
    try:
        b = TE.fetch(f"/player-profile/{pid}/tournaments")
    except Exception as x:
        print(rid, "FAILED", x)
        continue
    rows = []
    for chunk in re.split(r'(?=<h4 class="media__title)', b)[1:]:
        a = re.search(r'title="([^"]*)"', chunk)
        d = re.findall(r'<time datetime="(\d{4}-\d{2}-\d{2})', chunk)
        rows.append((d[:1], a.group(1) if a else "?"))
    print(rid, rows[:4])
    tabs = sorted(set(l for l in re.findall(r'href="([^"]+)"', b) if pid.lower() in l.lower()))
    if rid == "qi":
        print("  profile tabs:", tabs)
