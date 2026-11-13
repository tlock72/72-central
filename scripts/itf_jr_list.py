"""
72 Central - ITF junior rankings for Filtered Rankings (runs on Mondays in the "ITF junior rankings"
GitHub Action, no Claude needed).

Builds itfjr.json: every boy and girl in the ITF World Tennis Junior Rankings, with birth year, rank
and how far they have moved in the last week, 3 months (13 weeks) and 12 months (52 weeks). The
website's Filtered Rankings page shows it under "ITF Boys" / "ITF Girls" and filters it by birth year.

The week is the ranking date the ITF sends with the list itself (every page must carry the same date, or
nothing is saved), so a week published late on a Monday is still picked up by the next run. Any 72 junior
read for that same week (itf.json, itf_juniors.py) must also have the same rank in it.

Moves: the ITF has no past junior weeks (its ranking call ignores every date setting), so the 3-month and
12-month moves build up week by week in itfjr_history.json from 5 Oct 2026; a move of -1 means "not
tracked then". The 1-week move comes from that history too, or, if last week wasn't read, from the ITF's own
rankMovement, but only once the run has checked which way round the ITF counts it against our history.
Past weeks before our own history (from 2 Jun 2026, top 500 to 1,500 only) are copied in once from a public
project that saved the ITF's official list every Monday (OUTSIDE below), but only if every week it shares with
ours is identical; a player beyond the depth of such a week counts as "not tracked then" (-1), never as NEW.
On top of that, every player's rank in the ITF's official year-end list for last year (the ITF keeps those,
juniorRankingType=year) is stored once in itfjr_history.json["ye"] and shown as the "End 2025" column.

If the ITF answers with its bot check the script stops straight away (it never tries to get past
it) and keeps the previous list; the error is alerted by report_gaps.py.
"""
import csv, io, json, os, re, subprocess, tempfile, time, urllib.parse, urllib.request
from datetime import date, datetime, timedelta, timezone

BASE = "https://www.itftennis.com/tennis/api/PlayerRankApi/GetPlayerRankings"
UA = "72HubRankings/1.0 (+https://github.com/tlock72/72-central; weekly, one request every few seconds)"
PAUSE = 3      # seconds between requests (the ITF itself takes 3-15 s to answer each page)
TAKE = 100     # players per page (the ITF sends only 10 if asked for more)
MAX_PAGES = 70  # about 5,000 boys and 4,000 girls
OUT, HIST = "itfjr.json", "itfjr_history.json"
BACK = {"w": 7, "m3": 91, "m12": 364}  # 1 week, 13 weeks, 52 weeks
GENDERS = {"b": "B", "g": "G"}         # itfjr.json key -> ITF playerTypeCode
NOW = datetime.now(timezone.utc)
FORCE = os.environ.get("FORCE") == "1"


class Blocked(Exception):
    pass


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")


def get(skip, code, tries=4, take=TAKE, year=None):
    time.sleep(PAUSE)
    q = {"circuitCode": "JT", "playerTypeCode": code, "ageCategoryCode": "", "juniorRankingType": "itf",
         "take": take, "skip": skip, "isOrderAscending": "true"}
    if year:  # the ITF's official year-end list for that year
        q.update(juniorRankingType="year", juniorEndYear=year)
    req = urllib.request.Request(f"{BASE}?{urllib.parse.urlencode(q)}", headers={"User-Agent": UA, "Accept": "application/json"})
    for i in range(tries):  # the ITF is sometimes slow to answer: wait and ask again, up to 4 times
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read().decode("utf-8", "replace")
            break
        except Exception as e:
            if i == tries - 1:
                raise
            print(f"  slow answer ({e}), trying again", flush=True)
            time.sleep(10 * (i + 1))
    if not body.lstrip().startswith(("{", "[")):
        raise Blocked("ITF answered with its bot check")
    return json.loads(body)


def pick(d, *keys):
    for k in keys:
        if d.get(k) not in (None, ""):
            return d[k]
    return None


def tidy(s):
    s = " ".join(str(s or "").split())
    return s.title() if s.isupper() else s  # some lists give family names in capitals


def born(p):
    y = pick(p, "birthYear", "yearOfBirth", "playerBirthYear")
    if y is None:
        m = re.match(r"\s*(\d{4})", str(pick(p, "birthDate", "dateOfBirth", "playerBirthDate") or ""))
        y = m and m.group(1)
    try:
        y = int(y)
    except (TypeError, ValueError):
        return None
    return y if 1990 < y <= NOW.year else None


