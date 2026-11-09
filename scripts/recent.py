"""
72 Central - keeps the "last 12 months" results up to date between ITF updates (free, no key, no Claude).

The 12 months come from the ITF's player activity (prospects.py itf_results), but the ITF only lists a pro tournament
(ATP/WTA, Challenger, ITF World Tennis Tour) once it has finished, and sometimes a day or two after that. So a player
in a tournament this week showed nothing from it until the next week. Tennis Explorer lists each match as it's played.

topup() adds, from the player's Tennis Explorer page, their singles matches of the last 3 weeks that fall outside every
tournament the ITF already lists for them. Those rows carry "x": "tx" and are rebuilt every time (never kept on their
own), so once the ITF has the tournament its own version takes over. Used by prospects.py (watch list),
suggest_results.py (suggestions) and lookup_results.py (results/ files), refreshed every 3 hours per player.

Linking, never a guess: Tennis Explorer's own search (/res/ajax/search.php) by full name; exactly one player with the
same name words (any order, accents folded), the same sex and, when known, the same nation. Kept as rec["tx"]; a player
not found is searched again after a week. A blocked or odd page stops Tennis Explorer for the rest of the run (Stop).
"""
import json, re, time, unicodedata, urllib.parse, urllib.request
from datetime import date, datetime, timedelta, timezone

BASE = "https://www.tennisexplorer.com"
UA = "72HubRankings/1.0 (+https://github.com/tlock72/72-central; scouting list, one request every few seconds)"
PAUSE = 3
EVERY = timedelta(hours=3)      # each player's fill-in is rebuilt this often
RETRY = timedelta(days=7)
LINK_V = 2                      # raise when find() gets better, so players not found before are searched again       # a player not found on Tennis Explorer is searched again after this
DAYS = 21                       # how far back the fill-in looks (the ITF is never this far behind)
SKIP = re.compile(r"league|bundesliga|exhibition|utr|team|hopman|laver|united cup|davis|billie jean|king cup", re.I)
ROUND = {"1R": "R1", "2R": "R2", "3R": "R3", "4R": "R4", "F": "F", "SF": "SF", "QF": "QF"}


class Stop(Exception):
    pass


def now():
    return datetime.now(timezone.utc)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def ago(s):
    try:
        return now() - datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return timedelta(days=9999)


def words(s):
    s = unicodedata.normalize("NFKD", (s or "").lower().replace("ß", "ss")).encode("ascii", "ignore").decode()
    return " ".join(sorted(re.findall(r"[a-z]+", s)))


def get(path):
    time.sleep(PAUSE)
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:
        raise Stop(f"Tennis Explorer couldn't be read ({e})")


# Tennis Explorer's own nation codes where they differ from the ITF / ATP / WTA ones
NAT = {"SER": "SRB", "BLG": "BUL", "HON": "HKG", "NZ": "NZL", "URY": "URU", "PRT": "POR", "ROM": "ROU"}


# Players the search can't single out (very common names), pinned by hand: name as on the ranking list -> the slug in
# their Tennis Explorer link (www.tennisexplorer.com/player/<slug>/). Only add one after checking the profile.
PIN = {"Ivan Ivanov": "ivanov-5f3c9"}  # Bulgarian, born 2008 (Tennis Explorer has two Bulgarian Ivan Ivanovs)


