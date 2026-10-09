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
import gzip, html, json, os, re, sys, unicodedata, urllib.request, zlib
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
# (name shown on the site, feed addresses tried in order). All free and public; tennis sections only.
# ESPN (empty reply) and Eurosport (no feed) were tried in October 2026 and don't serve GitHub.
FEEDS = [
    ("BBC Sport", ["https://feeds.bbci.co.uk/sport/tennis/rss.xml"]),
    ("The Guardian", ["https://www.theguardian.com/sport/tennis/rss"]),
    ("Sky Sports", ["https://www.skysports.com/rss/12110"]),
    ("The Independent", ["https://www.independent.co.uk/sport/tennis/rss"]),
    ("The Telegraph", ["https://www.telegraph.co.uk/tennis/rss.xml"]),
    ("Tennis Majors", ["https://www.tennismajors.com/feed"]),
    ("Tennis365", ["https://www.tennis365.com/feed"]),
    ("Ubitennis", ["https://www.ubitennis.net/feed/"]),
]
# outlets that only cover tennis: everything they publish is kept
TENNIS_ONLY = {"Tennis Majors", "Tennis365", "Ubitennis"}
# from the others, a headline must be about tennis: one of these words, an "… Open", a ranked player's surname,
#   or a 72 player / prospect named in it or its summary (their tennis feeds also carry general sport pieces)
TENNIS = set("""tennis atp wta itf wimbledon slam roland garros masters challenger davis billie racket racquet
lta usta seed seeded seeds tiebreak tie break""".split())
STOP = set("""a an the and or but of to in on at for from by with as is are was were be been it its his her their
this that these those after before over under into out up down off about against v vs win wins won beat beats
beaten loses lost lose says said say set sets match matches open tennis first second third final finals semi
semifinal quarterfinal round title titles how why what who when where will can could would should has have had
not no yes new more most than then them they she he him we our you your all just still back year years day week
live latest update updates report reaction""".split())


def norm(s):
    s = re.sub(r"[\u2019\u2018'`]", " ", s or "")  # "Svitolina’s" -> "svitolina s", so names still match
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()
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
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
                                               "Accept": "application/rss+xml, application/xml, text/xml, */*",
                                               "Accept-Encoding": "gzip, deflate"})
    with urllib.request.urlopen(req, timeout=25) as r:
        raw, enc = r.read(), (r.headers.get("Content-Encoding") or "").lower()
    if enc == "gzip" or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    elif enc == "deflate":
        raw = zlib.decompress(raw, -zlib.MAX_WBITS)
    return raw.lstrip(b"\xef\xbb\xbf \r\n\t")


def image(el, f):
    """The story's picture: media:thumbnail / media:content / an image enclosure (the widest up to 800 px),
    else the first <img> in the summary or full text. Only https addresses are kept."""
    best, bw = None, -1
    for ch in el.iter():
        k, url = ch.tag.split("}")[-1], ch.get("url") or ""
        typ, med = ch.get("type") or "", ch.get("medium") or ""
        if not url.startswith("https://"):
            continue
        if k == "thumbnail" or (k in ("content", "enclosure") and (typ.startswith("image") or med == "image"
                                                                   or re.search(r"\.(jpe?g|png|webp)(\?|$)", url, re.I))):
            try:
                w = int(ch.get("width") or 0)
            except ValueError:
                w = 0
            if (w <= 800 and w > bw) or best is None:
                best, bw = url, w
    if not best:
        m = re.search(r"<img[^>]+src=[\"'](https://[^\"']+)", html.unescape(f.get("encoded") or "") + html.unescape(f.get("description") or ""))
        best = m and m.group(1)
    if best:
        best = re.sub(r"/ace/standard/\d+/", "/ace/standard/480/", html.unescape(best))  # BBC: a sharper size than the 240 px thumbnail
    return best or ""


def og_image(url):
    """The share picture an article page names for itself (<meta property="og:image">), https only, else ""."""
    try:
        page = fetch(url)[:300000].decode("utf-8", "ignore")
        for m in re.finditer(r"<meta\b[^>]*>", page, re.I):
            tag = m.group(0)
            if re.search(r"""(property|name)=["'](og:image|twitter:image)["']""", tag, re.I):
                c = re.search(r"""content=["'](https://[^"']+)""", tag, re.I)
                if c:
                    return html.unescape(c.group(1))
    except Exception as e:
        print("no picture from", url, e)
    return ""


def items(raw):
    """RSS <item> or Atom <entry> -> (title, link, summary, time, picture)."""
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
            sm = re.sub(r"\s*The post .* appeared first on .*$", "", text(f.get("description") or f.get("summary")))  # WordPress tag line
            out.append((t, u, sm[:240], d, image(el, f)))
    return out


def words(t):
    return {w for w in norm(t).split() if len(w) >= 3 and w not in STOP and not w.isdigit()}


