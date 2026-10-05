"""
72 Central - every player's match results since 2023 (runs inside the 'Update scores' workflow, once a day, no Claude).

Writes results/<roster id>.json (one file per player, opened by the "All results" button on their profile) and
results.json (what was checked, and when). Each file lists the player's singles events, newest first, with every
match: date, round, opponent, score (from the player's side) and W/L.

Sources (all free, no key):
  - ITF (itftennis.com, the same player activity the ITF titles use): every official singles match, Grand Slams,
    ATP/WTA Tour, Challengers, WTA 125, ITF World Tennis Tour, Davis Cup / Billie Jean King Cup and ITF Juniors,
    with each event's real category (that sets its colour on the site). Stops at the ITF bot check.
  - Tennis Explorer (tennisexplorer.com, already used for rankings): exhibitions and other non-tour events
    (UTS, Kooyong, Boodles, Laver Cup...) and the exact day of each match. Events that are also on the ITF's records
    are taken from the ITF; only the ones the ITF doesn't have are added from Tennis Explorer.
  - Tennis Europe (U14/U16): te.json's matches are kept here as they come in (te.json only holds recent days).
Loads each player's results since 2023 once, then this year's every day from 08:00 UK. A player that can't be read
keeps their saved results and is listed under 'pending' (report_gaps.py alerts). Nothing is guessed: a Tennis
Explorer profile is only used once its matches agree with the ITF's records.
"""
import html, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from update import ROSTER  # roster id -> (name, "atp" / "wta")

ITF = "https://www.itftennis.com/tennis/api"
TEX = "https://www.tennisexplorer.com"
UA = "72CentralResults/1.0 (+https://github.com/tlock72/72-central; once a day, one request every few seconds)"
PAUSE = {"itf": 4, "tex": 3}
FROM_YEAR = 2023
VERSION = 1  # bump to make every player be loaded again from 2023
BUDGET = timedelta(minutes=6)  # players not reached in time are picked up by the next run
OUT_DIR = "results"
STATE = "results.json"
UK = ZoneInfo("Europe/London")
NOW = datetime.now(timezone.utc)
UK_NOW = NOW.astimezone(UK)
T = UK_NOW.date()
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
# events not on the ITF's records: team events by name, exhibitions by these words, anything else is "Other event"
TEAM = ("united cup", "laver cup", "hopman cup", "davis cup", "billie jean king cup", "fed cup")
EXHIBITION = ("exh", "showdown", "world tennis league", "six kings", "bundesliga", "boodles", "hurlingham", "kooyong",
              "mubadala", "battle of", "tie break tens", "giorgio armani", "a day at the drive", "liga", "league", "charity")


class Blocked(Exception):
    pass


def get(url, kind):
    time.sleep(PAUSE[kind])
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/html"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z]+", s))


def skey(surname):
    """Surname key: 'De Minaur' / 'de Minaur' / 'Schwärzler' / 'Schwaerzler' all compare equal."""
    return re.sub(r"(ae|oe|ue)", lambda m: m.group(0)[0], norm(surname).replace(" ", ""))


def same_surname(a, b):
    return bool(a and b) and (a == b or (min(len(a), len(b)) >= 4 and (a.endswith(b) or b.endswith(a))))


def short(first, last):
    first = (first or "").strip()
    return f"{first[0]}. {last}".strip() if first else (last or "").strip()


