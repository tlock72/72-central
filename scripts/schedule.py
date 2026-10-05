"""
72 Central - Tour schedule (runs once a day in its own workflow, schedule.yml, no Claude, no paid services).

Builds schedule.json: every tournament from this week to the end of the year on the ATP Tour, WTA Tour,
ATP Challenger Tour, WTA 125, ITF men's and women's World Tennis Tour, ITF Juniors and Tennis Europe,
plus which 72 players are entered in the next few weeks (as far ahead as entry lists are published).

Sources (all free, no key):
  - ATP Tour and Challenger Tour: Wikipedia's "2026 ATP Tour" and "2026 ATP Challenger Tour" pages
    (week, name, city, surface and category). The ATP has no open calendar feed.
  - WTA Tour and WTA 125: the WTA's own feed (api.wtatennis.com), which also has each event's player list.
  - ITF (men, women, juniors): the ITF's calendar and acceptance lists (itftennis.com). Stops at the ITF
    bot check and never tries to get past it.
  - Tennis Europe: its tournament search on te.tournamentsoftware.com, and each 72 junior's profile, which
    lists the tournaments they have entered (used with permission, internal use only).
72 entries:
  - ITF: the official acceptance list, matched by ITF player id.
  - WTA / WTA 125: the WTA player list, matched by name.
  - Tennis Europe: the player's own Tennis Europe profile.
  - ATP / Challenger: the ATP's own site blocks GitHub, so three free sites are read. live-tennis.eu (each
    top ~1,000 player's events for the next 3 weeks, the most up to date) must list the player, and Tick Tock
    Tennis (each event's main draw, qualifying and alternate lists) or Spazio Tennis (each event's official
    acceptance list) must agree on the same event. This week's events aren't on live-tennis.eu, so for those
    Tick Tock and Spazio must both list the player. Once the draw is out, the matches in data.json show the
    player as "In the draw".
A part that fails keeps what it had last time and is listed under "errors" (report_gaps.py alerts).
"""
import html, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(__file__))
from update import ROSTER  # roster id -> (name, "atp" / "wta")

UK = ZoneInfo("Europe/London")
NOW = datetime.now(timezone.utc)
T = NOW.astimezone(UK).date()
YEAR = T.year
FROM = T - timedelta(days=T.weekday())          # Monday of this week
TO = date(YEAR, 12, 31)
ENTRY_DAYS = 28   # entry lists come out about 3-4 weeks before an event, so 72 entries are shown up to 4 weeks ahead
OUT = "schedule.json"
UA = "72CentralSchedule/1.0 (+https://github.com/tlock72/72-central; once a day, one request every few seconds)"
ITF = "https://www.itftennis.com/tennis/api"
WTA = "https://api.wtatennis.com/tennis"
WIKI = "https://en.wikipedia.org/w/api.php"
TE_SITE = "https://te.tournamentsoftware.com"
PAUSE = {"itf": 4, "te": 4, "other": 1}


class Blocked(Exception):
    pass


def get(url, kind="other", data=None, headers=None, opener=None):
    time.sleep(PAUSE[kind])
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept": "application/json,text/html", **(headers or {})})
    with (opener.open(req, timeout=40) if opener else urllib.request.urlopen(req, timeout=40)) as r:
        return r.read().decode("utf-8", "replace")


def get_json(url, kind="other"):
    body = get(url, kind)
    if not body.lstrip().startswith(("{", "[")):
        raise Blocked("answered with a web page instead of data (bot check)")
    return json.loads(body)


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def key(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return " ".join(sorted(re.findall(r"[a-z]+", s)))


def in_window(start, end):
    """Events whose entry list is normally out: started already but not finished, or starting within ENTRY_DAYS."""
    return end >= T.isoformat() and start <= (T + timedelta(days=ENTRY_DAYS)).isoformat()


# importance, 1 = biggest; the website colours and sizes events by it
def tier(tour, cat):
    c = (cat or "").lower()
    n = int(re.sub(r"\D", "", c) or 0)
    if tour == "jun":  # junior finals and team finals rank with the J500s
        return 5 if n >= 500 or "finals" in c else 6 if n >= 300 else 7 if n >= 200 else 8
    if "grand slam" in c or c.endswith("finals") and "next gen" not in c and "cup" not in c:
        return 1
    if tour in ("atp", "wta"):
        return 2 if n == 1000 else 3 if n == 500 or "cup" in c or "next gen" in c else 4
    if tour == "ch":
        return 5 if n >= 125 else 6 if n >= 75 else 7
    if tour in ("itfm", "itfw"):
        if "125" in c:
            return 5
        return 6 if n >= 75 else 7 if n >= 35 or n == 25 else 8
    if tour == "te":
        return 5 if any(w in c for w in ("super", "masters", "european championship")) else 6 if c.endswith("1") else 7 if c.endswith("2") else 8
    return 8


# ---------------- ATP Tour and Challenger Tour (Wikipedia) ----------------
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def wiki_week(s):
    """'5 Jan', 'January 5' or '12 October' -> date in YEAR."""
    m = re.match(r"(\d{1,2})\s+([A-Za-z]{3})", s) or None
    if m:
        d, mo = int(m.group(1)), m.group(2)
    else:
        m = re.match(r"([A-Za-z]{3})[A-Za-z]*\s+(\d{1,2})", s)
        if not m:
            return None
        mo, d = m.group(1), int(m.group(2))
    mo = MONTHS.get(mo.lower())
    return date(YEAR, mo, d) if mo else None


def unlink(s):
    s = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\{\{[^}]*\}\}", "", s)
    s = re.sub(r"<[^>]+>", " ", s)
    return html.unescape(re.sub(r"\s+", " ", s)).strip(" ,'")


