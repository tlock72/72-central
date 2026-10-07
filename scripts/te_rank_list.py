"""
72 Central - Tennis Europe U14 rankings for Filtered Rankings (runs in the "Scouting Corner" GitHub
Action, no Claude needed).

Builds terank.json: every boy and girl in the Tennis Europe Ranking "14 & Under" lists, with year of
birth, rank and the moves over 1 week, 3 months (13 weeks) and 12 months (52 weeks). The website's
Filtered Rankings page shows it under "TE U14 Boys" / "TE U14 Girls" and filters it by birth year.

Tennis Europe keeps every past ranking week, so the moves are read from its own past lists (no
building up). A week is only used when the page's own heading ("Tennis Europe Ranking (41-2026)")
and "Last updated" date agree with the week picked. Checks for a new week at most every 3 hours (one
request); a full rebuild (about 35 pages, plus past weeks not read before) only when a new week is out.
72 juniors are matched by their Tennis Europe profile id from te.json, never by name.
"""
import html, json, os, re, sys, time
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import te_matches as TE  # Tennis Europe: cookie consent and page fetch (5 s between requests)

OUT, HIST = "terank.json", "terank_history.json"
CATS = {"b14": "Boys 14 & Under", "g14": "Girls 14 & Under"}
BACK = {"w": 7, "m3": 91, "m12": 364}
PS = 100           # players per page
MAX_PAGES = 60
NOW = datetime.now(timezone.utc)
FORCE = os.environ.get("FORCE") == "1"
SITE = TE.SITE


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


def label_monday(w, y):
    """'41-2026' -> Monday 2026-10-05 (Tennis Europe also has a week 53 at some year ends)."""
    return date.fromisocalendar(y, 52, 1) + timedelta(days=7) if w == 53 else date.fromisocalendar(y, w, 1)


def page_week(page):
    """The Monday a ranking page is for, only if its heading and its "Last updated" date agree."""
    text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())
    lab = re.search(r"Tennis Europe Ranking \((\d{1,2})-(\d{4})\)", text)
    upd = re.search(r"Last updated: (\d{1,2} \w+ \d{4})", text)
    if not lab or not upd:
        return None
    try:
        monday = label_monday(int(lab[1]), int(lab[2]))
        d = datetime.strptime(upd[1], "%d %B %Y").date()
    except ValueError:
        return None
    return monday if d - timedelta(days=d.weekday()) == monday else None


def overview():
    """(newest publication id, its Monday, {publication id: Monday}, {key: category id})."""
    page = TE.fetch("/ranking/ranking.aspx?rid=79")
    sel = re.search(r"<select[^>]*dlPublication.*?</select>", page, re.S)
    if not sel or "Tennis Europe Ranking" not in page:
        raise RuntimeError("Tennis Europe ranking page not recognised")
    pubs = {}
    for v, w, y in re.findall(r'value="(\d+)"[^>]*>\s*(\d{1,2})-(\d{4})\s*<', sel[0]):
        try:
            pubs.setdefault(v, label_monday(int(w), int(y)))
        except ValueError:
            pass
    cur = re.search(r'<option[^>]*selected[^>]*value="(\d+)"|<option[^>]*value="(\d+)"[^>]*selected', sel[0])
    cur = cur and (cur[1] or cur[2])
    wk = page_week(page)
    if not cur or not wk or pubs.get(cur) != wk:
        raise RuntimeError("couldn't tell which week the Tennis Europe ranking is on")
    cats = {}
    links = [(c, " ".join(html.unescape(re.sub(r"<[^>]+>", " ", t)).split()))
             for c, t in re.findall(r'href="[^"]*category\.aspx\?id=\d+&(?:amp;)?category=(\d+)"[^>]*>(.*?)</a>', page, re.S)]
    for k, name in CATS.items():
        ids = {c for c, t in links if t == name} or {  # else the heading cell with that name and a link in it
            m[0] for th in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", page, re.S)
            if " ".join(html.unescape(re.sub(r"<[^>]+>", " ", th)).split()).startswith(name)
            for m in [re.search(r"category=(\d+)", th)] if m}
        if len(ids) != 1:
            raise RuntimeError(f"no single '{name}' list on the Tennis Europe ranking page")
        cats[k] = ids.pop()
    return cur, wk, pubs, cats