# ---------------- categories: same importance scale as the tour schedule (1 = biggest) ----------------
def itf_category(t, circuit):
    """(label, tier, team) for one ITF activity item. Tier 0 = not known (shown grey, never guessed)."""
    typ, code, name = t.get("tournamentType") or "", (t.get("tourCode") or "").upper(), t.get("tournamentName") or ""
    s = f"{typ} {code} {name}".lower()
    tour = "ATP" if circuit == "MT" else "WTA"
    if circuit == "JT":
        if code == "JGS" or "grand slam" in typ.lower():
            return "Junior Grand Slam", 5, 0
        m = re.search(r"\bj(\d{2,3})\b", f"{code} {typ}".lower())
        n = int(m[1]) if m else 0
        if code == "JA" or n >= 500:
            return f"ITF Juniors {code or 'J500'}", 5, 0
        return (f"ITF Juniors {code}" if code else "ITF Juniors"), (6 if n >= 300 else 7 if n >= 200 else 8), 0
    if code == "SL" or "grand slam" in typ.lower():
        return "Grand Slam", 1, 0
    if "next gen" in s:
        return "Next Gen Finals", 3, 0
    if code == "TF" or "finals" in typ.lower():
        return f"{tour} Finals", 1, 0
    if any(w in s for w in TEAM) or code in ("DC", "BJK", "FC"):
        return (typ if typ and not typ.isdigit() else name), 3, 1
    if "olympic" in s:
        return "Olympics", 2, 0
    if code == "CH" or "challenger" in s:
        m = re.search(r"challenger\s*(\d{2,3})", s)
        n = int(m[1]) if m else 0
        return (f"Challenger {n}" if n else "Challenger"), (5 if n >= 125 else 6 if n >= 75 or not n else 7), 0
    if code == "ITF" or typ in ("ITF World Tennis Tour", "Futures", "ITF Womens Circuit"):
        m = re.match(r"([MW])(\d{2,3})\b", name)
        if m:
            n = int(m[2])
            return f"ITF {m[1]}{n}", (5 if n >= 125 else 6 if n >= 75 else 7 if n >= 25 else 8), 0
        m = re.match(r"\$([\d,]+)", name)
        if m:
            n = int(m[1].replace(",", "")) // 1000
            return f"ITF ${n}K", (6 if n >= 75 else 7 if n >= 25 else 8), 0
        return ("Futures" if typ == "Futures" else "ITF"), 8, 0
    m = re.search(r"\b(1000|500|250|125)\b", f"{typ} {code}")
    if m:
        n = int(m[1])
        return f"{tour} {n}", {1000: 2, 500: 3, 250: 4, 125: 5}[n], 0
    print("  unknown ITF category:", typ, code, name)
    return typ or "Other", 0, 0


def te_category(name):
    """(label, tier, team) for a Tennis Explorer event the ITF doesn't have."""
    s = name.lower()
    if any(w in s for w in TEAM):
        return re.sub(r"\s*-\s*exh\.?$", "", name), 3, 1
    if any(w in s for w in EXHIBITION):
        return "Exhibition", 9, 0
    return "Other event", 0, 0


# ---------------- ITF ----------------
def itf_dates(s):
    """'29 Dec to 04 Jan 2026' -> (2025-12-29, 2026-01-04)."""
    m = re.search(r"(\d{1,2}) (\w{3})\w* to (\d{1,2}) (\w{3})\w* (\d{4})", s or "")
    if not m:
        return None, None
    y, m1, m2 = int(m[5]), MONTHS.get(m[2].lower()), MONTHS.get(m[4].lower())
    if not m1 or not m2:
        return None, None
    return date(y - (1 if m1 > m2 else 0), m1, int(m[1])), date(y, m2, int(m[3]))


ROUND = {"1st round": "R1", "2nd round": "R2", "3rd round": "R3", "4th round": "R4", "round of 128": "R128",
         "round of 64": "R64", "round of 32": "R32", "round of 16": "R16", "quarter-final": "QF", "quarterfinal": "QF",
         "quarter final": "QF", "semi-final": "SF", "semifinal": "SF", "semi final": "SF", "final": "F",
         "round robin": "RR", "group": "RR"}


def itf_round(value, draw):
    v = (value or "").strip()
    if re.search(r"world group|play.?off|tie", v, re.I):
        return ""  # Davis Cup / Billie Jean King Cup stages: the event name says it
    r = "RR" if re.search(r"group|round robin", v, re.I) and not re.search(r"world group", v, re.I) else ROUND.get(v.lower(), v)
    if "qual" in (draw or "").lower():
        return "Q" + r[1:] if re.match(r"^R\d$", r) else f"Q-{r}"
    return r


def itf_score(m):
    sets = []
    for s in m.get("scores") or []:
        a, b, tb = s.get("scoreOne"), s.get("scoreTwo"), s.get("losingScore")
        if a is None or b is None:
            continue
        sets.append(f"{a}-{b}" + (f"({tb})" if tb is not None else ""))
    out = ", ".join(sets)
    st = (m.get("resultStatusCode") or "").upper()
    if st in ("RET", "RTD"):
        out += " ret."
    elif st in ("DEF", "DQ"):
        out += " def."
    elif st and st not in ("WO", "W/O"):
        out += f" ({st.lower()})"
    return out.strip()


