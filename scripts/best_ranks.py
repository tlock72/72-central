"""
72 Central - past best rankings for Scouting Corner's "Over 21" suggestions (runs inside "Update scores", no Claude).

An over-21 player climbing fast is only interesting if they have never been this high before: someone coming
back from injury to a level they already reached isn't a find. So this keeps the official ATP and WTA rankings
at the start of every quarter (Jan, Apr, Jul, Oct) over the last 5 years, top 700 only, and works out each
over-21 player's best rank in those that are more than 12 months older than the current ranking week.

Sources (free, no key, the same as scripts/scouting.py):
  - ATP: Tennis Explorer's past weekly rankings (already checked against Tennis Abstract by scouting.py)
  - WTA: the official WTA rankings feed (api.wtatennis.com), matched by WTA player id

Past rankings never change, so each quarter is read once (3 a run per tour until they're all in, then one new
quarter every 3 months). Writes best.json:
  atp / wta: {"week": the scouting.json week it was worked out for,
              "ready": every quarter in the window has been read,
              "old": {name as in scouting.json: [best rank, ranking week] or 0 = never in the top 700 at those
                      checks}}  - a player left out could not be matched for certain, and the page leaves them out
  snaps: the stored quarters, tried: quarters already read (or with no ranking that week), errors{tour}
"""
import json, os, re, sys, time
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scouting as sc  # noqa: E402  (shares the download, name matching and file helpers)

OUT = "best.json"
TOP = 700        # ranks kept per quarter
YEARS = 5        # how far back
PER_RUN = 3      # quarters read per run per tour
OVER = 21        # only players older than this get an "old best"
MAX_RANK = 1000  # ...and only those ranked in the top 1000 now
NOW = datetime.now(timezone.utc)


def quarters(week):
    """First Monday of Jan/Apr/Jul/Oct from 5 years before `week` to 12 months before it."""
    out = []
    for y in range(week.year - YEARS - 1, week.year + 1):
        for m in (1, 4, 7, 10):
            d = date(y, m, 1)
            d += timedelta(days=(7 - d.weekday()) % 7)
            if week - timedelta(days=YEARS * 365) <= d <= week - timedelta(days=364):
                out.append(d.isoformat())
    return out


def atp_snap(d):
    """Tennis Explorer's ATP ranking in force at date d (that week, or one of the next 3 if it has no list that
    week), top 700, as {tok(name): rank}; -1 = two players with that name. (None, None) if none of them has one."""
    for shift in (0, 7, 14, 21):
        w = (date.fromisoformat(d) + timedelta(days=shift)).isoformat()
        seen, ok = {}, True
        for p in range(1, 40):
            page = sc.get(sc.TE_URL.format(d=w, p=p))
            if p == 1 and not re.search(r'<option value="%s" selected' % w, page):
                ok = False  # no ranking published that week (e.g. the off-season), Tennis Explorer shows another one
                break
            ranks = []
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
                m = re.search(r'class="rank first">\s*(\d+)\.\s*</td>.*?class="t-name"><a href="/player/[^"]*">([^<]+)</a>', tr, re.S)
                if m:
                    ranks.append(int(m.group(1)))
                    seen.setdefault(sc.tok(sc.html.unescape(m.group(2))), []).append(ranks[-1])
            if not ranks or max(ranks) >= TOP:
                break
            time.sleep(0.3)
        if ok:
            if len(seen) < TOP * 0.9:
                raise RuntimeError(f"Tennis Explorer list for {w} looks short ({len(seen)} players)")
            return w, {k: (v[0] if len(v) == 1 else -1) for k, v in seen.items() if min(v) <= TOP}
    return None, None


def wta_snap(d):
    """The official WTA ranking in force at date d, top 700, as {WTA player id: rank}."""
    out, week = {}, None
    for p in range(12):
        rows = json.loads(sc.get(sc.WTA_URL.format(p=p) + f"&at={d}"))
        if not rows:
            break
        week = week or sc.monday(date.fromisoformat(rows[0]["rankedAt"][:10])).isoformat()
        for r in rows:
            if r["ranking"] <= TOP:
                out[str(r["player"]["id"])] = r["ranking"]
        if rows[-1]["ranking"] >= TOP or len(rows) < 100:
            break
        time.sleep(1)
    # the feed must really have gone back to that date (not handed back the current list)
    if not week or not (date.fromisoformat(d) - timedelta(days=21) <= date.fromisoformat(week) <= date.fromisoformat(d)):
        raise RuntimeError(f"WTA feed gave the week of {week} when asked for {d}")
    if len(out) < TOP * 0.9:
        raise RuntimeError(f"WTA list for {d} looks short ({len(out)} players)")
    return week, out


def main():
    data = sc.load(OUT, {})
    before = json.dumps(data, sort_keys=True)
    S = sc.load(sc.OUT, {})
    seen = set(sc.load(sc.HIST, {}).get("teSeen", []))  # every name Tennis Explorer has listed (tells "not ranked" from "not matched")
    snaps = data.setdefault("snaps", {})
    tried = data.setdefault("tried", {})
    errors = data.get("errors") or {}
    for t in ("atp", "wta"):
        T = S.get(t)
        if not T or not T.get("week"):
            continue
        snaps.setdefault(t, {})
        tried.setdefault(t, [])
        want = quarters(date.fromisoformat(T["week"]))
        try:
            for d in [d for d in want if d not in tried[t]][:PER_RUN]:
                w, lst = (atp_snap if t == "atp" else wta_snap)(d)
                tried[t].append(d)
                if lst:
                    snaps[t][d] = {"week": w, "r": lst}
                    seen |= set(lst) if t == "atp" else set()
                print(f"Best ranks: {t.upper()} {d} -> {w or 'no ranking that month'} ({len(lst or {})} players)")
            errors.pop(t, None)
        except Exception as e:
            print(f"Best ranks: {t.upper()} failed (tries again next run):", e)
            errors[t] = {"at": NOW.isoformat(timespec="seconds"), "msg": str(e)[:200]}
        # quarters that have moved out of the 5-year window are dropped
        snaps[t] = {d: v for d, v in snaps[t].items() if d in want}
        tried[t] = [d for d in tried[t] if d in want]
        yr = int(T["week"][:4])
        old = {}
        for r in T["players"]:
            rank, name, born = r[0], r[1], r[3]
            if rank > MAX_RANK or not born or yr - born <= OVER:
                continue
            if t == "atp":
                k = sc.tok(name)
                if not sc.tok_find(k, seen):
                    continue  # Tennis Explorer spells the name differently: can't check, so not suggested
                vals = [(s["r"].get(sc.tok_find(k, s["r"]) or ""), s["week"]) for s in snaps[t].values()]
            else:
                m = re.search(r"/players/(\d+)/", r[7] or "")
                if not m:
                    continue
                vals = [(s["r"].get(m.group(1)), s["week"]) for s in snaps[t].values()]
            if any(v == -1 for v, _ in vals):
                continue  # two players with that name in a past list
            got = sorted((v, w) for v, w in vals if v)
            old[name] = list(got[0]) if got else 0
        data[t] = {"week": T["week"], "ready": all(d in tried[t] for d in want), "old": old}
    data["errors"] = errors
    if json.dumps(data, sort_keys=True) != before:
        data["checked"] = NOW.isoformat(timespec="seconds")
        sc.save(OUT, data, compact=True)
        print("Best ranks: saved", {t: (len((data.get(t) or {}).get("old", {})), (data.get(t) or {}).get("ready")) for t in ("atp", "wta")})
    else:
        print("Best ranks: nothing new")


if __name__ == "__main__":
    main()
