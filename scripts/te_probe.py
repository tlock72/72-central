"""One-off: see where Tennis Europe publishes entry/acceptance lists for coming events (read-only, prints to the log)."""
import html, json, re, sys, time
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


evs = [e for e in s["events"] if e["tour"] == "te" and e["end"] >= t.isoformat() and e["start"] <= (t + timedelta(days=28)).isoformat()]
mine = {pid.upper(): rid for rid, pid in json.load(open("te.json"))["profiles"].items() if ":" not in rid}
cat = next(e for e in evs if "E21AD649" in e["link"])
b = TE.fetch("/sport/acceptancelist.aspx?id=" + cat["link"].split("id=")[-1])
i = b.find("Select event")
print("SELECT RAW:", b[i - 200:i + 1500])
for word in ("Qualifying (", "Withdrawn", "Alternate", "Main ("):
    j = b.find(word)
    print(f"RAW around {word!r}:", b[max(0, j - 700):j + 500] if j >= 0 else "not found")
opts = re.findall(r'<option[^>]*value="([^"]*)"[^>]*>([^<]*)</option>', b[i:i + 3000])
print("options:", opts)
links = sorted(set(re.findall(r'href="([^"]*acceptancelist[^"]*)"', b, re.I)))
print("acceptance links:", links)

print("\n== SCAN", len(evs), "events")
for e in sorted(evs, key=lambda e: e["start"]):
    tid = e["link"].split("id=")[-1]
    try:
        b = TE.fetch(f"/sport/acceptancelist.aspx?id={tid}")
    except Exception as x:
        print(e["start"], e["name"], "FAILED", x)
        continue
    i = b.find("Select event")
    evlinks = sorted(set(l for l in re.findall(r'href="([^"]*acceptancelist[^"]*)"', b[i:i + 5000], re.I) if "event=" in l.lower()))
    opts = re.findall(r'<option[^>]*value="([^"]*)"', b[i:i + 3000])
    pages = [b]
    for l in evlinks[1:]:
        try:
            pages.append(TE.fetch(html.unescape(l)))
        except Exception as x:
            print("   sub-event failed", l, x)
    hit = []
    for pb in pages:
        for g in re.findall(r"/player-profile/([0-9A-Fa-f-]{36})", pb):
            if g.upper() in mine:
                hit.append(mine[g.upper()])
    state = "NOT YET" if "not yet available" in b else ("0 entries" if re.search(r">\s*0\s*</[^>]*>\s*Active entries|\b0 Active entries", re.sub("<[^>]+>", " ", b)) else "out")
    print(e["start"], e["name"], e.get("ages"), state, "sub-events", len(evlinks), "opts", opts[:6], "72:", sorted(set(hit)))
