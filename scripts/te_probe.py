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


def text(b):
    m = re.search(r'<div class="page-content-start.*', b, re.S)
    b = re.sub(r"<script.*?</script>", " ", m.group(0) if m else b, flags=re.S)
    return re.sub(r"\s+", " ", re.sub("<[^>]+>", " ", b))


evs = sorted(evs, key=lambda e: e["start"])
pick = evs[:3] + evs[len(evs) // 2:len(evs) // 2 + 2] + evs[-2:]
for e in pick:
    tid = e["link"].split("id=")[-1]
    print("\n==", e["name"], e["start"], e["cat"], e.get("ages"), tid)
    try:
        b = TE.fetch(f"/sport/acceptancelist.aspx?id={tid}")
    except Exception as x:
        print("  FAILED", x)
        continue
    print("  chars", len(b), "profile links", len(re.findall(r"/player-profile/", b)), "player links", len(re.findall(r'href="[^"]*player[^"]*"', b, re.I)))
    print("  sample links:", sorted(set(re.findall(r'href="([^"]*(?:player|accept|event)[^"]*)"', b, re.I)))[:15])
    print("  ajax:", sorted(set(re.findall(r"['\"](/[^'\"]*(?:Accept|accept|Players|Entr)[^'\"]*)['\"]", b)))[:15])
    t = text(b)
    i = t.find("Acceptance list")
    print("  text:", t[max(0, i - 100):i + 2500])
    if e is pick[0]:
        i = b.find("Acceptance")
        print("  RAW:", b[b.find("<table") if "<table" in b else i: (b.find("<table") if "<table" in b else i) + 3000])