def list_date(res):
    """The ranking date the ITF sends with the list, e.g. "09 November 2026" (None if missing)."""
    return (res.get("rankDate") or None) if isinstance(res, dict) else None


def peek(code):
    """One small request: the ranking date of the ITF's current list."""
    return list_date(get(0, code, take=10))


def read_list(code, year=None):
    """The whole ranking list for boys (B) or girls (G): ([{id, rank, name, nat, born, url, mv}], ranking date).
    With year: the ITF's official year-end list for that year."""
    out, total, skip, when = [], None, 0, None
    for page in range(MAX_PAGES):
        res = get(skip, code, year=year)
        items = res if isinstance(res, list) else pick(res, "items", "players", "rankings", "data") or []
        if total is None and isinstance(res, dict):
            total = pick(res, "totalItems", "total", "totalCount")
        d = list_date(res)
        if page == 0:
            when = d
        elif d != when:  # the ITF published a new week while we were reading: never mix two weeks
            raise RuntimeError(f"the ranking date changed while reading ({when} to {d})")
        if page == 0 and items:
            print("fields:", sorted(items[0].keys()))
        print(f"  {code} page {page + 1}: {len(items)} players", flush=True)
        for p in items:
            pid, rank = pick(p, "playerId", "id"), pick(p, "rank", "ranking", "currentRank")
            given = pick(p, "playerGivenName", "givenName", "firstName") or ""
            family = pick(p, "playerFamilyName", "familyName", "lastName") or ""
            name = tidy(f"{tidy(given)} {tidy(family)}") or tidy(pick(p, "playerName", "name"))
            if not pid or not rank or not name:
                continue
            nat = str(pick(p, "playerNationalityCode", "nationalityCode", "nationality") or "")[:3].upper()
            link = pick(p, "profileLink", "playerProfileUrl")
            slug = re.sub(r"[^a-z]+", "-", name.lower()).strip("-")
            url = (("https://www.itftennis.com" + link) if str(link or "").startswith("/") else link) \
                or f"https://www.itftennis.com/en/players/{slug}/{pid}/{nat.lower()}/jt/s/overview/"
            mv = p.get("rankMovement")
            out.append({"id": int(pid), "rank": int(rank), "name": name, "nat": nat, "born": born(p), "url": url,
                        "mv": int(mv) if isinstance(mv, (int, float)) else None})
        skip += len(items)  # the ITF may send fewer than asked for per page
        if page == 0 and total and len(items) < TAKE and int(total) > len(items) * MAX_PAGES:
            raise RuntimeError(f"the ITF only sends {len(items)} players a page, too few to read {total}")
        if not items or (total and skip >= int(total)) or (not total and len(items) < TAKE):
            break
    else:
        raise RuntimeError(f"more than {MAX_PAGES * TAKE} players listed, stopped")
    return out, when


def check(rows, itf, wk):
    """Every 72 junior read for this week must have the same rank in the list (else it's another week)."""
    by_id = {r["id"]: r["rank"] for r in rows}
    seen, bad = 0, []
    for rid, p in (itf.get("players") or {}).items():
        if not p.get("itfId") or not p.get("rank") or week_of(p.get("rankDate")) != wk:
            continue
        if p["itfId"] in by_id:  # only players on this list (boys or girls)
            seen += 1
            if by_id[p["itfId"]] != p["rank"]:
                bad.append(f"{rid} {by_id[p['itfId']]} v {p['rank']}")
    return seen, bad


def mv_sign(rows, prev):
    """Which way round the ITF counts rankMovement, checked against last week's ranks we read ourselves:
    +1 = positive means moved up (last week = rank + mv), -1 = the other way, None = can't tell yet."""
    up = down = n = 0
    for r in rows:
        was = prev.get(str(r["id"]))
        if r["mv"] in (None, 0) or not was:
            continue
        n += 1
        up += was == r["rank"] + r["mv"]
        down += was == r["rank"] - r["mv"]
    print(f"  rankMovement check: {n} movers, {up} fit 'positive = up', {down} fit 'positive = down'")
    if n >= 50 and up >= 0.98 * n:
        return 1
    if n >= 50 and down >= 0.98 * n:
        return -1
    return None


