"""
72 Central - News (runs every hour in its own workflow, news.yml, no Claude, no paid services).

Builds news.json: the top tennis headlines from well-known outlets, read from their free public RSS feeds.
Only the headline, a short summary, the time and the link are kept; the site links out to the outlet's own
article and never copies the article itself.

How "important" is decided (no guessing, no AI):
  - the same story covered by several outlets is grouped (headlines sharing most of their key words),
    and a story more outlets ran ranks higher; newer beats older (a day's age costs about one outlet);
  - a headline or summary naming a 72 player (full name, any accents) is tagged with their roster id (p72),
    and one naming a Scouting Corner prospect (corner.json) is tagged too (sc), so the page can put them first.
A feed that can't be read keeps nothing from this run (its stories drop out once they are old anyway);
sources{name}.ok is the last UK date it was read, and report_gaps.py alerts a feed unreadable for 2 days.
"""
import html, json, math, os, re, sys, unicodedata, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(__file__))
from update import ROSTER  # roster id -> (name, "atp" / "wta")

OUT = "news.json"
UK = ZoneInfo("Europe/London")
NOW = datetime.now(timezone.utc)
TODAY = NOW.astimezone(UK).date().isoformat()
KEEP_H = 72          # top headlines: the last 3 days
KEEP_72_H = 24 * 7   # stories on 72 players or prospects: the last week
MAX_TOP = 40
# (name shown on the site, feed). All free and public; tennis sections only.
FEEDS = [
    ("BBC Sport", "https://feeds.bbci.co.uk/sport/tennis/rss.xml"),
    ("The Guardian", "https://www.theguardian.com/sport/tennis/rss"),
    ("ESPN", "https://www.espn.com/espn/rss/tennis/news"),
    ("Sky Sports", "https://www.skysports.com/rss/12110"),
    ("The Independent", "https://www.independent.co.uk/sport/tennis/rss"),
    ("Eurosport", "https://www.eurosport.com/tennis/rss.xml"),
    ("Tennis Majors", "https://www.tennismajors.com/feed"),
    ("Ubitennis", "https://www.ubitennis.net/feed/"),
]
STOP = set("""a an the and or but of to in on at for from by with as is are was were be been it its his her their
this that these those after before over under into out up down off about against v vs win wins won beat beats
beaten loses lost lose says said say set sets match matches open tennis first second third final finals semi
semifinal quarterfinal round title titles how why what who when where will can could would should has have had
not no yes new more most than then them they she he him we our you your all just still back year years day week
live latest update updates report reaction""".split())


def norm(s):
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()
    s = s.replace("ae", "a").replace("oe", "o").replace("ue", "u")
    return " " + re.sub(r"[^a-z0-9]+", " ", s).strip() + " "


def text(s):
    s = re.sub(r"<[^>]+>", " ", html.unescape(s or ""))
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def when(s):
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s.strip())
    except Exception:
        try:
            d = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (72 Central news reader)",
                                               "Accept": "application/rss+xml, application/xml, text/xml, */*"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def items(raw):
    """RSS <item> or Atom <entry> -> (title, link, summary, time)."""
    root = ET.fromstring(raw)
    out = []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        f = {}
        for ch in el:
            k = ch.tag.split("}")[-1]
            if k == "link" and ch.get("href"):
                f.setdefault("link", ch.get("href"))
            elif k not in f:
                f[k] = (ch.text or "").strip()
        t = text(f.get("title"))
        u = f.get("link") or f.get("guid") or ""
        d = when(f.get("pubDate") or f.get("published") or f.get("updated") or f.get("date"))
        if t and u.startswith("http") and d:
            out.append((t, u, text(f.get("description") or f.get("summary"))[:240], d))
    return out


def words(t):
    return {w for w in norm(t).split() if len(w) >= 3 and w not in STOP and not w.isdigit()}


def main():
    try:
        old = json.load(open(OUT))
    except Exception:
        old = {}
    sources = old.get("sources") or {}
    names72 = [(rid, norm(n)) for rid, (n, _) in ROSTER.items()]
    try:
        corner = json.load(open("corner.json"))
        scouts = [(p["name"], norm(p["name"])) for p in (corner.get("players") or {}).values() if p.get("name")]
        removed = {norm(n) for n in corner.get("removed") or []}
        scouts = [x for x in scouts if x[1] not in removed]
    except Exception:
        scouts = []

    got = []
    for name, url in FEEDS:
        try:
            its = items(fetch(url))
            if not its:
                raise ValueError("no headlines in the feed")
            sources[name] = {"ok": TODAY, "n": len(its)}
            got += [(name,) + it for it in its]
            print(f"{name}: {len(its)} headlines")
        except Exception as e:
            sources.setdefault(name, {})["err"] = str(e)[:120]
            sources[name]["n"] = 0
            print(f"{name}: couldn't be read ({e})")

    # one copy per link, newest first
    seen, rows = set(), []
    for s, t, u, d, at in sorted(got, key=lambda x: x[4], reverse=True):
        if u in seen or at > NOW + timedelta(hours=1) or NOW - at > timedelta(hours=KEEP_72_H):
            continue
        seen.add(u)
        blob = norm(t + " " + d)
        rows.append({"t": t, "u": u, "s": s, "d": d, "at": at,
                     "p72": [rid for rid, n in names72 if n in blob],
                     "sc": [n for n, k in scouts if k in blob], "w": words(t)})

    # group the same story across outlets: most of the shorter headline's key words in common (at least 3)
    groups = []
    for r in rows:
        for g in groups:
            a = g[0]["w"]
            common = len(a & r["w"])
            if common >= 3 and common >= 0.6 * min(len(a), len(r["w"])) and r["s"] not in {x["s"] for x in g}:
                g.append(r)
                break
        else:
            groups.append([r])

    out = []
    for g in groups:
        lead = g[0]  # the newest copy leads
        n = len({x["s"] for x in g})
        age = (NOW - max(x["at"] for x in g)).total_seconds() / 3600
        p72 = sorted({p for x in g for p in x["p72"]})
        sc = sorted({p for x in g for p in x["sc"]})
        if age > KEEP_H and not (p72 or sc):
            continue
        out.append({"t": lead["t"], "u": lead["u"], "s": lead["s"], "d": lead["d"],
                    "at": lead["at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "also": [{"s": x["s"], "u": x["u"]} for x in g[1:]],
                    "p72": p72, "sc": sc, "score": round(n - age / 24, 2)})
    out.sort(key=lambda x: (-x["score"], [-ord(c) for c in x["at"]]))
    top = [x for x in out if not (x["p72"] or x["sc"])][:MAX_TOP]
    keep = [x for x in out if x["p72"] or x["sc"]] + top
    keep.sort(key=lambda x: (-x["score"], [-ord(c) for c in x["at"]]))

    new = {"updated": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "items": keep, "sources": sources}
    if old.get("items") == keep and old.get("sources") == sources:
        print("No new headlines")
        return
    json.dump(new, open(OUT, "w"), ensure_ascii=False, indent=0)
    print(f"Saved {len(keep)} stories ({sum(1 for x in keep if x['p72'])} on 72 players)")


if __name__ == "__main__":
    main()