def read_list(pub, cat, want):
    """Every row of one category in one week: [{id, rank, name, nat, born}]. Refuses a page of another week."""
    rows = []
    for p in range(1, MAX_PAGES + 1):
        page = TE.fetch(f"/ranking/category.aspx?id={pub}&category={cat}&C{cat}FOG_3_F2048=&p={p}&ps={PS}")
        if page_week(page) != want:
            raise RuntimeError(f"Tennis Europe page {p} isn't the week of {want}")
        got = 0
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
            rk = re.search(r'<td class="rank"[^>]*>\s*<div[^>]*>\s*(\d+)', tr)
            pl = re.search(r'profile/default\.aspx\?id=([0-9A-Fa-f-]{36})"[^>]*>([^<]+)</a>', tr)
            if not rk or not pl:
                continue
            nat = re.search(r'flags/([A-Z]{3})\.', tr)
            # year of birth: the cell straight after the player's name (it can end in a non-breaking space)
            cells = [" ".join(html.unescape(re.sub(r"<[^>]+>", " ", c)).split()) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            at = next((i for i, c in enumerate(re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)) if "profile/default.aspx" in c), None)
            yob = re.fullmatch(r"(\d{4})", cells[at + 1]) if at is not None and at + 1 < len(cells) else None
            rows.append({"id": pl[1].upper(), "rank": int(rk[1]), "name": " ".join(html.unescape(pl[2]).split()),
                         "nat": nat[1] if nat else "", "born": int(yob[1]) if yob else None})
            got += 1
        total = re.search(r"Page \d+ of (\d+)", page)
        if not got or not total or p >= int(total[1]):
            break
    return rows


def main():
    out = load(OUT, {})
    hist = load(HIST, {})
    errors = out.setdefault("errors", {})
    last = out.get("checked")
    # every 3 hours at most, except while a list has never loaded (then every run until it does)
    if last and not FORCE and all(out.get(k) for k in CATS) and NOW - datetime.fromisoformat(last) < timedelta(hours=3):
        print("Tennis Europe ranking checked less than 3 hours ago"); return
    roster = {v.upper(): k for k, v in (load("te.json", {}).get("profiles") or {}).items() if ":" not in k}
    try:
        TE.consent()
        cur, wk, pubs, cats = overview()
    except Exception as e:
        print("Tennis Europe ranking not readable:", e)
        for k in CATS:
            errors[k] = {"at": NOW.isoformat(timespec="seconds"), "msg": str(e)[:200]}
        out["checked"] = NOW.isoformat(timespec="seconds")
        save(OUT, out); return
    week = wk.isoformat()
    changed = False
    for k in CATS:
        if (out.get(k) or {}).get("week") == week and not FORCE:
            print(k, "already on the week of", week); errors.pop(k, None); continue
        try:
            rows = read_list(cur, cats[k], wk)
            if len(rows) < 200:
                raise RuntimeError(f"only {len(rows)} players listed")
            if not any(r["born"] for r in rows):
                raise RuntimeError("the list has no years of birth")
            h = hist.setdefault(k, {})
            h[week] = {r["id"]: r["rank"] for r in rows}
            cmp = {}
            for m, days in BACK.items():  # the past weeks the moves need, from Tennis Europe's own lists
                want = wk - timedelta(days=days)
                pub = next((p for p, d in pubs.items() if abs((d - want).days) <= 3), None)
                if not pub:
                    cmp[m] = None; continue
                pw = pubs[pub].isoformat()
                if pw not in h:
                    try:
                        h[pw] = {r["id"]: r["rank"] for r in read_list(pub, cats[k], pubs[pub])}
                    except Exception as e:  # that week stays "not tracked" and is tried again next week
                        print(k, "past week", pw, "not read:", e); cmp[m] = None; continue
                cmp[m] = pw
            keep = set(cmp.values()) | {week}
            for w in [w for w in h if w not in keep and w < (wk - timedelta(days=380)).isoformat()]:
                del h[w]
            mv = lambda r, m: (h[cmp[m]].get(r["id"]) if cmp[m] else -1)  # None = not ranked then, -1 = not tracked
            out[k] = {"week": week, "cmp": cmp, "players": [
                [r["rank"], r["name"], r["nat"], r["born"], mv(r, "w"), mv(r, "m3"), mv(r, "m12"),
                 f"{SITE}/player-profile/{r['id']}", roster.get(r["id"])] for r in sorted(rows, key=lambda r: r["rank"])]}
            errors.pop(k, None)
            changed = True
            print(f"{k}: {len(rows)} players, week of {week}")
        except Exception as e:
            print(k, "failed:", e)
            errors[k] = {"at": NOW.isoformat(timespec="seconds"), "msg": str(e)[:200]}
    out["checked"] = NOW.isoformat(timespec="seconds")
    if changed:
        out["updated"] = out["checked"]
        save(HIST, hist)
    save(OUT, out)


if __name__ == "__main__":
    main()
