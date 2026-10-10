"""
72 Central - News (runs every hour in its own workflow, news.yml, no Claude, no paid services).

Builds news.json: the top tennis headlines from well-known outlets, read from their free public RSS feeds.
Only the headline, a short summary, the time and the link are kept; the site links out to the outlet's own
article and never copies the article itself.

How "important" is decided (no guessing, no AI):
  - business and tournament stories come first (topic(): investors, sponsors, broadcasters, the tours' and
    federations' decisions and people; the calendar, venues, entry lists), ranking BONUS outlets higher than match
    reports and kept for a week; they also come from sport-business outlets and Google News searches (BIZ_FEEDS),
    which only ever add tennis business / tournament stories;
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
KEEP_72_H = 24 * 7   # stories on 72 players or prospects, and business / tournament stories: the last week
MAX_TOP = 40         # match and player stories (business / tournament stories have their own 40)
BONUS = {"biz": 3, "ev": 2}  # business and tournament stories rank this many "outlets" higher than match reports
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
    # the business of sport: only their tennis business / tournament stories are kept (BIZ_FEEDS below)
    ("SportsPro", ["https://www.sportspromedia.com/feed/"]),
    ("Sportico", ["https://www.sportico.com/feed/"]),
    ("Front Office Sports", ["https://frontofficesports.com/feed/"]),
    # Google News searches (free, public RSS) for tennis business news from any outlet (Sports Business Journal,
    #   The Times, Reuters, the tours' own sites...). Each headline is shown under its own outlet's name.
    ("Google News", [
        "https://news.google.com/rss/search?hl=en-GB&gl=GB&ceid=GB:en&q=tennis+(sponsor+OR+sponsorship+OR+investment+OR+investor+OR+stake+OR+%22prize+money%22+OR+broadcast+OR+%22media+rights%22+OR+CEO+OR+acquisition+OR+partnership)+when:3d",
        "https://news.google.com/rss/search?hl=en-GB&gl=GB&ceid=GB:en&q=(ATP+OR+WTA+OR+ITF+OR+PTPA+OR+%22Tennis+Europe%22+OR+LTA+OR+USTA+OR+%22Tennis+Australia%22)+(calendar+OR+tournament+OR+licence+OR+sanction+OR+deal+OR+governance+OR+rules+OR+chairman+OR+CEO)+when:3d",
        "https://news.google.com/rss/search?hl=en-GB&gl=GB&ceid=GB:en&q=tennis+tournament+(venue+OR+%22new+event%22+OR+relocate+OR+upgrade+OR+%22wild+card%22+OR+%22entry+list%22+OR+host+OR+expansion)+when:3d",
    ]),
]
# "Google News" reads every address in its list (the others stop at the first that works)
SEARCHES = {"Google News"}
# outlets that only cover tennis: everything they publish is kept
TENNIS_ONLY = {"Tennis Majors", "Tennis365", "Ubitennis"}
# outlets covering every sport, or searches: a story is kept only if it is a business or tournament story (topic
#   below) and, from the outlets, clearly tennis (STRICT, in the headline or summary): no match reports or other sports
BIZ_FEEDS = {"SportsPro", "Sportico", "Front Office Sports"} | SEARCHES
STRICT = ["tennis", "atp", "wta", "itf", "wimbledon", "roland garros", "ptpa", "lta", "usta", "davis cup",
          "billie jean king cup", "australian open", "us open tennis", "laver cup"]
# when several outlets run a story, the best-known one leads (first in this list; outlets not listed come last,
#   then the newest copy) and the rest sit behind the "Other outlets" button. Names as the feeds / Google give them.
BEST = ["reuters", "bbc sport", "bbc", "the times", "the guardian", "financial times", "bloomberg", "associated press",
        "ap news", "the new york times", "the athletic", "sports business journal", "sportico", "sportspro",
        "sportspro media", "the telegraph", "the independent", "sky sports", "front office sports", "espn",
        "tennis majors", "wta tennis", "atp tour", "itf", "tennis.com", "ubitennis", "tennis365"]


def rank(o):
    o = o.lower()
    return BEST.index(o) if o in BEST else len(BEST)


# a search result from an outlet already read directly is left out (that outlet's own copy is used)
DIRECT = {"bbc", "bbc sport", "the guardian", "sky sports", "the independent", "the telegraph", "tennis majors",
          "tennis365", "ubitennis", "sportspro", "sportspro media", "sportico", "front office sports"}
# from the others, a headline must be about tennis: one of these words, an "… Open", a ranked player's surname,
#   or a 72 player / prospect named in it or its summary (their tennis feeds also carry general sport pieces)
TENNIS = set("""tennis atp wta itf wimbledon slam roland garros masters challenger davis billie racket racquet
lta usta seed seeded seeds tiebreak tie break
federer nadal sharapova serena navratilova agassi sampras mcenroe""".split())  # retired stars: no longer ranked, still in business news
STOP = set("""a an the and or but of to in on at for from by with as is are was were be been it its his her their
this that these those after before over under into out up down off about against v vs win wins won beat beats
beaten loses lost lose says said say set sets match matches open tennis first second third final finals semi
semifinal quarterfinal round title titles how why what who when where will can could would should has have had
not no yes new more most than then them they she he him we our you your all just still back year years day week
live latest update updates report reaction""".split())


# What a story is about, from its headline (and, for the clearest phrases, its summary). The business and
#   running of the game matters more to 72 than match reports, so these rank higher and are kept for a week:
#   "biz" = money, owners, investors, sponsors, broadcasters, the tours' and federations' decisions and people;
#   "ev"  = tournament info: the calendar, new or moved events, venues, dates, formats, entry lists, wild cards.
BIZ = set("""invest invests invested investing investment investments investor investors stake stakes takeover
acquire acquires acquired acquisition buyout merger merge sponsor sponsors sponsored sponsorship sponsorships
partner partners partnership partnerships deal deals agreement agreements contract broadcast broadcaster broadcasters
broadcasting streaming revenue revenues profit profits funding fund funds valuation billion owner owners
ownership licence license licences licenses sanction sanctions sanctioned ceo chairman chairwoman chair chief
executive executives president board boss bosses appoint appoints appointed appointment governance ptpa lawsuit
antitrust legal union pif commercial brand brands endorsement endorsements apparel betting gambling integrity itia
doping marketing media viewers viewership audience audiences tickets ticket attendance business industry economics
finance financial budget pension pensions welfare council regulation regulations rule rules reform reforms vote
voted ruling saudi strike boycott""".split())
EV = set("""calendar calendars venue venues relocate relocates relocated relocation upgrade upgraded upgrades
expansion expand expands expanded stadium roof dates wildcard wildcards exhibition hosts hosting hosted
host""".split())
BIZ_PH = ["prize money", "equal pay", "premium tour", "media rights", "tv rights", "chief executive",
          "governing body", "players association", "players council", "player council", "saudi arabia",
          "title sponsor", "sovereign wealth", "private equity", "tennis europe", "tennis federation"]
EV_PH = ["entry list", "draw date", "wild card", "new tournament", "new event", "combined event", "tournament director",
         "96 player", "draw size", "host city", "will host", "to host", "tournament will"]
EV_T = ["davis cup", "billie jean king cup", "united cup", "laver cup", "hopman cup", "next gen", "six kings"]  # headline only
NOISE = ["where to watch", "how to watch", "live stream", "watch live", "net worth", "ncaa", "college", "invitational",
         "university"]
# a match report: one of these in the headline keeps it a match story, whatever else it mentions (so do a player's
#   "ranking points and prize money after…" pieces and "On this day" history pieces such as "October 7, 1999: …")
PLAY = set("""beat beats beaten defeat defeats defeated stun stuns stunned crash crashes crashed reach reaches reached
advance advances advanced knock knocks knocked oust ousts ousted edge edges edged rout routs thrash thrashes down
downs overcome overcomes battle battles save saves survive survives withdraw withdraws retire retires rally rallies
cruise cruises sweep sweeps outlast outlasts dispatch dispatches eliminate eliminates exit""".split())


def topic(t, d):
    """ "biz", "ev" or "" (a match or player story), see BIZ above."""
    tw, tn, dn = set(norm(t).split()), norm(t), norm(d)
    if (tw & PLAY and not any(f" {p} " in tn for p in BIZ_PH)) or " ranking points " in tn or re.match(r"[A-Z][a-z]+ \d{1,2}, \d{4}:", t):
        return ""
    # where-to-watch guides, "net worth" pieces and US college tennis aren't the business of the game
    if any(f" {p} " in tn for p in NOISE):
        return ""
    if any(f" {p} " in tn for p in EV_PH + EV_T):
        return "ev"
    if tw & BIZ or any(f" {p} " in tn or f" {p} " in dn for p in BIZ_PH):
        return "biz"
    if tw & EV or any(f" {p} " in dn for p in EV_PH):
        return "ev"
    return ""


def pro_named(t, pros, fulls):
    """A ranked player named in a headline: first name + surname, or the surname on its own unless it is used as
    someone's first name there, i.e. straight after it comes another capitalised name ("Donald Trump" is not
    Matthew Donald; "Sinner wins" and "Alcaraz beats Sinner" are fine)."""
    if any(f in norm(t) for f in fulls):
        return True
    for m in re.finditer(r"[^\W\d_]+", t):
        nxt = t[m.end():m.end() + 2]
        if norm(m.group()).strip() in pros and not (nxt[:1] == " " and nxt[1:].isupper()):
            return True
    return False


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
    """RSS <item> or Atom <entry> -> (title, link, summary, time, picture, outlet named in <source> or "")."""
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
            src = text(f.get("source"))  # Google News: the outlet that ran it ("Title - Outlet"; its summary is just links)
            if src:
                t, sm = re.sub(r"(\s+[-\u2013|]\s+" + re.escape(src) + r")+$", "", t), ""  # "… | Gulf Times - Gulf Times"
            out.append((t, u, sm[:240], d, image(el, f), src))
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
    pros, names, fulls = set(), set(), set()  # names: every word of those players' full names (first names too)
    try:
        sq = json.load(open("scouting.json"))
        for t in ("atp", "wta"):
            for row in (sq.get(t) or {}).get("players") or []:
                w = norm(row[1]).split()
                if row[0] <= 500 and w and len(w[-1]) >= 4 and w[-1] not in STOP:
                    pros.add(w[-1])
                if row[0] <= 500:
                    names |= set(w)
                    if len(w) > 1:
                        fulls.add(f" {w[0]} {w[-1]} ")
    except Exception:
        pass
    pros |= {norm(n).split()[-1] for n, _ in ROSTER.values()}
    names |= pros | {w for n, _ in ROSTER.values() for w in norm(n).split()}

    got = []
    for name, urls in FEEDS:
        errs, n = [], 0
        for url in urls:
            try:
                its = items(fetch(url))
                if not its:
                    raise ValueError("no headlines in the feed")
                n += len(its)
                sources[name] = {"ok": TODAY, "n": n}
                got += [(name,) + it for it in its]
                print(f"{name}: {len(its)} headlines ({url})")
                if name not in SEARCHES:
                    break
            except Exception as e:
                errs.append(f"{url}: {e}")
        if not n:
            sources.setdefault(name, {})["err"] = "; ".join(errs)[:300]
            sources[name]["n"] = 0
            print(f"{name}: couldn't be read ({'; '.join(errs)})")

    # one copy per link, newest first
    seen, rows = set(), []
    for feed, t, u, d, at, img, src in sorted(got, key=lambda x: x[4], reverse=True):
        s = src or feed  # a search result is shown under the outlet that ran it
        if u in seen or (s, t) in seen or at > NOW + timedelta(hours=1) or NOW - at > timedelta(hours=KEEP_72_H):
            continue
        seen |= {u, (s, t)}
        blob = norm(t + " " + d)
        tw = set(norm(t).split())
        p72 = [rid for rid, n in names72 if n in blob]
        sc = [n for n, k in scouts if k in blob]
        k = topic(t, d)
        tennis = tw & TENNIS or pro_named(t, pros, fulls) or re.search(r"\b[A-Z][a-z]+ Open\b", t) or p72 or sc
        if feed in BIZ_FEEDS:
            # a search result's headline must look like tennis (as for the general outlets' feeds below)
            if (not k or not (tennis if feed in SEARCHES else any(f" {w} " in blob for w in STRICT))
                    or (src and s.lower() in DIRECT)
                    or len(re.sub(r"[^A-Za-z]", "", t)) < 0.6 * len(t.replace(" ", ""))):  # not English
                continue
        elif not (s in TENNIS_ONLY or tennis):
            print("not tennis, left out:", t)
            continue
        rows.append({"t": t, "u": u, "s": s, "d": d, "at": at, "img": img, "k": k,
                     "p72": p72, "sc": sc, "w": words(t), "who": words(t) & pros, "wd": words(t + " " + d)})

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

    # then fold together pieces on the same match or moment, even from the same outlet (e.g. three pieces on one
    #   final, or an outlet's match report and ranking-points piece), using headline + summary: within 12 hours of
    #   the group's lead and the same two ranked players, or one ranked player plus 3+ other key words (not names).
    #   Only the lead is compared, so stories can't chain together across a whole tournament. Groups covered by
    #   the most outlets come first; the best-known outlet's piece is then shown (BEST) and the rest go behind "Other outlets".
    def close(a, b):
        both = a["wd"] & b["wd"]
        who = len(both & pros)
        return abs((a["at"] - b["at"]).total_seconds()) < 12 * 3600 and (who >= 2 or (who >= 1 and len(both - names) >= 3))
    groups.sort(key=lambda g: (-len({x["s"] for x in g}), -max(x["at"] for x in g).timestamp()))
    folded = []
    for g in groups:
        for f in folded:
            if close(f[0], g[0]):
                f.extend(g)
                break
        else:
            folded.append(list(g))
    groups = folded

    out = []
    for g in groups:
        g = sorted(g, key=lambda x: (rank(x["s"]), -x["at"].timestamp()))  # the best-known outlet leads, see BEST
        lead = g[0]
        n = len({x["s"] for x in g})
        age = (NOW - max(x["at"] for x in g)).total_seconds() / 3600
        p72 = sorted({p for x in g for p in x["p72"]})
        sc = sorted({p for x in g for p in x["sc"]})
        k = lead["k"] or next((t for t in ("biz", "ev") if 2 * sum(x["k"] == t for x in g) >= len(g)), "")  # its lead's, or half the pieces
        if age > KEEP_H and not (p72 or sc or k):
            continue
        out.append({"t": lead["t"], "u": lead["u"], "s": lead["s"], "d": lead["d"],
                    "img": next((x["img"] for x in g if x["img"]), ""),  # the lead's picture, else another outlet's
                    "at": lead["at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "also": [{"s": x["s"], "u": x["u"]} for x in g[1:]],
                    "p72": p72, "sc": sc, "k": k, "score": round(n - age / 24 + BONUS.get(k, 0), 2)})
    out.sort(key=lambda x: (-x["score"], [-ord(c) for c in x["at"]]))
    top = [x for x in out if not (x["p72"] or x["sc"] or x["k"])][:MAX_TOP]
    biz = [x for x in out if x["k"] and not (x["p72"] or x["sc"])][:MAX_TOP]
    keep = [x for x in out if x["p72"] or x["sc"]] + biz + top
    keep.sort(key=lambda x: (-x["score"], [-ord(c) for c in x["at"]]))

    # a story whose feed has no picture: the article page's own share picture (og:image), read once per link
    #   (pics remembers what each link gave, "" = none, so a page is never read twice); at most 25 pages a run
    pics, fetched = old.get("pics") or {}, 0
    for x in keep:
        if x["img"] or "news.google." in x["u"]:  # a search link is Google's own page, not the article
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