def atp_wiki(page, tour):
    w = get(WIKI + "?" + urllib.parse.urlencode({"action": "parse", "page": page, "prop": "wikitext", "format": "json", "formatversion": 2}))
    text = json.loads(w)["parse"]["wikitext"]
    out, week, weeks = [], None, 1
    for line in text.split("\n"):
        if not line.startswith("|") or line.startswith(("|-", "|+", "|}")):
            continue
        cells = line[1:].split("||")
        first = re.sub(r'^\s*(?:rowspan="?\d+"?\s*\|)?', "", cells[0]).strip()
        wk = wiki_week(re.sub(r"<br\s*/?>.*", "", first))
        if wk:
            week = wk
            last = wiki_week(re.split(r"<br\s*/?>", first)[-1].strip())  # two-week events list both Mondays
            weeks = max(1, ((last - wk).days // 7 + 1) if last and last > wk else 1)
            cells = cells[1:]
        if not week or not cells:
            continue
        cell = re.sub(r'^\s*(?:(?:style|rowspan|colspan)="?[^|"]*"?\s*)+\|', "", cells[0]).strip()
        parts = [p for p in re.split(r"<br\s*/?>", cell)]
        if len(parts) < 3:
            continue
        name, place = unlink(parts[0]), unlink(parts[1])
        rest = [unlink(p) for p in parts[2:]]
        cat, surface = None, ""
        for p in rest:
            m = re.search(r"(Grand Slam|Next Gen ATP Finals|ATP Finals|ATP (?:250|500|1000)|Challenger \d+|Davis Cup[^–]*|Laver Cup|United Cup)", p)
            if m and not cat:
                cat = m.group(1).strip()
            if " – " in p and not surface:
                surface = p.split(" – ")[0].strip()
        if tour == "atp" and not cat and "Grand Slam" in line:
            cat = "Grand Slam"
        if not cat and re.search(r"Davis Cup|Laver Cup|United Cup", name):
            cat = re.search(r"Davis Cup|Laver Cup|United Cup", name).group(0) + (" Finals" if "Finals" in name else "")
        if not cat or not name:
            continue
        link = re.match(r"\s*\[\[([^\]|]+)", parts[0])
        out.append({"tour": tour, "cat": cat, "name": name, "place": place, "start": week.isoformat(),
                    "end": (week + timedelta(days=7 * weeks - 1)).isoformat(), "surface": surface, "weekOnly": True,
                    "link": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(link.group(1).replace(" ", "_")) if link else ""})
    return out


# ---------------- WTA Tour and WTA 125 (WTA feed) ----------------
def wta_events():
    out, page = [], 0
    while page < 10:
        j = get_json(f"{WTA}/tournaments/?" + urllib.parse.urlencode({"page": page, "pageSize": 100, "excludeLevels": "ITF",
                                                                      "from": FROM.isoformat(), "to": TO.isoformat()}))
        rows = j.get("content") or []
        for t in rows:
            g = t.get("tournamentGroup") or {}
            lvl = t.get("level") or g.get("level") or ""
            lvl = "WTA Finals" if lvl.lower() == "finals" else lvl
            slug = re.sub(r"[^a-z0-9]+", "-", (g.get("name") or "").lower()).strip("-")
            out.append({"tour": "itfw" if "125" in lvl else "wta", "cat": lvl, "name": (t.get("title") or "").split(" - ")[0],
                        "place": ", ".join(x for x in ((t.get("city") or "").title(), t.get("country") or "") if x),
                        "start": t.get("startDate"), "end": t.get("endDate"), "surface": t.get("surface") or "",
                        "link": f"https://www.wtatennis.com/tournaments/{g.get('id')}/{slug}/{t.get('year')}", "wtaId": g.get("id"), "year": t.get("year")})
        if len(rows) < 100:
            break
        page += 1
    return out


def wta_entries(ev, wta72):
    j = get_json(f"{WTA}/tournaments/{ev['wtaId']}/{ev['year']}/players")
    found = []
    for e in j.get("events") or []:
        if e.get("eventTypeCode") != "LS":  # ladies' singles
            continue
        for ep in e.get("eventPlayers") or []:
            for p in ep.get("players") or []:
                rid = wta72.get(key(p.get("fullName") or f"{p.get('firstName', '')} {p.get('lastName', '')}"))
                if rid:
                    found.append({"id": rid, "how": {"Q": "Qualifier", "WC": "Wildcard", "LL": "Lucky loser", "PR": "Protected ranking",
                                                     "SE": "Special exempt", "ALT": "Alternate"}.get(ep.get("entryType") or "", "Entered")})
    return found


# ---------------- ITF (men's, women's, juniors) ----------------
def itf_events(circuit, tour):
    out, skip = [], 0
    while skip < 1000:
        j = get_json(f"{ITF}/TournamentApi/GetCalendar?" + urllib.parse.urlencode({
            "circuitCode": circuit, "searchString": "", "skip": skip, "take": 100, "nationCodes": "", "zoneCodes": "",
            "dateFrom": FROM.isoformat(), "dateTo": TO.isoformat(), "indoorOutdoor": "", "categories": "",
            "isOrderAscending": "true", "orderField": "startDate", "surfaceCodes": ""}), "itf")
        items = j.get("items") or []
        for t in items:
            if (t.get("tourStatusCode") or "").upper() in ("C", "X"):  # cancelled
                continue
            cat = {"JM": "Junior Finals", "GC": "Junior team finals"}.get(t.get("category") or "", t.get("category") or "")
            out.append({"tour": tour, "cat": cat, "name": t.get("tournamentName") or t.get("name") or "",
                        "place": ", ".join(x for x in (t.get("location") or t.get("venue"), t.get("hostNation")) if x),
                        "start": (t.get("startDate") or "")[:10], "end": (t.get("endDate") or "")[:10], "surface": t.get("surfaceDesc") or "",
                        "link": "https://www.itftennis.com" + (t.get("tournamentLink") or ""), "itfKey": t.get("tournamentKey"), "circuit": circuit})
        skip += 100
        if skip >= (j.get("totalItems") or 0) or not items:
            break
    return out


ITF_HOW = {"M": "Main draw", "Q": "Qualifying", "A": "Alternate", "JA": "Junior exempt", "SE": "Special exempt",
           "WC": "Wildcard", "LL": "Lucky loser", "JR": "Junior reserved"}


def itf_entries(ev, itf72):
    lists = get_json(f"{ITF}/TournamentApi/GetAcceptanceList?" + urllib.parse.urlencode({"tournamentKey": ev["itfKey"], "circuitCode": ev["circuit"]}), "itf")
    found = {}
    for group in lists or []:
        for cl in group.get("entryClassifications") or []:
            raw = (cl.get("entryClassification") or "").strip().lower()
            if "withdraw" in raw:
                continue  # pulled out: not entered any more
            how = next((v for k, v in (("main draw", "Main draw"), ("qualif", "Qualifying"), ("alternate", "Alternate"), ("junior exempt", "Junior exempt"),
                                       ("wild", "Wildcard"), ("special exempt", "Special exempt"), ("lucky", "Lucky loser")) if k in raw), None) \
                or raw.capitalize() or ITF_HOW.get(cl.get("entryClassificationCode") or "", "Entered")
            for e in cl.get("entries") or []:
                for p in e.get("players") or []:
                    rid = itf72.get(p.get("playerId"))
                    if rid and rid not in found:
                        found[rid] = {"id": rid, "how": how}
    return list(found.values())


# ---------------- Tennis Europe ----------------
def te_session():
    import te_matches as TE  # same cookie choice as a visitor (only the essential cookies)
    TE.consent()
    return TE


def te_events(TE):
    out, seen = [], set()
    for page in range(1, 80):
        data = urllib.parse.urlencode({"Page": page, "TournamentFilter.StartDate": FROM.isoformat(), "TournamentFilter.EndDate": TO.isoformat(),
                                       "TournamentFilter.DateFilterType": "0", "TournamentFilter.Q": "",
                                       "LoadMoreResults": "true" if page > 1 else "false"}).encode()
        body = get(TE_SITE + "/find/tournament/DoSearch", "te", data=data, opener=TE.opener,
                   headers={"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/x-www-form-urlencoded"})
        items = te_items(body)
        new = [i for i in items if i["teId"] not in seen]
        for i in new:
            seen.add(i["teId"])
            out.append(i)
        if not new:
            break
    return out


def te_items(body):
    out = []
    for chunk in re.split(r'(?=<h4 class="media__title)', body)[1:]:
        a = re.search(r'href="(/sport/tournament\?id=([0-9A-Fa-f-]+))"[^>]*title="([^"]*)"', chunk)
        times = re.findall(r'<time datetime="(\d{4}-\d{2}-\d{2})', chunk)
        if not a or len(times) < 2:
            continue
        sub = re.search(r'media__subheading">(.*?)</small>', chunk, re.S)
        place = unlink(sub.group(1)) if sub else ""
        place = place.split("|")[-1].strip() if "|" in place else place
        tags = [unlink(t) for t in re.findall(r'<span class="tag[^"]*">(.*?)</span>', chunk, re.S)]
        cat = next((t for t in tags if re.match(r"(Super Category|Category \d|Masters|European Championship|Tennis Europe Festival|Invitational|Small States)", t)), "")
        if not cat:
            continue  # not a Tennis Europe graded event
        ages = [t.replace("&U", "") for t in tags if re.match(r"\d+&U", t)]
        out.append({"tour": "te", "cat": cat, "name": html.unescape(a.group(3)).strip(), "place": place, "start": times[0], "end": times[1],
                    "surface": "", "ages": ages, "status": "Postponed" if "Postponed" in tags else "",
                    "link": TE_SITE + html.unescape(a.group(1)), "teId": a.group(2).upper()})
    return out


def te_entries(TE, profiles):
    """Tournament id -> 72 juniors entered, from each junior's Tennis Europe profile."""
    found = {}
    for rid, pid in profiles.items():
        if ":" in rid or not pid:
            continue
        body = get(f"{TE_SITE}/player-profile/{pid}/tournaments", "te", opener=TE.opener)
        for chunk in re.split(r'(?=<h4 class="media__title)', body)[1:]:
            a = re.search(r'/sport/tournament\?id=([0-9A-Fa-f-]+)', chunk)
            if a:
                found.setdefault(a.group(1).upper(), []).append({"id": rid, "how": "Entered"})
    return found


# ---------------- ATP / Challenger: 72 entries before the draw (two free sites that must agree) ----------------
LT_URL = "https://live-tennis.eu/en/atp-schedule"   # top ~1,000 men, each with the tournaments entered in the next 3 weeks
TT_URL = "https://www.ticktocktennis.com/atp"       # every ATP / Challenger entry list for the next few weeks
SP_API = "https://www.spaziotennis.com/wp-json/wp/v2"  # Spazio Tennis (Italian): each event's official acceptance list, posted weeks ahead
IT_CITY = {"pechino": "beijing", "basilea": "basel", "firenze": "florence", "lisbona": "lisbon", "siviglia": "seville", "ginevra": "geneva",
           "parigi": "paris", "londra": "london", "bruxelles": "brussels", "anversa": "antwerp", "stoccolma": "stockholm", "marsiglia": "marseille",
           "lione": "lyon", "amburgo": "hamburg", "monaco di baviera": "munich", "praga": "prague", "atene": "athens", "canton": "guangzhou",
           "citta del messico": "mexico", "nuova delhi": "delhi", "san pietroburgo": "petersburg", "varsavia": "warsaw", "cracovia": "krakow",
           "salonicco": "thessaloniki", "mosca": "moscow", "il cairo": "cairo", "colonia": "cologne", "tenerife": "tenerife"}
TT_HOW = {"main": "Main draw", "wc": "Wildcard", "qual": "Qualifying", "alt": "Alternate", "next": "Alternate",
          "qnext": "Qualifying alternate", "qualAlt": "Qualifying alternate"}
PLAIN = {"challenger", "open", "tennis", "cup", "international", "masters", "championships", "trophy", "tournament", "atp",
         "hardcourt", "clay", "grass", "carpet", "indoor", "outdoor", "qual"}


def pkey(s):
    """Player name key that copes with accents, umlauts written as 'ae', and any word order."""
    s = (s or "").lower().replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"(?<=[a-z])(ae|oe|ue)", lambda m: m.group(1)[0], s)
    return " ".join(sorted(re.findall(r"[a-z]+", s)))


def place_words(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return {w for w in re.findall(r"[a-z]{3,}", s) if w not in PLAIN}


def find_event(name, monday, events):
    """The one ATP / Challenger event in the week of `monday` whose name or city matches `name` ('Olbia', 'Guangzhou 2')."""
    want = place_words(re.sub(r"\(.*?\)|\s-\s.*$", "", name))
    if not want:
        return None
    hits = [e for e in events if e["tour"] in ("atp", "ch") and e["start"] == monday.isoformat()
            and want <= place_words(e["name"]) | place_words(e["place"])]
    return hits[0] if len(hits) == 1 else None


def best_weeks(cols, events, offsets, need):
    """Which week each column is: the offset (in weeks from this Monday) under which most names match a real event.
    The sites roll their weeks over at their own time, so this is checked every run instead of assumed."""
    score = {}
    for off in offsets:
        score[off] = sum(1 for i, names in enumerate(cols) for n in names if find_event(n, FROM + timedelta(weeks=i + off), events))
    best = max(score, key=score.get)
    if score[best] < need or any(v * 2 > score[best] for k, v in score.items() if k != best):
        raise RuntimeError(f"couldn't tell which week is which (matches per offset: {score})")
    return best


def lt_entries(events, men, need):
    """live-tennis.eu: {(roster id, event key): qualifying?} for 72 men, {event key: every player listed}, and the
    week (from this Monday) of its first column: events starting before that aren't covered."""
    body = get(LT_URL)
    rows = re.findall(r"(?s)<tr[^>]*>\s*<td class=\"?rk\"?>.*?</tr>", body)
    if len(rows) < 800:
        raise RuntimeError(f"the player table has only {len(rows)} rows")
    parsed = []
    for r in rows:
        name = re.search(r"<td class=\"?pn\"?>(.*?)</td>", r)
        cells = re.split(r"<td", r.split("</td>", 5)[-1])[1:]  # the week columns after rank, flag, name, age and country
        weeks = []
        for c in cells:
            attrs, _, inner = c.partition(">")
            span = int((re.search(r"colspan=(\d+)", attrs) or [0, 1])[1])
            parts = [p.strip() for p in re.split(r"[\n,]", html.unescape(re.sub(r"<[^>]+>", "\n", inner)))]
            weeks += [[p for p in parts if p]] + [[] for _ in range(span - 1)]
        parsed.append((html.unescape(re.sub(r"<[^>]+>", "", name.group(1))) if name else "", weeks))
    unq = lambda n: n.replace("Qual.", "").strip()
    cols = [[unq(n) for _, w in parsed if i < len(w) for n in w[i]] for i in range(max(len(w) for _, w in parsed))]
    off = best_weeks(cols, events, (0, 1), need)
    out, everyone = {}, {}
    for name, weeks in parsed:
        rid = men.get(pkey(name))
        for i, names in enumerate(weeks):
            for n in names:
                ev = find_event(unq(n), FROM + timedelta(weeks=i + off), events)
                if ev:
                    everyone.setdefault(ev_key(ev), set()).add(pkey(name))
                    if rid:
                        out[(rid, ev_key(ev))] = n.startswith("Qual.")
    return out, everyone, off


def tt_entries(events, men, need, everyone):
    """Tick Tock Tennis: {(roster id, event key): list it is on} for 72 men. The page holds one block of lists per week."""
    body = get(TT_URL)
    upd = re.search(r"Data updated (\w{3} \d{1,2}, \d{4})", body)
    if not upd:
        raise RuntimeError("no 'Data updated' date on the page")
    upd = datetime.strptime(upd.group(1), "%b %d, %Y").date()
    if (T - upd).days > 6:
        raise RuntimeError(f"the entry lists haven't been updated since {upd}")
    blocks = re.split(r"atpData\.\w+\s*=\s*\{\s*\"gs\"", body)[1:]
    if not blocks:
        raise RuntimeError("no entry lists found on the page")
    weeks = []
    for b in blocks:
        tours = []
        for t in re.split(r"\{\s*name:\s*", b.split("};", 1)[0])[1:]:
            tname = (re.match(r'"([^"]*)"', t) or [None, ""])[1]
            lists = {}
            for part, arr in re.findall(r"(\w+):\s*(\[\[.*?\]\]|\[\])", t):
                for p in re.findall(r"\[([^\[\]]*)\]", arr):
                    try:
                        x = json.loads("[" + p + "]")  # [rank, name, country, tags...]
                    except ValueError:
                        print("Tick Tock Tennis: unreadable entry skipped:", p[:80])
                        continue
                    if len(x) >= 2:
                        lists[pkey(x[1])] = "withdrawn" if "W" in x[3:] else part
            tours.append((tname, lists))
        weeks.append(tours)
    off = best_weeks([[n for n, _ in w] for w in weeks], events, (-1, 0, 1), need)
    out = {}
    for i, tours in enumerate(weeks):
        for tname, lists in tours:
            ev = find_event(tname, FROM + timedelta(weeks=i + off), events)
            for k, part in lists.items() if ev else ():
                if part != "withdrawn":
                    everyone.setdefault(ev_key(ev), set()).add(k)  # helps recognise Spazio's lists
                if k in men:
                    out[(men[k], ev_key(ev))] = part
    return out


def sp_entries(events, men, everyone):
    """Spazio Tennis: {(roster id, event key): "main" or "alt"} for 72 men. Each list is matched to the coming event in
    the city its heading names (Italian names like 'Firenze' translated), and only used if most of its players are
    also down for that event on live-tennis.eu or Tick Tock, so an old edition's list is never used."""
    cat = json.loads(get(f"{SP_API}/categories?slug=ent&_fields=id"))
    if not cat:
        raise RuntimeError("the 'Entry List' category is missing")
    after = (FROM - timedelta(days=42)).isoformat() + "T00:00:00"
    posts = json.loads(get(f"{SP_API}/posts?categories={cat[0]['id']}&per_page=100&after={after}&_fields=id,content"))
    window = [ev_key(e) for e in events if e["tour"] in ("atp", "ch") and FROM.isoformat() <= e["start"] <= (FROM + timedelta(weeks=5)).isoformat()]
    byk = {ev_key(e): e for e in events}
    out, lists = {}, 0
    for post in posts:
        body = (post.get("content") or {}).get("rendered") or ""
        for sec in re.split(r"<h[23][^>]*>", body)[1:]:
            end = re.search(r"</h[23]>", sec)
            head, rest = (sec[:end.start()], sec[end.end():]) if end else (sec, "")
            head = html.unescape(re.sub(r"<[^>]+>", " ", head))
            if not re.search(r"ENTRY LIST", head, re.I) or re.search(r"QUALI|WTA", head, re.I):
                continue
            main, alt, out_, part = set(), set(), set(), "main"
            for raw in re.split(r"<br\s*/?>|</p>", rest):
                line = html.unescape(re.sub(r"<[^>]+>", "", raw)).strip()
                if re.match(r"ALTERNATE", line, re.I):
                    part = "alt"
                    continue
                m = re.match(r"^(?:\+|PR\b|OUT\b|IN\b|\d+|\s)*([^,\d()]+),([^\d()]+?)\s*(?:\(\d+\))?\s*(?:[A-Z]{3}\b)?[A-Z ]*\d+$", line)
                if not m:
                    continue
                k = pkey(m.group(2) + " " + m.group(1))
                if "<del" in raw or line.startswith("OUT"):  # Spazio strikes through withdrawals
                    out_.add(k)
                elif part == "main" or line.startswith("IN"):  # "IN": an alternate who has got into the main draw
                    main.add(k)
                else:
                    alt.add(k)
            if len(main) < 8:
                continue
            city = unicodedata.normalize("NFKD", head).encode("ascii", "ignore").decode().lower()
            city = re.sub(r"entry list|\batp\b|challenger|masters|\d+", " ", city)
            for it, en in IT_CITY.items():
                city = re.sub(rf"\b{it}\b", en, city)
            want = place_words(city)
            same = [k for k in window if want and want <= place_words(byk[k]["name"]) | place_words(byk[k]["place"])]
            score = sorted(((len(main & everyone.get(k, set())), k) for k in same), reverse=True)
            if not score or score[0][0] < max(4, len(main) * 0.4) or (len(score) > 1 and score[1][0] * 2 > score[0][0]):
                continue  # not a coming event in that city, or an old edition's list (too few of the same players)
            lists += 1
            for k in main | alt | out_:
                if k in men:
                    out[(men[k], score[0][1])] = "withdrawn" if k in out_ else "main" if k in main else "alt"
    if not lists:
        raise RuntimeError("no entry list could be matched to a coming event")
    return out


def ev_key(e):
    return (e.get("src"), e.get("name"), e.get("start"))


def atp_entries(events, errors):
    """72 men entered in ATP / Challenger events. A player is shown if any one of live-tennis.eu, Tick Tock Tennis or
    Spazio Tennis lists him for the event, unless any of them marks him as withdrawn. Each site can fail on its own;
    only if all three fail are yesterday's entries kept."""
    soon = sum(1 for e in events if e["tour"] in ("atp", "ch") and FROM.isoformat() <= e["start"] <= (FROM + timedelta(weeks=4)).isoformat())
    if not soon:
        return {}  # off-season: no ATP or Challenger events in the next few weeks
    need = min(15, soon)  # names that must match the calendar before the week columns are trusted
    men = {pkey(n): rid for rid, (n, t) in ROSTER.items() if t == "atp"}
    everyone, got = {}, {}

    def lt():
        out, ev, _ = lt_entries(events, men, need)
        for k, v in ev.items():
            everyone.setdefault(k, set()).update(v)
        return out
    for name, fn in (("live-tennis", lt), ("tick tock", lambda: tt_entries(events, men, need, everyone)),
                     ("spazio", lambda: sp_entries(events, men, everyone))):
        try:
            got[name] = fn()
        except Exception as x:
            print(f"ATP entries: {name} failed, carrying on with the others:", x)
            errors[f"atp-entries-{name.replace(' ', '').replace('-', '')}"] = {"at": NOW.isoformat(timespec="seconds"), "msg": str(x)[:200]}
    if not got:
        raise RuntimeError("none of live-tennis.eu, Tick Tock Tennis or Spazio Tennis could be read")
    lv, tt, sp = got.get("live-tennis", {}), got.get("tick tock", {}), got.get("spazio", {})
    found = {}
    for (rid, k) in sorted(lv.keys() | tt.keys() | sp.keys()):
        q, t, p = lv.get((rid, k)), tt.get((rid, k)), sp.get((rid, k))
        if "withdrawn" in (t, p):
            print("ATP entry left out (withdrawn):", rid, k[1])
            continue
        hows = {TT_HOW[t]} if t else set()
        if p:
            hows.add({"main": "Main draw", "alt": "Alternate"}[p])
        if q is not None and (q or not hows):
            hows.add("Qualifying" if q else "Entered")
        # the sites agree, or only one lists him: use its wording; if they disagree, just "Entered"
        how = hows.pop() if len(hows) == 1 else "Wildcard" if hows == {"Main draw", "Wildcard"} else "Entered"
        found.setdefault(k, []).append({"id": rid, "how": how})
    return found


# ---------------- ATP / Challenger: 72 players in a draw (data.json) ----------------
def draw_entries(events):
    d = load("data.json", {})
    words = lambda s: set(re.findall(r"[a-z]{4,}", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()))
    for m in d.get("matches") or []:
        cat = (m.get("category") or "").lower()
        tour = "ch" if cat.startswith("challenger") else "atp" if cat.startswith("atp") else None
        if not tour or not m.get("date"):
            continue
        rid = next((m.get(k) for k in ("p1Id", "p2Id") if m.get(k) in ROSTER and ROSTER[m.get(k)][1] == "atp"), None)
        if not rid:
            continue
        tw = words(m.get("tournament"))
        hits = [e for e in events if e["tour"] == tour and e["start"] <= m["date"] <= (date.fromisoformat(e["start"]) + timedelta(days=13)).isoformat()
                and tw & (words(e["name"]) | words(e["place"]))]
        if len(hits) == 1 and in_window(hits[0]["start"], hits[0]["end"]):
            e72 = hits[0].setdefault("e72", [])
            e72[:] = [x for x in e72 if x["id"] != rid] + [{"id": rid, "how": "In the draw"}]


def main():
    prev = load(OUT, {})
    old = {}
    for e in prev.get("events") or []:
        old.setdefault(e["tour"], []).append(e)
    errors, events, done = {}, [], {}

    def part(name, tours, fn):
        try:
            got = fn()
            if not got:
                raise RuntimeError("no events found")
            events.extend(got)
            done[name] = NOW.isoformat(timespec="seconds")
            print(f"{name}: {len(got)} events")
        except Exception as e:
            print(f"{name} failed, keeping the previous list:", e)
            errors[name] = {"at": NOW.isoformat(timespec="seconds"), "msg": str(e)[:200]}
            for t in tours:
                events.extend(x for x in old.get(t, []) if x.get("src") == name)
            if name in (prev.get("done") or {}):
                done[name] = prev["done"][name]

    def tag(src, fn):
        return lambda: [dict(e, src=src) for e in fn()]

    part("atp", ["atp"], tag("atp", lambda: atp_wiki(f"{YEAR}_ATP_Tour", "atp")))
    part("challenger", ["ch"], tag("challenger", lambda: atp_wiki(f"{YEAR}_ATP_Challenger_Tour", "ch")))
    part("wta", ["wta", "itfw"], tag("wta", wta_events))
    itf_ok = True
    for circuit, tour, name in (("MT", "itfm", "itf-men"), ("WT", "itfw", "itf-women"), ("JT", "jun", "itf-juniors")):
        if itf_ok:
            part(name, [tour], tag(name, lambda c=circuit, t=tour: itf_events(c, t)))
            itf_ok = name not in errors or "bot check" not in errors[name]["msg"]
        else:
            errors[name] = {"at": NOW.isoformat(timespec="seconds"), "msg": "skipped: the ITF bot check was shown"}
            events.extend(x for x in old.get(tour, []) if x.get("src") == name)
    TE = None

    def te_all():
        nonlocal TE
        TE = te_session()
        return te_events(TE)
    part("te", ["te"], tag("te", te_all))

    events = [e for e in events if e.get("start") and e.get("end") and e["end"] >= FROM.isoformat() and e["start"] <= TO.isoformat()]
    for e in events:
        e["tier"] = tier(e["tour"], e["cat"])
        e.pop("e72", None)

    # ---- 72 entries, only for events whose entry lists are out ----
    prev_e72 = {(e.get("src"), e.get("name"), e.get("start")): e.get("e72") for e in prev.get("events") or [] if e.get("e72")}
    wta72 = {key(n): rid for rid, (n, t) in ROSTER.items() if t == "wta"}
    ids = {**(load("titles.json", {}).get("ids") or {})}
    for rid, p in (load("itf.json", {}).get("players") or {}).items():
        if p.get("itfId"):
            ids[rid] = p["itfId"]
    itf72 = {int(v): rid for rid, v in ids.items() if v}
    itf_blocked = not itf_ok
    for e in sorted(events, key=lambda e: e["start"]):
        if not in_window(e["start"], e["end"]):
            continue
        try:
            if e.get("wtaId"):
                e["e72"] = wta_entries(e, wta72)
            elif e.get("itfKey") and not itf_blocked:
                e["e72"] = itf_entries(e, itf72)
            elif e.get("itfKey"):
                e["e72"] = prev_e72.get((e.get("src"), e["name"], e["start"])) or []
        except Blocked as x:
            print("ITF bot check on acceptance lists, keeping the previous ones:", x)
            itf_blocked = True
            errors["itf-entries"] = {"at": NOW.isoformat(timespec="seconds"), "msg": "the ITF bot check was shown"}
            e["e72"] = prev_e72.get((e.get("src"), e["name"], e["start"])) or []
        except Exception as x:
            print("entry list failed", e["name"], x)
            e["e72"] = prev_e72.get((e.get("src"), e["name"], e["start"])) or []
    if TE:
        try:
            byid = te_entries(TE, load("te.json", {}).get("profiles") or {})
            for e in events:
                if e.get("teId") in byid and in_window(e["start"], e["end"]):
                    e["e72"] = byid[e["teId"]]
        except Exception as x:
            print("Tennis Europe entries failed:", x)
            errors["te-entries"] = {"at": NOW.isoformat(timespec="seconds"), "msg": str(x)[:200]}
    atp_window = [e for e in events if e["tour"] in ("atp", "ch") and in_window(e["start"], e["end"])]
    try:
        byev = atp_entries(events, errors)
        for e in atp_window:
            e["e72"] = byev.get(ev_key(e), [])
    except Exception as x:
        print("ATP / Challenger entries failed, keeping the previous ones:", x)
        errors["atp-entries"] = {"at": NOW.isoformat(timespec="seconds"), "msg": str(x)[:200]}
        for e in atp_window:
            e["e72"] = [p for p in prev_e72.get(ev_key(e)) or [] if p["how"] != "In the draw"]
    draw_entries(events)

    for e in events:
        for k in ("wtaId", "year", "itfKey", "circuit", "teId"):
            e.pop(k, None)
        if not e.get("e72"):
            e.pop("e72", None)
    events.sort(key=lambda e: (e["start"], e["tier"], e["name"]))
    data = {"updated": NOW.isoformat(timespec="seconds"), "from": FROM.isoformat(), "to": TO.isoformat(),
            "entriesTo": (T + timedelta(days=ENTRY_DAYS)).isoformat(), "done": done, "errors": errors, "events": events}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"schedule.json: {len(events)} events, {sum(1 for e in events if e.get('e72'))} with 72 players entered, errors: {list(errors)}")


if __name__ == "__main__":
    main()