def find(name, nat, g):
    """(slug, note): the one Tennis Explorer player with this name, sex and (if known) nation, else (None, why).
    Searched by full name and by surname (its search misses some full names). Exact name words first; failing that,
    the same surname with a first name starting the same 3 letters (Darya / Daria, Yulia / Yuliia)."""
    if name in PIN:
        return PIN[name], "pinned by hand"
    sex = {"M": "man", "F": "woman"}.get(g)
    mine = words(name).split()
    longest = max(mine, key=len) if mine else ""
    seen = {}
    for q in dict.fromkeys([name, longest]):
        body = get("/res/ajax/search.php?" + urllib.parse.urlencode({"s": q, "t": "p"}))
        try:
            js = json.loads(body)
        except ValueError:
            raise Stop("Tennis Explorer's search didn't answer as expected")
        for x in js.get("links") or []:
            seen[x.get("url")] = x
    exact, close = [], []
    for x in seen.values():
        m = re.match(r"(.*?),\s*(.*?)\s*\(([A-Z]{2,3})\)\s*$", x.get("name") or "")
        if x.get("type") != "p" or not m or (sex and x.get("sex") != sex):
            continue
        if nat and NAT.get(m[3], m[3]) != nat:
            continue
        if words(m[1] + " " + m[2]) == words(name):
            exact.append(x["url"])
            continue
        last, first = words(m[1]).split(), words(m[2]).split()
        rest = [w for w in mine if w not in last]
        if last and set(last) <= set(mine) and len(rest) == len(first) == 1 and first[0][:3] == rest[0][:3]:
            close.append(x["url"])
        elif set(mine) < set(last + first) and len(last + first) == len(mine) + 1:
            close.append(x["url"])  # one extra first name on Tennis Explorer ("Maria Aran Teixido Garcia")
    for hits, how in ((exact, ""), (close, "close spelling")):
        if len(hits) == 1:
            return hits[0], how
        if len(hits) > 1:
            return None, "more than one player fits"
    return None, "not found"


def score_of(cell):
    cell = re.sub(r"<sup>\s*(\d+)\s*</sup>", r"(\1)", cell)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cell)).replace("&nbsp;", " ").strip()


def flip(s):
    """'6-2, 6-1' from the winner's side -> '2-6, 1-6' from the loser's (tiebreak points stay where they are)."""
    return re.sub(r"(\d+)-(\d+)", r"\2-\1", s)


def matches(slug, year):
    """The player's singles matches this year on Tennis Explorer, newest first, grouped by tournament heading."""
    page = get(f"/player/{slug}/")
    if f'/player/{slug}/' not in page:
        raise Stop("Tennis Explorer sent a page without the player on it")
    i = page.find(f'id="matches-{year}-1-data"')
    if i < 0:
        return []
    seg = page[i:page.find("</table>", i)]
    out, head = [], None
    for tr in re.findall(r"<tr class=\"([^\"]*)\">(.*?)</tr>", seg, re.S):
        cls, row = tr
        if "head" in cls:
            a = re.search(r'<td class="t-name"[^>]*>(?:<a href="([^"]+)">)?(.*?)(?:</a>)?</td>', row, re.S)
            name = re.sub(r"<[^>]+>|&nbsp;", " ", a[2] if a else "")
            head = {"t": re.sub(r"\s+", " ", name).strip(), "link": (BASE + a[1]) if a and a[1] else ""}
            continue
        d = re.search(r'<td class="first time">\s*(\d{2})\.(\d{2})\.', row)
        ps = re.findall(r'<a href="/player/([^/"]+)/"[^>]*>(.*?)</a>', row, re.S)
        rnd = re.search(r'<td class="round"[^>]*>(.*?)</td>', row, re.S)
        sc = re.search(r'<td class="tl">(.*?)</td>', row, re.S)
        if not (head and d and len(ps) == 2 and rnd and sc):
            continue
        rnd = re.sub(r"<[^>]+>|&nbsp;", "", rnd[1]).strip()
        s = score_of(sc[1])
        if not rnd or SKIP.search(head["t"]):
            continue  # league / team / exhibition matches aren't on the ITF either
        walkover = re.search(r"w/?o|walk", s, re.I)
        if not re.search(r"\d-\d", s) and not walkover:
            continue  # not played yet
        me = [p[0] for p in ps].index(slug) if slug in [p[0] for p in ps] else -1
        if me < 0:
            continue
        opp = re.sub(r"<[^>]+>", "", ps[1 - me][1]).strip()
        m = re.match(r"(.+?)\s+([A-Z][\w'-]*)\.?$", opp)  # "Rodionov J." -> "J. Rodionov"
        opp = f"{m[2][0]}. {m[1]}" if m else opp
        q = rnd.upper().startswith("Q-")
        r = ROUND.get(rnd[2:] if q else rnd, rnd[2:] if q else rnd)
        mid = re.search(r"match-detail/\?id=(\d+)", sc[1])
        out.append({"id": mid[1] if mid else "", "day": date(year, int(d[2]), int(d[1])), "head": head, "r": ("Q-" if q else "") + r, "o": opp,
                    "res": "W" if me == 0 else "L", "s": "walkover" if walkover else (s if me == 0 else flip(s))})
    return out