def year_end(hist, key, code, year):
    """The ITF's official year-end list for `year` ({id: rank}), read once and kept (it never changes)."""
    ye = hist.setdefault("ye", {}).setdefault(key, {})
    if str(year) not in ye:
        rows, when = read_list(code, year=year)
        if len(rows) < 300:
            raise RuntimeError(f"the {year} year-end list has only {len(rows)} players")
        ye[str(year)] = {"date": when, "ranks": {str(r["id"]): r["rank"] for r in rows}}
        print(f"{key}: {year} year-end list read, {len(rows)} players ({when})", flush=True)
    return ye[str(year)]


# A public project that saved the ITF's official junior ranking (its own feed, the same as GET above) every Monday
# from 2 Jun 2026: data/clean/rankings_snapshot.csv, rewritten each week, so every past week is in its git history.
# Checked in Nov 2026: all 15,000 ranks of the 10 weeks we both had were identical.
OUTSIDE = ("https://github.com/genaromoraes/itf-juniors-live-ranking.git", "data/clean/rankings_snapshot.csv")


def backfill(hist):
    """Once: copy past weeks we never read ourselves from OUTSIDE's git history. Only if every week we both
    have is identical (no rank differs, at least 99.9% of their players found on ours)."""
    if hist.get("backfill", {}).get("done"):
        return
    gk = {"M": "b", "F": "g"}
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["git", "clone", "-q", "--filter=blob:none", OUTSIDE[0], d], check=True, timeout=300)
        git = lambda *a: subprocess.run(["git", "-C", d, *a], capture_output=True, text=True, timeout=120).stdout
        weeks = {}  # (b/g, Monday) -> {id: rank}; a later version of the same week wins
        for sha in reversed(git("log", "--format=%H", "--", OUTSIDE[1]).split()):
            per = {}
            for r in csv.DictReader(io.StringIO(git("show", f"{sha}:{OUTSIDE[1]}"))):
                try:
                    k, day = gk[r["gender"]], date.fromisoformat(r["ranking_date"])
                    per.setdefault((k, (day - timedelta(days=day.weekday())).isoformat()), {})[str(int(r["player_id"]))] = int(r["rank"])
                except (KeyError, ValueError):
                    continue
            weeks.update(per)
    shared = bad = found = total = 0
    for (k, wk), ranks in weeks.items():
        mine = hist.get(k, {}).get(wk)
        if not mine:
            continue
        shared += 1
        for pid, r in ranks.items():
            total += 1
            if pid in mine:
                found += 1
                bad += mine[pid] != r
    print(f"backfill check: {shared} shared weeks, {total} ranks, {found} found on ours, {bad} different")
    if shared < 4 or bad or found < 0.999 * total:
        raise RuntimeError(f"the outside copy of past weeks doesn't match ours ({shared} weeks, {bad} different, {total - found} missing), not used")
    added = 0
    for (k, wk), ranks in weeks.items():
        if wk not in hist.setdefault(k, {}):
            hist[k][wk] = ranks
            hist.setdefault("depth", {}).setdefault(k, {})[wk] = max(ranks.values())  # only the top N of that week
            added += 1
    hist["backfill"] = {"done": NOW.isoformat(timespec="seconds"), "weeks": added, "checked": shared}
    print(f"backfill: {added} past weeks copied in")


def week_of(s):
    try:
        d = datetime.strptime(s or "", "%d %B %Y").date()
    except ValueError:
        return None
    return (d - timedelta(days=d.weekday())).isoformat()  # the Monday of that ranking week


def past(hist, wk, days):
    """The stored week closest to `days` before wk (within 3 days), or None if it wasn't tracked."""
    want = date.fromisoformat(wk) - timedelta(days=days)
    near = [w for w in hist if abs((date.fromisoformat(w) - want).days) <= 3]
    return min(near, key=lambda w: abs((date.fromisoformat(w) - want).days)) if near else None