def itf_events(pid, circuit, since):
    """This player's singles events on one ITF circuit (MT men, WT women, JT juniors) that ended in `since` or later."""
    out, skip = [], 0
    while True:
        body = get(f"{ITF}/PlayerApi/GetPlayerActivity?" + urllib.parse.urlencode(
            dict(circuitCode=circuit, matchTypeCode="S", playerId=pid, skip=skip, take=50)), "itf")
        if not body.lstrip().startswith(("{", "[")):
            raise Blocked("ITF answered with its bot check, stopping")
        act = json.loads(body)
        items = act.get("items") or []
        older = False
        for t in items:
            start, end = itf_dates(t.get("dates"))
            if not end:
                raise ValueError(f"unreadable dates {t.get('dates')!r} at {t.get('tournamentName')}")
            if end.year < since:
                older = True
                continue
            label, tier, team = itf_category(t, circuit)
            ms = []
            for ev in t.get("events") or []:
                if (ev.get("matchType") or "singles").lower() != "singles":
                    continue  # asked for singles; Davis Cup leaves this blank
                for m in ev.get("matches") or []:
                    rc, st = (m.get("resultCode") or "").upper(), (m.get("resultStatusCode") or "").upper()
                    if rc in ("", "B") or st == "BYE":
                        continue  # not played yet, or a bye
                    if rc not in ("W", "L", "O"):
                        raise ValueError(f"result code {rc!r} at {t.get('tournamentName')}")
                    opp = (m.get("opponents") or [{}])[0]
                    ms.append({"d": None, "r": itf_round((m.get("roundGroup") or {}).get("Value"), ev.get("drawType")),
                               "o": short(opp.get("givenName"), opp.get("familyName")), "oc": opp.get("nationality") or "",
                               "ok": skey(opp.get("familyName")), "s": itf_score(m), "res": "L" if rc == "L" else "W",
                               "wo": 1 if rc == "O" or st in ("WO", "W/O") else 0})
            if ms:
                out.append({"y": end.year, "t": t.get("tournamentName") or "", "c": label, "k": tier, "team": team,
                            "w0": start.isoformat(), "w1": end.isoformat(), "sf": t.get("surfaceDesc") or "",
                            "src": "itf", "link": "https://www.itftennis.com" + (t.get("tournamentLink") or ""), "m": ms})
        skip += len(items)
        if not items or older or skip >= (act.get("totalItems") or 0):
            return out


# ---------------- Tennis Explorer ----------------
def tex_set(s):
    """'7-6<sup>2</sup>' -> (7, 6, 2); '6<sup>2</sup>-7' -> (6, 7, 2); '13-8' -> (13, 8, None)."""
    m = re.match(r"\s*(\d+)(?:<sup>(\d+)</sup>)?-(\d+)(?:<sup>(\d+)</sup>)?\s*$", s)
    if not m:
        return None
    return int(m[1]), int(m[3]), m[2] or m[4]


def tex_score(raw, won):
    """Tennis Explorer writes the winner's games first; turn it round to the player's side."""
    out = []
    for part in re.sub(r"</?a[^>]*>", "", raw).split(","):
        s = tex_set(part)
        if not s:
            txt = html.unescape(re.sub(r"<[^>]+>", "", part)).strip()
            if txt:
                out.append(txt)
            continue
        a, b, tb = s
        if not won:
            a, b = b, a
        out.append(f"{a}-{b}" + (f"({tb})" if tb else ""))
    return ", ".join(out)


def tex_round(r):
    r = html.unescape(re.sub(r"<[^>]+>", "", r or "")).strip()
    q = r.startswith("Q-")
    r = r[2:] if q else r
    m = re.match(r"^(\d)R$", r)
    if m:
        r = f"R{m[1]}"
    return ("Q" + r[1:] if re.match(r"^R\d$", r) else f"Q-{r}") if q else r