def main():
    try:
        old = json.load(open(OUT))
    except Exception:
        old = {}
    sources = {k: v for k, v in (old.get("sources") or {}).items() if k in dict(FEEDS)}  # outlets no longer read drop out
    names72 = [(rid, norm(n)) for rid, (n, _) in ROSTER.items()]
    try:
        corner = json.load(open("corner.json"))
        scouts = [(p["name"], norm(p["name"])) for p in (corner.get("players") or {}).values() if p.get("name")]
        removed = {norm(n) for n in corner.get("removed") or []}
        scouts = [x for x in scouts if x[1] not in removed]
    except Exception:
        scouts = []

    # surnames of the ranked ATP/WTA top 500 (scouting.json): the "who" words used to match stories across outlets
    pros = set()
    try:
        sq = json.load(open("scouting.json"))
        for t in ("atp", "wta"):
            for row in (sq.get(t) or {}).get("players") or []:
                w = norm(row[1]).split()
                if row[0] <= 500 and w and len(w[-1]) >= 4 and w[-1] not in STOP:
                    pros.add(w[-1])
    except Exception:
        pass
    pros |= {norm(n).split()[-1] for n, _ in ROSTER.values()}

    got = []
    for name, urls in FEEDS:
        errs = []
        for url in urls:
            try:
                its = items(fetch(url))
                if not its:
                    raise ValueError("no headlines in the feed")
                sources[name] = {"ok": TODAY, "n": len(its)}
                got += [(name,) + it for it in its]
                print(f"{name}: {len(its)} headlines ({url})")
                break
            except Exception as e:
                errs.append(f"{url}: {e}")
        else:
            sources.setdefault(name, {})["err"] = "; ".join(errs)[:300]
            sources[name]["n"] = 0
            print(f"{name}: couldn't be read ({'; '.join(errs)})")

    # one copy per link, newest first
    seen, rows = set(), []
    for s, t, u, d, at, img in sorted(got, key=lambda x: x[4], reverse=True):
        if u in seen or at > NOW + timedelta(hours=1) or NOW - at > timedelta(hours=KEEP_72_H):
            continue
        seen.add(u)
        blob = norm(t + " " + d)
        tw = set(norm(t).split())
        p72 = [rid for rid, n in names72 if n in blob]
        sc = [n for n, k in scouts if k in blob]
        if not (s in TENNIS_ONLY or tw & TENNIS or tw & pros or re.search(r"\b[A-Z][a-z]+ Open\b", t) or p72 or sc):
            print("not tennis, left out:", t)
            continue
        rows.append({"t": t, "u": u, "s": s, "d": d, "at": at, "img": img,
                     "p72": p72, "sc": sc, "w": words(t), "who": words(t) & pros})

    # group the same story across outlets (within 36 hours of each other):
    #   the same two ranked players in the headline (e.g. "Hurkacz defeats Djokovic" / "Djokovic suffers Hurkacz loss"),
    #   or one ranked player plus 3+ key words in common, or 3+ key words that are most of the shorter headline
    def same(a, r):
        common = len(a["w"] & r["w"])
        who = len(a["who"] & r["who"])
        return (who >= 2 or (who >= 1 and common >= 3)
                or (common >= 3 and common >= 0.6 * min(len(a["w"]), len(r["w"]))))
    groups = []
    for r in rows:
        for g in groups:
            if (r["s"] not in {x["s"] for x in g} and abs((g[0]["at"] - r["at"]).total_seconds()) < 36 * 3600
                    and same(g[0], r)):
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
                    "img": next((x["img"] for x in g if x["img"]), ""),  # the lead's picture, else another outlet's
                    "at": lead["at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "also": [{"s": x["s"], "u": x["u"]} for x in g[1:]],
                    "p72": p72, "sc": sc, "score": round(n - age / 24, 2)})
    out.sort(key=lambda x: (-x["score"], [-ord(c) for c in x["at"]]))
    top = [x for x in out if not (x["p72"] or x["sc"])][:MAX_TOP]
    keep = [x for x in out if x["p72"] or x["sc"]] + top
    keep.sort(key=lambda x: (-x["score"], [-ord(c) for c in x["at"]]))

    # a story whose feed has no picture: the article page's own share picture (og:image), read once per link
    #   (pics remembers what each link gave, "" = none, so a page is never read twice); at most 25 pages a run
    pics, fetched = old.get("pics") or {}, 0
    for x in keep:
        if x["img"]:
            continue
        if x["u"] not in pics and fetched < 25:
            fetched += 1
            pics[x["u"]] = og_image(x["u"])
        x["img"] = pics.get(x["u"]) or ""
    pics = {u: pics[u] for u in {x["u"] for x in keep} if u in pics}

    new = {"updated": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "items": keep, "sources": sources, "pics": pics}
    if old.get("items") == keep and old.get("sources") == sources and old.get("pics") == pics:
        print("No new headlines")
        return
    json.dump(new, open(OUT, "w"), ensure_ascii=False, indent=0)
    print(f"Saved {len(keep)} stories ({sum(1 for x in keep if x['p72'])} on 72 players)")


if __name__ == "__main__":
    main()