def tournaments(ms, g=None):  # g: kept for callers
    """Rows as the site shows them: one tournament per heading (ITF 'Futures' headings split where there's a gap)."""
    groups = []
    for m in ms:  # newest first
        g = groups[-1] if groups else None
        if g and g["head"] is m["head"] and (g["first"] - m["day"]).days <= 5:
            g["m"].append(m); g["first"] = m["day"]
        else:
            groups.append({"head": m["head"], "m": [m], "first": m["day"], "last": m["day"]})
    rows = []
    for g in groups:
        h, first, last = g["head"], g["first"], g["last"]
        start = first - timedelta(days=first.weekday())
        if first.weekday() >= 5 and all(m["r"].startswith("Q-") for m in g["m"]):
            start += timedelta(days=7)  # weekend qualifying belongs to the next week's tournament
        end = max(last - timedelta(days=last.weekday()) + timedelta(days=6), start + timedelta(days=6))
        # level only when Tennis Explorer's name says it ("Taipei challenger", "Hong Kong WTA", "Le Neubourg ITF",
        # "Futures 2026"); a bare city ("Paris", "Rovereto") can be a tour or ITF event, so it gets no level (never a guess)
        t = re.sub(r"\s+", " ", h["t"]).strip()
        nice = lambda x: " ".join(w[:1].upper() + w[1:] for w in x.split())
        if re.match(r"futures\b", t, re.I):
            name, cat = "ITF World Tennis Tour event", "ITF"
        elif re.search(r"\bitf$", t, re.I):
            name, cat = nice(re.sub(r"\s*itf$", "", t, flags=re.I)) + " ITF", "ITF"
        elif re.search(r"\bchallenger$", t, re.I):
            name, cat = nice(re.sub(r"\s*challenger$", "", t, flags=re.I)) + " Challenger", "CH"
        elif re.search(r"\b(atp|wta)$", t, re.I):
            tour = t[-3:].upper()
            name, cat = nice(t[:-3].strip()) + " " + tour, tour
        else:
            name, cat = nice(t), ""
        for m in g["m"]:
            rows.append({"src": "itf-pro", "start": start.isoformat(), "end": end.isoformat(), "t": name, "cat": cat,
                         "where": "", "link": h["link"], "r": m["r"], "o": m["o"], "on": "", "res": m["res"], "s": m["s"],
                         "x": "tx", "day": m["day"].isoformat()})
    return rows