def tex_events(page, since):
    """Singles events from a Tennis Explorer player page, from `since` on: [{y, t, sf, m: [{d, o, ok, r, s, res}]}]."""
    out = []
    for sec in re.finditer(r'<div id="matches-(\d{4})-1-data"', page):
        year = int(sec[1])
        if year < since:
            continue
        body = page[sec.end():]
        stop = body.find('-2-data"')
        body = body[:stop if stop > 0 else len(body)]
        ev = None
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
            head = re.search(r'<td class="t-name" colspan="3"><a href="[^"]*">(.*?)</a>', tr, re.S)
            if head:
                ev = {"y": year, "t": html.unescape(re.sub(r"<[^>]+>|&nbsp;", "", head[1])).strip(), "sf": "", "m": []}
                out.append(ev)
                continue
            if ev is None or 'class="first time"' not in tr:
                continue
            dm = re.search(r'class="first time">\s*(\d{1,2})\.(\d{1,2})\.', tr)
            names = re.search(r'<td class="t-name">(.*?)</td>', tr, re.S)
            sc = re.search(r'title="Click for match detail">(.*?)</a>', tr, re.S)
            if not (dm and names and sc):
                continue
            players = re.findall(r'<a href="/player/[^"]*"( class="notU")?>(.*?)</a>', names[1], re.S)
            if len(players) != 2 or sum(1 for p in players if p[0]) != 1:
                continue
            won = bool(players[0][0])  # the winner is always listed first
            opp = html.unescape(re.sub(r"<[^>]+>", "", players[1][1] if won else players[0][1])).strip()
            parts = opp.split()
            while len(parts) > 1 and re.match(r"^[A-Z][a-z]?\.$|^[A-Z]\.-?[A-Z]?\.?$", parts[-1]):
                parts.pop()  # "De Minaur A." -> "De Minaur"
            initial = opp[len(" ".join(parts)):].strip()
            d = date(year, int(dm[2]), int(dm[1]))
            surf = re.search(r'class="s-color"><span title="([^"]+)"', tr)
            if surf and not ev["sf"]:
                ev["sf"] = surf[1].capitalize()
            rd = re.search(r'<td class="round"[^>]*>(.*?)</td>', tr, re.S)
            ev["m"].append({"d": d.isoformat(), "o": f"{initial} {' '.join(parts)}".strip(), "ok": skey(" ".join(parts)),
                            "r": tex_round(rd[1] if rd else ""), "s": tex_score(sc[1], won), "res": "W" if won else "L"})
    for e in out:  # an event that ends in January (United Cup): its December days are in the year before
        if any(m["d"][5:7] == "01" for m in e["m"]):
            for m in e["m"]:
                if m["d"][5:7] == "12":
                    m["d"] = f"{e['y'] - 1}{m['d'][4:]}"
    return [e for e in out if e["m"]]


def tex_find(name, itf_known):
    """Tennis Explorer profile for a roster name, only when its matches agree with the player's ITF matches."""
    words = norm(name).split()
    cands = []
    for w in sorted(set(words), key=len, reverse=True)[:2]:
        page = get(f"{TEX}/list-players/?search-text-pl={urllib.parse.quote(w)}", "tex")
        for slug, nm in re.findall(r'<a href="/player/([^/"]+)/"[^>]*>([^<]+)</a>', page):
            have = norm(html.unescape(nm)).split()
            if (set(words) <= set(have) or (len(have) >= 2 and set(have) <= set(words))) and slug not in [c for c, _ in cands]:
                cands.append((slug, nm))
        if cands:
            break
    best = (0, None, None)
    for slug, _ in cands[:4]:
        page = get(f"{TEX}/player/{slug}/?annual=all", "tex")
        evs = tex_events(page, FROM_YEAR)
        n = sum(1 for e in evs for m in e["m"] if find_itf(m, itf_known))
        if n > best[0]:
            best = (n, slug, evs)
    return best[1], best[2]


def find_itf(tm, events):
    """The ITF match a Tennis Explorer match is: same opponent, in that event's dates (or the week before, for qualifying)."""
    d = date.fromisoformat(tm["d"])
    for before in (1, 9):
        for e in events:
            if e.get("src") != "itf" or not (date.fromisoformat(e["w0"]) - timedelta(days=before) <= d <= date.fromisoformat(e["w1"]) + timedelta(days=1)):
                continue
            for m in e["m"]:
                if same_surname(m.get("ok"), tm["ok"]):
                    return e, m
    return None


def merge(itf, tex):
    """ITF events, with Tennis Explorer's exact days added, plus the Tennis Explorer events the ITF doesn't have."""
    extra = []
    for te in tex:
        hits = [find_itf(m, itf) for m in te["m"]]
        if any(hits):
            for m, h in zip(te["m"], hits):
                if h and not h[1]["d"]:
                    h[1]["d"] = m["d"]
            continue
        label, tier, team = te_category(te["t"])
        ds = sorted(m["d"] for m in te["m"])
        if not tier and ds[-1] >= (T - timedelta(days=21)).isoformat():
            continue  # most likely an event the ITF hasn't listed yet: wait for it rather than call it "Other"
        extra.append({"y": te["y"], "t": re.sub(r"\s*-\s*exh\.?$", "", te["t"]), "c": label, "k": tier, "team": team,
                      "w0": ds[0], "w1": ds[-1], "sf": te["sf"], "src": "tex", "m": [dict(m, oc="", wo=0) for m in te["m"]]})
    return itf + extra


