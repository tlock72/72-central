"""
72 Central - Scouting HQ (runs inside the "Update scores" GitHub Action, no Claude needed).

Builds scouting.json: every ranked ATP and WTA singles player aged 21 or under by birth year
(born in or after this year minus 21), with birth year, current official ranking and how far
they have moved in the last week, 3 months (13 weeks) and 12 months (52 weeks).

Sources (both free, no key):
  - ATP: Tennis Abstract's weekly ranking report (official ATP ranking + date of birth)
         https://www.tennisabstract.com/reports/atpRankings.html
         Past ATP weeks come from scouting_history.json, which this script adds to every week.
  - WTA: the official WTA rankings feed (api.wtatennis.com), which also serves past weeks.

It only does work when something is new: at most one check every 3 hours, and it rebuilds
when either tour has published a new ranking week (or when RANKINGS=1 / FORCE=1).
"""
import html, json, os, re, sys, time, unicodedata, urllib.request
from datetime import date, datetime, timedelta, timezone

UA = "72CentralScouting/1.0 (+https://github.com/tlock72/72-central; weekly, a few requests)"
TA_URL = "https://www.tennisabstract.com/reports/atpRankings.html"
WTA_URL = "https://api.wtatennis.com/tennis/players/ranked?page={p}&pageSize=100&type=rankSingles&sort=asc&metric=SINGLES"
OUT, HIST = "scouting.json", "scouting_history.json"
NOW = datetime.now(timezone.utc)
FORCE = os.environ.get("RANKINGS") == "1" or os.environ.get("FORCE") == "1"
BACK = {"w": 7, "m3": 91, "m12": 364}  # 1 week, 13 weeks, 52 weeks


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
    if not FORCE and data.get("atp") and data.get("wta") and last:
        if NOW - datetime.fromisoformat(last) < timedelta(hours=3):
            print("Scouting HQ: checked recently, nothing to do")
            return
    data["checked"] = NOW.isoformat(timespec="seconds")
    min_year = NOW.year - 21
    hist.setdefault("atp", {})
    changed = False
    errors = data.get("errors") or {}  # tour -> {"at": iso, "msg": text}; read by report_gaps.py

    # ---- ATP ----
    try:
        week, rows = atp_current()
        if FORCE or not data.get("atp") or data["atp"].get("week") != week:
            weeks = hist["atp"]
            # keep a compact copy of this week's young players for future comparisons
            weeks[week] = {key(r["name"]): r["rank"] for r in rows if r["dob"][:4].isdigit() and int(r["dob"][:4]) >= min_year - 2}
            cmp = {k: pick_week([w for w in weeks if w < week], (date.fromisoformat(week) - timedelta(days=d)).isoformat())
                   for k, d in BACK.items()}
            players = []
            for r in rows:
                y = int(r["dob"][:4]) if r["dob"][:4].isdigit() else None
                if not y or y < min_year:
                    continue
                k = key(r["name"])
                prev = {c: (snapshot_rank(weeks[w], k) if w else None) for c, w in cmp.items()}
                players.append([r["rank"], r["name"], r["cty"], y, prev["w"], prev["m3"], prev["m12"], r["url"]])
            data["atp"] = {"week": week, "cmp": cmp, "players": players}
            # trim history: last 60 weeks, young players only
            cutoff = (date.fromisoformat(week) - timedelta(weeks=60)).isoformat()
            young = {key(r["name"]) for r in rows if r["dob"][:4].isdigit() and int(r["dob"][:4]) >= min_year - 2}
            by8 = {}
            for y2 in young:
                by8.setdefault(y2[:8], []).append(y2)

            def keep(k):
                return k in young or (len(k) >= 8 and any(k.startswith(y2) or y2.startswith(k) for y2 in by8.get(k[:8], [])))
            for w in list(weeks):
                if w < cutoff:
                    del weeks[w]
                else:
                    weeks[w] = {k: v for k, v in weeks[w].items() if keep(k)}
            changed = True
            print(f"Scouting HQ: ATP week {week}, {len(players)} players born {min_year}+, compared with {cmp}")
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
        if FORCE or not data.get("wta") or data["wta"].get("week") != week:
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
                y = int(dob[:4]) if dob[:4].isdigit() else None
                if not y or y < min_year:
                    continue
                name = p.get("fullName") or f"{p.get('firstName', '')} {p.get('lastName', '')}".strip()
                slug = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()).strip("-")
                players.append([r["ranking"], name, p.get("countryCode") or "", y,
                                prev_maps["w"].get(p["id"]), prev_maps["m3"].get(p["id"]), prev_maps["m12"].get(p["id"]),
                                f"https://www.wtatennis.com/players/{p['id']}/{slug}"])
            data["wta"] = {"week": week, "cmp": cmp, "players": players}
            changed = True
            print(f"Scouting HQ: WTA week {week}, {len(players)} players born {min_year}+, compared with {cmp}")
        else:
            print("Scouting HQ: WTA unchanged", week)
        errors.pop("wta", None)
    except Exception as e:
        print("Scouting HQ: WTA failed:", e)
        errors["wta"] = {"at": NOW.isoformat(timespec="seconds"), "msg": str(e)[:200]}

    data["minYear"] = min_year
    data["errors"] = errors
    if changed:
        data["updated"] = NOW.isoformat(timespec="seconds")
        save(HIST, hist, compact=True)
    save(OUT, data, compact=True)


if __name__ == "__main__":
    main()