def topup(rec, name, nat, g, pro=False, force=False):
    """Rebuilds the Tennis Explorer fill-in on rec["results"]. pro: an ATP/WTA list player (else only players with
    ITF pro results). Returns True if rec changed. Raises Stop when Tennis Explorer can't be used this run."""
    base = [r for r in rec.get("results") or [] if not r.get("x")]
    had = [r for r in rec.get("results") or [] if r.get("x")]
    if not (pro or any(r.get("src") == "itf-pro" for r in base)) or not g:
        return False
    tx = rec.get("tx") or {}
    if tx.get("q") != [name, nat, g]:
        tx = {}
    # the ITF part was just re-read (the scripts rebuild "results" from the ITF alone): rebuild the fill-in now
    sig = f'{len(base)}|{base[0].get("start") if base else ""}|{base[0].get("t") if base else ""}|{len(had)}'
    if not force and ago(tx.get("at")) < EVERY and tx.get("sig") == sig:
        return False
    if not tx.get("slug") and ago(tx.get("tried")) < RETRY and tx.get("v") == LINK_V:
        return False
    if not tx.get("slug"):
        slug, note = find(name, nat, g)
        tx = {"q": [name, nat, g], "tried": iso(now()), "v": LINK_V}
        if not slug:
            tx["note"] = note
            rec["tx"] = tx
            if had:
                rec["results"] = base
            return True
        tx["slug"] = slug
        if note:
            tx["how"] = note
    today = now().date()
    ms = matches(tx["slug"], today.year)
    lo = today - timedelta(days=DAYS)
    ms = [m for m in ms if m["day"] >= lo]
    # a whole tournament is left out when the ITF already lists it: the same week, or (two-week events) a start
    # within 13 days and a word of the name in common ("Paris" / "Paris ATP 1000")
    itf = {(r["start"], r["t"]) for r in base if r.get("src") == "itf-pro" and r.get("start")}
    key = lambda t: {w for w in re.findall(r"[a-z]{4,}", words(t)) if w not in ("challenger", "open", "tour", "world", "tennis", "event")}
    def covered(row):
        st = date.fromisoformat(row["start"])
        return any(s == row["start"] or (abs((date.fromisoformat(s) - st).days) <= 13 and key(t) & key(row["t"])) for s, t in itf)
    extra = [r for r in tournaments(ms, g) if not covered(r)]
    tx["at"] = iso(now())
    tx["sig"] = f'{len(base)}|{base[0].get("start") if base else ""}|{base[0].get("t") if base else ""}|{len(extra)}'
    rec["tx"] = tx
    res = sorted(base + extra, key=lambda r: (r["end"], r["start"], r.get("day") or ""), reverse=True)
    # newest match first inside each tournament (the page reads the first one as how far they went)
    rec["results"] = res
    if "w" in rec or "l" in rec:
        rec["w"] = sum(r["res"] == "W" for r in res)
        rec["l"] = sum(r["res"] == "L" for r in res)
    if extra:
        print(f"  Tennis Explorer: {len(extra)} recent match{'es' if len(extra) != 1 else ''} the ITF hasn't listed yet")
    return True


# ---------- Watch list "Scores & results": live / last 24 hours / next 24 hours ----------
# Tennis Explorer's day pages (/matches/?type=all, every ATP, WTA, Challenger and ITF singles match of a day, times in
# the GMT offset the page states) give each match's start time and the score at the time of reading. Those pages don't
# mark retirements, walkovers or the end of a match, so a match only counts as finished once it is on the player's own
# page (matches(), by Tennis Explorer's match id) with its final score; until then a score is "live", and once 5 hours
# have passed since the start with no final score it is "no final score yet" (never a guessed result).
LIVE_FOR = timedelta(hours=5)


def opp_name(raw):
    raw = re.sub(r"<[^>]+>", "", raw).strip()
    m = re.match(r"(.+?)\s+([A-Z][\w'-]*)\.?$", raw)
    return f"{m[2][0]}. {m[1]}" if m else raw