# ---------------- Tennis Europe (from te.json) ----------------
def te_tier(cat):
    c = (cat or "").lower()
    return 5 if any(w in c for w in ("super", "masters", "european championship")) else 6 if c.endswith("1") else 7 if c.endswith("2") else 8


def archive_te(state):
    """Keep every finished Tennis Europe match te.json has shown (it only holds recent days). Returns changed ids."""
    arch, changed = state.setdefault("teArchive", {}), set()
    for m in load("te.json", {}).get("matches") or []:
        if m.get("status") != "finished" or not m.get("score"):
            continue
        rid = m.get("p1Id") or m.get("p2Id")
        if rid not in ROSTER:
            continue
        if m.get("winner") not in (1, 2):
            continue
        won = (m.get("winner") == 1) == (m.get("p1Id") == rid)
        sets = []
        for s in re.sub(r"\s*ret\.?$", "", m["score"]).split(","):
            x = re.match(r"\s*(\d+)-(\d+)(\(\d+\))?", s)
            if x:
                a, b = (x[1], x[2]) if won else (x[2], x[1])
                sets.append(f"{a}-{b}{x[3] or ''}")
        score = ", ".join(sets) + (" ret." if m["score"].rstrip().endswith("ret.") else "")
        opp = m.get("p2") if m.get("p1Id") == rid else m.get("p1")
        cat = (m.get("category") or "").split("·")[-1].strip()
        row = {"id": m.get("matchId"), "y": int(m["date"][:4]), "t": m.get("tournament") or "", "c": m.get("category") or "Tennis Europe",
               "k": te_tier(cat), "d": m["date"], "r": re.sub(r"\s*\(walkover\)", "", m.get("round") or ""), "o": opp or "",
               "s": score, "res": "W" if won else "L", "wo": 1 if "walkover" in (m.get("round") or "") else 0, "link": m.get("link") or ""}
        lst = arch.setdefault(rid, [])
        old = next((i for i, r in enumerate(lst) if r["id"] == row["id"]), None)
        if old is None:
            lst.append(row); changed.add(rid)
        elif lst[old] != row:
            lst[old] = row; changed.add(rid)
    return changed


def te_events(rows):
    by = {}
    for r in sorted(rows, key=lambda r: r["d"]):
        e = by.setdefault((r["y"], r["t"], r["c"]), {"y": r["y"], "t": r["t"], "c": r["c"], "k": r["k"], "team": 0, "w0": r["d"],
                                                     "w1": r["d"], "sf": "", "src": "te", "link": r["link"], "m": []})
        e["w1"] = r["d"]
        e["m"].append({k: r[k] for k in ("d", "r", "o", "s", "res", "wo")} | {"oc": ""})
    return list(by.values())


# ---------------- per-player file ----------------
STAGE = ["Q-", "Q1", "Q2", "Q3", "R128", "R64", "R1", "R32", "R2", "R3", "R16", "R4", "RR", "QF", "SF", "F"]


def stage(r):
    return STAGE.index(r) if r in STAGE else (0 if r.startswith("Q") else 12)


def tidy(events):
    for e in events:
        dated = all(m["d"] for m in e["m"])  # by day when every match has one, else by round
        e["m"].sort(key=lambda m: (m["d"], stage(m["r"])) if dated else (stage(m["r"]), m["d"] or ""), reverse=True)
        for m in e["m"]:
            m.pop("ok", None)
    return sorted(events, key=lambda e: (e["w1"], e["w0"]), reverse=True)