def main():
    itf = load("itf.json", {})
    out = load(OUT, {})
    hist = load(HIST, {})
    errors = out.setdefault("errors", {})
    roster = {p["itfId"]: rid for rid, p in (itf.get("players") or {}).items() if p.get("itfId")}
    ye_year = NOW.year - 1  # "End 2025": last season's official year-end list
    changed = False
    try:
        backfill(hist)
        errors.pop("backfill", None)
    except Exception as e:  # tried again next run; the weekly list goes ahead either way
        print("backfill failed:", e)
        errors["backfill"] = {"at": NOW.isoformat(timespec="seconds"), "msg": str(e)[:200]}
    bf_new = (hist.get("backfill") or {}).get("done", "") > (out.get("updated") or "")
    for key, code in GENDERS.items():
        try:
            wk = week_of(peek(code))
            if not wk:
                raise RuntimeError("the ITF list came back without a ranking date")
            try:  # a year-end problem never holds up the weekly list
                ye = year_end(hist, key, code, ye_year)
                errors.pop(key + "ye", None)
            except Blocked:
                raise
            except Exception as e:
                print(key, "year-end list failed:", e)
                errors[key + "ye"] = {"at": NOW.isoformat(timespec="seconds"), "msg": f"{ye_year} year-end list: {e}"[:200]}
                ye = None
            ye_new = bool(ye) and (out.get(key) or {}).get("ye", {}).get("year") != ye_year
            if (out.get(key) or {}).get("week") == wk and not FORCE and not ye_new and not bf_new:
                print(key, "already on the week of", wk); continue
            rows, when = read_list(code)
            if week_of(when) != wk:
                raise RuntimeError(f"the ITF moved to a new week while reading ({wk} to {week_of(when)})")
            if len(rows) < 300:
                raise RuntimeError(f"only {len(rows)} players listed")
            seen, bad = check(rows, itf, wk)
            if bad:
                raise RuntimeError(f"the list doesn't match our juniors' ranks for the week of {wk} ({', '.join(bad[:3])})")
            print(f"  {seen} of our juniors read for this week agree with the list")
            if not any(r["born"] for r in rows):
                raise RuntimeError("the list has no birth years")
        except Exception as e:
            print(key, "failed:", e)
            errors[key] = {"at": NOW.isoformat(timespec="seconds"), "msg": str(e)[:200]}
            if isinstance(e, Blocked):
                break
            continue
        h = hist.setdefault(key, {})
        h[wk] = {str(r["id"]): r["rank"] for r in rows}
        depth = hist.setdefault("depth", {}).setdefault(key, {})
        for w in [w for w in h if w < (date.fromisoformat(wk) - timedelta(days=380)).isoformat()]:
            del h[w]  # older than the 12-month move needs
            depth.pop(w, None)
        cmp = {k: past(h, wk, d) for k, d in BACK.items()}
        last = (date.fromisoformat(wk) - timedelta(days=7)).isoformat()
        sign = hist.setdefault("mvSign", {}).get(key)
        if cmp["w"] == last:  # we have last week ourselves: learn (or re-check) which way round rankMovement is
            sign = mv_sign(rows, h[last]) or sign
            hist["mvSign"][key] = sign
        use_mv = cmp["w"] != last and sign is not None  # last week missing: fall back on the ITF's own 1-week move
        if use_mv:
            cmp["w"] = last
            print(f"  1-week moves from the ITF's own rankMovement (last week, {last}, wasn't read here)")

        def mv(r, k):  # rank then; None = not ranked then, -1 = not tracked then
            if k == "w" and use_mv:
                return (r["rank"] + sign * r["mv"]) if r["mv"] is not None else -1
            if not cmp[k]:
                return -1
            was = h[cmp[k]].get(str(r["id"]))
            return -1 if was is None and cmp[k] in depth else was  # a copied-in week only has its top N
        yr = ye["ranks"] if ye else {}
        out[key] = {"week": wk, "cmp": cmp, **({"ye": {"year": ye_year, "date": ye["date"]}} if ye else {}), "players": [
            [r["rank"], r["name"], r["nat"], r["born"], mv(r, "w"), mv(r, "m3"), mv(r, "m12"), r["url"], roster.get(r["id"]),
             None, yr.get(str(r["id"])) if ye else -1]  # [9] stays empty (points on the ATP/WTA lists); [10] = rank in last year's year-end list
            for r in sorted(rows, key=lambda r: r["rank"])]}
        errors.pop(key, None)
        changed = True
        print(f"{key}: {len(rows)} players, week of {wk}", flush=True)
        out["updated"] = NOW.isoformat(timespec="seconds")
        save(HIST, hist); save(OUT, out)  # boys are kept even if the girls run out of time
    out["checked"] = NOW.isoformat(timespec="seconds")
    if changed:
        out["updated"] = out["checked"]
    save(HIST, hist)
    save(OUT, out)


if __name__ == "__main__":
    main()
