"""
72 Central - Scouting HQ (runs inside the "Update scores" GitHub Action, no Claude needed).

Builds scouting.json: every ranked ATP and WTA singles player (the website filters by age, birth
year and ranking), with birth year, current official ranking and how far they have moved in the
last week, 3 months (13 weeks) and 12 months (52 weeks).
A move of -1 means "not tracked then". Until 5 Oct 2026 the ATP history kept only players aged
about 23 or under; those weeks are now filled in for every player from Tennis Explorer (a few
weeks per run, the weeks the current page compares with first).

Sources (both free, no key):
  - ATP: Tennis Abstract's weekly ranking report (official ATP ranking + date of birth)
         https://www.tennisabstract.com/reports/atpRankings.html
         Past ATP weeks come from scouting_history.json, which this script adds to every week.
         Older weeks that only held young players are filled in once from Tennis Explorer's past
         weekly ATP rankings (https://www.tennisexplorer.com/ranking/atp-men/?date=YYYY-MM-DD), after
         checking that Tennis Explorer agrees with Tennis Abstract on a recent week.
  - WTA: the official WTA rankings feed (api.wtatennis.com), which also serves past weeks.

It only does work when something is new: at most one check every 3 hours, and it rebuilds
when either tour has published a new ranking week (or when RANKINGS=1 / FORCE=1).
"""
import html, json, os, re, sys, time, unicodedata, urllib.request
from datetime import date, datetime, timedelta, timezone

UA = "72CentralScouting/1.0 (+https://github.com/tlock72/72-central; weekly, a few requests)"
TA_URL = "https://www.tennisabstract.com/reports/atpRankings.html"
TE_URL = "https://www.tennisexplorer.com/ranking/atp-men/?date={d}&page={p}"
TE_WEEKS = 5  # past ATP weeks filled in per run (about 45 pages each)
WTA_URL = "https://api.wtatennis.com/tennis/players/ranked?page={p}&pageSize=100&type=rankSingles&sort=asc&metric=SINGLES"
OUT, HIST = "scouting.json", "scouting_history.json"
NOW = datetime.now(timezone.utc)
FORCE = os.environ.get("RANKINGS") == "1" or os.environ.get("FORCE") == "1"
BACK = {"w": 7, "m3": 91, "m12": 364}  # 1 week, 13 weeks, 52 weeks
AGES = "all"  # scouting.json holds every age; an older file (young players only) is rebuilt once


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/html"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save(path, obj, compact=False):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":") if compact else None,
                  indent=None if compact else 0)
        f.write("\n")