def main():
    state = load(STATE, {})
    if state.get("v") != VERSION:
        state = {"v": VERSION, "teArchive": state.get("teArchive", {}), "tex": state.get("tex", {})}
    os.makedirs(OUT_DIR, exist_ok=True)
    today = T.isoformat()
    full = state.setdefault("full", [])
    tex_slugs, tex_looked = state.setdefault("tex", {}), state.setdefault("texLooked", {})
    jt = state.setdefault("jt", {})
    te_changed = archive_te(state)

    daily = state.get("checked") != today and UK_NOW.hour >= 8
    need_full = [r for r in ROSTER if r not in full]
    if state.get("todo"):
        order = state["todo"]
    elif daily:
        order = list(ROSTER)
    elif need_full:
        order = need_full
    else:
        order = []
    state["tried"] = NOW.strftime("%Y-%m-%dT%H:%M:%SZ") if order else state.get("tried")

    titles, juniors = load("titles.json", {}), load("itf.json", {}).get("players") or {}
    ids = {r: (juniors.get(r) or {}).get("itfId") or (titles.get("ids") or {}).get(r) for r in ROSTER}
    pending, todo, blocked = [], [], False
    for rid in order:
        if rid not in ROSTER:
            continue
        if blocked or datetime.now(timezone.utc) - NOW > BUDGET:
            (pending if blocked else todo).append(rid)
            continue
        name, tour = ROSTER[rid]
        career = rid not in full
        since = FROM_YEAR if career else T.year - (1 if T.month == 1 else 0)
        path = os.path.join(OUT_DIR, f"{rid}.json")
        old = load(path, {}).get("events") or []
        try:
            itf = []
            if ids.get(rid):
                itf = itf_events(ids[rid], "MT" if tour == "atp" else "WT", since)
                if career or jt.get(rid):
                    j = itf_events(ids[rid], "JT", since)
                    if career:
                        jt[rid] = bool(j)
                    itf += j
            # Tennis Explorer: only for players the ITF knows (its matches are checked against the ITF's)
            tex, tex_ok = [], True
            if ids.get(rid):
                try:
                    known = itf + [e for e in old if e.get("src") == "itf"]
                    slug = tex_slugs.get(rid)
                    if not slug and tex_looked.get(rid, "") <= (T - timedelta(days=30)).isoformat():
                        slug, evs = tex_find(name, known)
                        tex_looked[rid] = today
                        if slug:
                            tex_slugs[rid] = slug
                            tex = [e for e in evs if e["y"] >= since]
                            print(f"{name}: Tennis Explorer profile {slug}")
                    elif slug:
                        page = get(f"{TEX}/player/{slug}/?annual={'all' if career else T.year}", "tex")
                        tex = tex_events(page, since)
                        if since < T.year and not career:
                            tex += tex_events(get(f"{TEX}/player/{slug}/?annual={since}", "tex"), since)
                except Exception as e:
                    print(f"{name}: Tennis Explorer not read ({e}), keeping saved exhibitions")
                    tex_ok = False
            events = merge(itf, tex)
            keep = [e for e in old if e.get("src") != "te" and (e["y"] < since or (not tex_ok and e.get("src") == "tex"))]
            events = tidy(keep + events + te_events(state["teArchive"].get(rid, [])))
            data = {"id": rid, "name": name, "from": FROM_YEAR, "events": events}
            if load(path, {}).get("events") != events:
                data["updated"] = today
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
                    f.write("\n")
            if career:
                full.append(rid)
            print(f"{name}: {sum(len(e['m']) for e in events)} matches in {len(events)} events" + (" (loaded from 2023)" if career else ""))
            te_changed.discard(rid)
        except Blocked as e:
            print(e); blocked = True; pending.append(rid)
        except Exception as e:  # network hiccup or something unreadable: keep the saved results, retry later
            print("failed", name, e); pending.append(rid)

    # new Tennis Europe matches for players not refreshed above
    for rid in te_changed:
        path = os.path.join(OUT_DIR, f"{rid}.json")
        old = load(path, {"id": rid, "name": ROSTER[rid][0], "from": FROM_YEAR, "events": []})
        old["events"] = tidy([e for e in old["events"] if e.get("src") != "te"] + te_events(state["teArchive"].get(rid, [])))
        old["updated"] = today
        with open(path, "w", encoding="utf-8") as f:
            json.dump(old, f, ensure_ascii=False, separators=(",", ":"))
            f.write("\n")

    # players no longer on the roster drop out
    for f in os.listdir(OUT_DIR):
        if f.endswith(".json") and f[:-5] not in ROSTER:
            os.remove(os.path.join(OUT_DIR, f))
    state["full"] = [r for r in full if r in ROSTER]
    if order:
        state["pending"], state["todo"] = pending, todo
        if daily and not todo:
            state["checked"] = today
    state["source"] = "ITF player activity (itftennis.com), Tennis Explorer (exhibitions, match days), Tennis Europe"
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"done: {len(state['full'])}/{len(ROSTER)} players loaded from {FROM_YEAR}, {len(pending)} pending, {len(todo)} for the next run")


if __name__ == "__main__":
    main()
