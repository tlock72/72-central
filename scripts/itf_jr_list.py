"""
72 Central - ITF junior rankings for Filtered Rankings (runs on Mondays in the "ITF junior rankings"
GitHub Action, no Claude needed).

Builds itfjr.json: every boy and girl in the ITF World Tennis Junior Rankings, with birth year, rank
and how far they have moved in the last week, 3 months (13 weeks) and 12 months (52 weeks). The
website's Filtered Rankings page shows it under "ITF Boys" / "ITF Girls" and filters it by birth year.

The ITF's ranking list has no date on it, so the week comes from itf.json (the date the ITF shows on
our own juniors' profiles, read just before by itf_juniors.py). The list is only saved if every 72
junior read for that same week has the same rank in it, so a list from another week is never saved
under the wrong date. The ITF has no past junior weeks, so the moves build up week by week in
itfjr_history.json: a move of -1 means "not tracked then".

If the ITF answers with its bot check the script stops straight away (it never tries to get past
it) and keeps the previous list; the error is alerted by report_gaps.py.
"""
import json, os, re, time, urllib.parse, urllib.request
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


def get(skip, code):
    time.sleep(PAUSE)
    q = {"circuitCode": "JT", "playerTypeCode": code, "ageCategoryCode": "", "juniorRankingType": "itf",
         "take": TAKE, "skip": skip, "isOrderAscending": "true"}
    req = urllib.request.Request(f"{BASE}?{urllib.parse.urlencode(q)}", headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8", "replace")
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


def read_list(code):
    """The whole ranking list for boys (B) or girls (G): [{id, rank, name, nat, born, url}]."""
    out, total, skip = [], None, 0
    for page in range(MAX_PAGES):
        res = get(skip, code)
        items = res if isinstance(res, list) else pick(res, "items", "players", "rankings", "data") or []
        if total is None and isinstance(res, dict):
            total = pick(res, "totalItems", "total", "totalCount")
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
            out.append({"id": int(pid), "rank": int(rank), "name": name, "nat": nat, "born": born(p), "url": url})
        skip += len(items)  # the ITF may send fewer than asked for per page
        if page == 0 and total and len(items) < TAKE and int(total) > len(items) * MAX_PAGES:
            raise RuntimeError(f"the ITF only sends {len(items)} players a page, too few to read {total}")
        if not items or (total and skip >= int(total)) or (not total and len(items) < TAKE):
            break
    else:
        raise RuntimeError(f"more than {MAX_PAGES * TAKE} players listed, stopped")
    return out


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
    wk = week_of(itf.get("rankDate"))
    out = load(OUT, {})
    hist = load(HIST, {})
    errors = out.setdefault("errors", {})
    if not wk:
        print("itf.json has no ranking date yet"); return
    roster = {p["itfId"]: rid for rid, p in (itf.get("players") or {}).items() if p.get("itfId")}
    changed = False
    for key, code in GENDERS.items():
        if (out.get(key) or {}).get("week") == wk and not FORCE:
            print(key, "already on the week of", wk); continue
        try:
            rows = read_list(code)
            if len(rows) < 300:
                raise RuntimeError(f"only {len(rows)} players listed")
            seen, bad = check(rows, itf, wk)
            if bad:
                raise RuntimeError(f"the list doesn't match our juniors' ranks for the week of {wk} ({', '.join(bad[:3])})")
            if not seen:
                raise RuntimeError(f"no 72 junior to check the list's week against (week of {wk})")
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
        for w in [w for w in h if w < (date.fromisoformat(wk) - timedelta(days=380)).isoformat()]:
            del h[w]  # older than the 12-month move needs
        cmp = {k: past(h, wk, d) for k, d in BACK.items()}
        mv = lambda r, k: (h[cmp[k]].get(str(r["id"])) if cmp[k] else -1)  # None = not ranked then, -1 = not tracked then
        out[key] = {"week": wk, "cmp": cmp, "players": [
            [r["rank"], r["name"], r["nat"], r["born"], mv(r, "w"), mv(r, "m3"), mv(r, "m12"), r["url"], roster.get(r["id"])]
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