def key(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", s)


def monday(d):
    return d - timedelta(days=d.weekday())


# ---------------- ATP (Tennis Abstract) ----------------
def atp_current():
    page = get(TA_URL)
    m = re.search(r"Last update:\s*(\d{4}-\d{2}-\d{2})", page)
    if not m:
        raise RuntimeError("Tennis Abstract page has no update date")
    week = monday(date.fromisoformat(m.group(1))).isoformat()
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", page, re.S):
        tds = [html.unescape(re.sub(r"<[^>]+>", "", td)).replace("\xa0", " ").strip()
               for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(tds) == 4 and tds[0].isdigit():
            link = re.search(r"player\.cgi\?p=([^\"'&]+)", tr)
            rows.append({"rank": int(tds[0]), "name": tds[1], "cty": tds[2], "dob": tds[3],
                         "url": f"https://www.tennisabstract.com/cgi-bin/player.cgi?p={link.group(1)}" if link else None})
    if len(rows) < 1000:
        raise RuntimeError(f"Tennis Abstract list looks short ({len(rows)} players)")
    return week, rows


def snapshot_rank(snap, k):
    """Rank of player-key k in a history snapshot; tolerates longer/shorter name forms (e.g. second surnames)."""
    if k in snap:
        return snap[k]
    if len(k) >= 8:
        hits = [v for s, v in snap.items() if len(s) >= 8 and (s.startswith(k) or k.startswith(s))]
        if len(hits) == 1:
            return hits[0]
    return None


def tok(name):
    """Name key that ignores word order: Tennis Explorer writes "De Minaur Alex", Tennis Abstract "Alex De Minaur"."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return " ".join(sorted(re.sub(r"(ae|oe|ue)", lambda m: m.group(0)[0], w) for w in re.findall(r"[a-z]+", s)))


def te_week(d):
    """Every player in Tennis Explorer's ATP ranking of week d, as {tok(name): rank}. None if it has no list for that week."""
    seen = {}
    for p in range(1, 90):
        page = get(TE_URL.format(d=d, p=p))
        if p == 1 and not re.search(r'<option value="%s" selected' % d, page):
            return None  # Tennis Explorer has no ranking for that date (it shows another week instead)
        n = 0
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
            m = re.search(r'class="rank first">\s*(\d+)\.\s*</td>.*?class="t-name"><a href="/player/[^"]*">([^<]+)</a>', tr, re.S)
            if m:
                n += 1
                seen.setdefault(tok(html.unescape(m.group(2))), []).append(int(m.group(1)))
        if not n:
            break
        time.sleep(0.3)
    if len(seen) < 1000:
        raise RuntimeError(f"Tennis Explorer list for {d} looks short ({len(seen)} players)")
    return {k: v[0] for k, v in seen.items() if len(v) == 1}  # two players with the same name: leave both out


def backfill_atp(hist, rows, priority):
    """Fill in past ATP weeks that only hold young players, from Tennis Explorer. Returns the weeks filled.
    A filled week is stored as {"_tok": 1, tok(name): rank} for every ranked player that week."""
    weeks = hist["atp"]
    skip = set(hist.get("teSkip", []))
    todo = [w for w in weeks if "_all" not in weeks[w] and "_tok" not in weeks[w] and w not in skip]
    if not todo:
        return set()
    # first check Tennis Explorer agrees with Tennis Abstract on the newest full week
    full = max((w for w in weeks if "_all" in weeks[w]), default=None)
    te = te_week(full) if full else None
    if not te:
        print("Scouting HQ: ATP history fill skipped, no Tennis Explorer list to check against")
        return set()
    both = [(weeks[full][key(r["name"])], te[tok(r["name"])]) for r in rows
            if key(r["name"]) in weeks[full] and tok(r["name"]) in te]
    same = sum(a == b for a, b in both)
    print(f"Scouting HQ: Tennis Explorer check on {full}: {len(both)}/{len(rows)} matched, {same} same rank")
    if len(both) < 0.9 * len(rows) or same < 0.99 * len(both):
        print("Scouting HQ: Tennis Explorer does not agree with Tennis Abstract, ATP history fill skipped")
        return set()
    seen = set(hist.get("teSeen", [])) | set(te)
    done = set()
    for w in sorted(todo, key=lambda w: (w not in priority, w))[:TE_WEEKS]:
        lst = te_week(w)
        if lst is None:
            skip.add(w)
            print("Scouting HQ: Tennis Explorer has no ATP ranking for", w)
            continue
        weeks[w] = {"_tok": 1, **lst}
        seen |= set(lst)
        done.add(w)
        print(f"Scouting HQ: ATP week {w} filled in for every player ({len(lst)})")
    hist["teSeen"] = sorted(seen)
    hist["teSkip"] = sorted(skip)
    return done


def te_refresh(hist):
    """On a new ATP week, add Tennis Explorer's names to teSeen (tells "not ranked then" from "name not matched")."""
    weeks = hist["atp"]
    w = max((w for w in weeks if "_all" in weeks[w]), default=None)
    if not w or not any("_tok" in v for v in weeks.values()) or hist.get("teSeenWeek") == w:
        return
    lst = te_week(w)
    if lst:
        hist["teSeen"] = sorted(set(hist.get("teSeen", [])) | set(lst))
        hist["teSeenWeek"] = w


def pick_week(weeks, target):
    """Latest stored ranking week on or before target (the ranking that was in force then)."""
    best = None
    for w in weeks:
        if w <= target and (best is None or w > best):
            best = w
    return best


# ---------------- WTA (official feed) ----------------
def wta_list(at=None):
    out, p = [], 0
    while p < 40:
        url = WTA_URL.format(p=p) + (f"&at={at}" if at else "")
        rows = json.loads(get(url))
        if not rows:
            break
        out.extend(rows)
        if len(rows) < 100:
            break
        p += 1
        time.sleep(1)
    if len(out) < 500:
        raise RuntimeError(f"WTA list looks short ({len(out)} players)")
    return out


def main():
    data = load(OUT, {})
    hist = load(HIST, {})
    last = data.get("checked")
    force = FORCE or data.get("ages") != AGES
    hist.setdefault("atp", {})
    pending = any("_all" not in v and "_tok" not in v and w not in hist.get("teSkip", []) for w, v in hist["atp"].items())
    if not force and not pending and data.get("atp") and data.get("wta") and last:
        # hourly on Mondays and Tuesdays (when the tours publish), every 3 hours otherwise
        if NOW - datetime.fromisoformat(last) < timedelta(hours=1 if NOW.weekday() in (0, 1) else 3):
            print("Scouting HQ: checked recently, nothing to do")
            return
    data["checked"] = NOW.isoformat(timespec="seconds")
    min_year = NOW.year - 21
    changed = False
    errors = data.get("errors") or {}  # tour -> {"at": iso, "msg": text}; read by report_gaps.py

    # ---- ATP ----
    try:
        week, rows = atp_current()
        filled = set()
        if pending:
            try:
                filled = backfill_atp(hist, rows, set(((data.get("atp") or {}).get("cmp") or {}).values()))
                changed = changed or bool(filled)
            except Exception as e:
                print("Scouting HQ: ATP history fill failed (tries again next run):", e)
        if force or not data.get("atp") or data["atp"].get("week") != week or filled & set(data["atp"].get("cmp", {}).values()):
            weeks = hist["atp"]
            # keep a compact copy of this week's ranking for future comparisons ("_all": every player is in it;
            # older weeks without it only hold players born in or after min_year - 2)
            weeks[week] = {key(r["name"]): r["rank"] for r in rows}
            weeks[week]["_all"] = 1
            cmp = {k: pick_week([w for w in weeks if w < week], (date.fromisoformat(week) - timedelta(days=d)).isoformat())
                   for k, d in BACK.items()}
            if data.get("atp", {}).get("week") != week:
                try:
                    te_refresh(hist)
                except Exception as e:
                    print("Scouting HQ: Tennis Explorer names not refreshed:", e)
            seen = set(hist.get("teSeen", []))

            def prev_rank(snap, r, y):
                if "_tok" in snap:  # filled in from Tennis Explorer: absent = not ranked then, unless the name never matched
                    t = tok(r["name"])
                    return snap[t] if t in snap else (None if t in seen else -1)
                if "_all" in snap or (y and y >= min_year - 2):
                    return snapshot_rank(snap, key(r["name"]))
                return -1

            players = []
            for r in rows:
                y = int(r["dob"][:4]) if r["dob"][:4].isdigit() else None  # None: birth date not published
                prev = {c: prev_rank(weeks[w], r, y) if w else None for c, w in cmp.items()}
                players.append([r["rank"], r["name"], r["cty"], y, prev["w"], prev["m3"], prev["m12"], r["url"]])
            data["atp"] = {"week": week, "cmp": cmp, "players": players}
            # trim history: last 60 weeks
            cutoff = (date.fromisoformat(week) - timedelta(weeks=60)).isoformat()
            for w in list(weeks):
                if w < cutoff:
                    del weeks[w]
            hist["teSkip"] = [w for w in hist.get("teSkip", []) if w in weeks]
            changed = True
            print(f"Scouting HQ: ATP week {week}, {len(players)} players, compared with {cmp}")
        else:
            print("Scouting HQ: ATP unchanged", week)
        errors.pop("atp", None)
    except Exception as e:
        print("Scouting HQ: ATP failed:", e)
        errors["atp"] = {"at": NOW.isoformat(timespec="seconds"), "msg": str(e)[:200]}

    # ---- WTA ----
    try:
        cur = wta_list()
        week = monday(date.fromisoformat(cur[0]["rankedAt"][:10])).isoformat()
        if force or not data.get("wta") or data["wta"].get("week") != week:
            cmp, prev_maps = {}, {}
            for c, d in BACK.items():
                at = (date.fromisoformat(week) - timedelta(days=d)).isoformat()
                lst = wta_list(at)
                cmp[c] = monday(date.fromisoformat(lst[0]["rankedAt"][:10])).isoformat()
                prev_maps[c] = {r["player"]["id"]: r["ranking"] for r in lst}
            players = []
            for r in cur:
                p = r["player"]
                dob = p.get("dateOfBirth") or ""
                y = int(dob[:4]) if dob[:4].isdigit() else None  # None: birth date not published
                name = p.get("fullName") or f"{p.get('firstName', '')} {p.get('lastName', '')}".strip()
                slug = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()).strip("-")
                players.append([r["ranking"], name, p.get("countryCode") or "", y,
                                prev_maps["w"].get(p["id"]), prev_maps["m3"].get(p["id"]), prev_maps["m12"].get(p["id"]),
                                f"https://www.wtatennis.com/players/{p['id']}/{slug}"])
            data["wta"] = {"week": week, "cmp": cmp, "players": players}
            changed = True
            print(f"Scouting HQ: WTA week {week}, {len(players)} players, compared with {cmp}")
        else:
            print("Scouting HQ: WTA unchanged", week)
        errors.pop("wta", None)
    except Exception as e:
        print("Scouting HQ: WTA failed:", e)
        errors["wta"] = {"at": NOW.isoformat(timespec="seconds"), "msg": str(e)[:200]}

    data["minYear"] = min_year
    if data.get("atp") and data.get("wta") and not ({"atp", "wta"} & set(errors)):
        data["ages"] = AGES
    data["errors"] = errors
    if changed:
        data["updated"] = NOW.isoformat(timespec="seconds")
        save(HIST, hist, compact=True)
    save(OUT, data, compact=True)


if __name__ == "__main__":
    main()