def day_page(d):
    """Singles matches on Tennis Explorer's page for day d: [{id, t, link, at (UTC iso or ""), p: [(slug, name)] x2,
    sets: [a, b] or None, games: ["6-3", ...] from player 1's side}]."""
    page = get(f"/matches/?type=all&year={d.year}&month={d.month:02d}&day={d.day:02d}")
    off = re.search(r"GMT([+-]\d{1,2})", page)
    if not off or "<table" not in page:
        raise Stop("Tennis Explorer's day page didn't answer as expected")
    tz = timezone(timedelta(hours=int(off[1])))
    out, head, i = [], None, page.find('<table class="result')
    rows = re.findall(r'<tr(?: id="([rs]\d+b?)")? class="([^"]*)"[^>]*>(.*?)</tr>', page[i:], re.S)
    k = 0
    while k < len(rows):
        rid, cls, row = rows[k]
        if "head" in cls:
            a = re.search(r'<td class="t-name"[^>]*>(?:<a href="([^"]+)">)?(.*?)(?:</a>)?</td>', row, re.S)
            name = re.sub(r"<[^>]+>|&nbsp;", " ", a[2] if a else "")
            head = {"t": re.sub(r"\s+", " ", name).strip(), "link": (BASE + a[1]) if a and a[1] else ""}
            k += 1; continue
        if not rid or rid.endswith("b") or k + 1 >= len(rows) or rows[k + 1][0] != rid + "b" or not head:
            k += 1; continue
        a, b = row, rows[k + 1][2]
        k += 2
        pa = re.search(r'<td class="t-name"><a href="/player/([^/"]+)/">(.*?)</a>', a)
        pb = re.search(r'<td class="t-name"><a href="/player/([^/"]+)/">(.*?)</a>', b)
        if not pa or not pb:
            continue  # doubles (two names a side) or no player link
        tm = re.search(r'<td class="first time"[^>]*>\s*(\d{2}):(\d{2})', a)
        at = datetime(d.year, d.month, d.day, int(tm[1]), int(tm[2]), tzinfo=tz).astimezone(timezone.utc) if tm else None
        res = lambda r: (re.search(r'<td class="result">\s*(\d+)\s*</td>', r) or [None, None])[1]
        sa, sb = res(a), res(b)
        ga = [score_of(x) for x in re.findall(r'<td class="score">(.*?)</td>', a, re.S)]
        gb = [score_of(x) for x in re.findall(r'<td class="score">(.*?)</td>', b, re.S)]
        games = []
        for x, y in zip(ga, gb):
            if not x or not y or not re.match(r"\d", x) or not re.match(r"\d", y):
                break
            tx_, ty = re.match(r"(\d+)(?:\((\d+)\))?", x), re.match(r"(\d+)(?:\((\d+)\))?", y)
            tb = tx_[2] or ty[2]
            games.append(f"{tx_[1]}-{ty[1]}" + (f"({tb})" if tb else ""))
        mid = re.search(r"match-detail/\?id=(\d+)", a)
        out.append({"id": mid[1] if mid else "", "t": head["t"], "link": head["link"], "at": iso(at) if at else "",
                    "p": [(pa[1], pa[2]), (pb[1], pb[2])], "sets": [int(sa), int(sb)] if sa is not None and sb is not None else None,
                    "games": games})
    return out


def live(slugs):
    """slugs: {Tennis Explorer slug: watch list key}. Their singles matches from yesterday to tomorrow (Tennis
    Explorer's days), each {k, id, t, link, at, o, st: live / done / open / next, res, s (from our player's side), sets}."""
    today = now().date()
    found = []
    for d in (today - timedelta(days=1), today, today + timedelta(days=1)):
        for m in day_page(d):
            me = 0 if m["p"][0][0] in slugs else 1 if m["p"][1][0] in slugs else -1
            if me >= 0:
                found.append((me, m))
    done = {}
    for slug in {m["p"][me][0] for me, m in found}:
        for x in matches(slug, today.year)[:8]:  # the player's own page: finished matches with their final scores
            if x["id"]:
                done[x["id"]] = x
    out = []
    for me, m in found:
        slug, k = m["p"][me][0], slugs[m["p"][me][0]]
        g = m["games"] if me == 0 else [flip(x) for x in m["games"]]
        e = {"k": k, "id": m["id"], "t": m["t"], "link": m["link"], "at": m["at"], "o": opp_name(m["p"][1 - me][1])}
        f = done.get(m["id"])
        if f:
            e.update(st="done", res=f["res"], s=f["s"], r=f["r"])
        elif not g:
            e["st"] = "next"
        elif m["at"] and ago(m["at"]) > LIVE_FOR:
            e.update(st="open", s=", ".join(g))   # a score but no final result after 5 hours: shown, never decided
        else:
            e.update(st="live", s=", ".join(g))
            if m["sets"]:
                e["sets"] = m["sets"] if me == 0 else m["sets"][::-1]
        out.append(e)
    return sorted(out, key=lambda e: e["at"] or "9")
