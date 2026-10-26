"""
"""
import html, json, os, re, time, unicodedata, urllib.parse, urllib.request
from http.cookiejar import CookieJar
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

SITE = "https://te.tournamentsoftware.com"
UA = ""
PAUSE = 5
UK = ZoneInfo("Europe/London")
NOW = datetime.now(timezone.utc)
UK_NOW = NOW.astimezone(UK)
T = UK_NOW.date()

# every 72 player born 2010 or later: id -> name as Tennis Europe spells it (alternatives split by |)
PLAYERS = {
    "qi": "Hongjin Qi|Hongjing Qi", "pinera": "Paola Pinera Celorio|Paola Pinera", "fazekas": "Vencel Fazekas",
    "skryp": "Violetta Skryp", "choi": "Fu Wang Choi", "mmakarova": "Mariia Makarova", "vmakarova": "Varvara Makarova",
    "dotsenko": "Ekaterina Dotsenko", "drijver": "Laurens Drijver", "lin": "Yu Jun Lin", "daraban": "Luca Daraban",
    "newman": "Welles Newman", "tarlazzi": "Diego Tarlazzi", "kanabar": "Jensi Kanabar|Jensi Dipakbhai Kanabar",
    "farkxodov": "Saidaslam Farkxodov", "kurylova": "Nicole Kurylova", "iwasa": "Ayaka Iwasa",
    "mateo": "Jorge Mateo Moreno|Jorge Mateo", "davies": "Fletcher Davies", "momot": "Henry Momot", "liu": "Xichen Liu",
    "luchetti": "Giulia Luchetti",
}
KNOWN = {"momot": "84A53D21-B1AC-4757-BE1B-0896A13174DD", "davies": "6B0C03DA-40B9-4FC3-9768-0FCD24CFEA83",
         "luchetti": "2F65EB7D-F034-4088-A2F5-86292F475429"}
ROUNDS = {"round of 128": "R128", "round of 64": "R64", "round of 32": "R32", "round of 16": "R16",
          "quarter final": "QF", "quarter-final": "QF", "semi final": "SF", "semi-final": "SF", "final": "Final"}

jar = CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


class Stop(Exception):
    pass


def fetch(path, data=None):
    time.sleep(PAUSE)
    req = urllib.request.Request(SITE + path, data=data, headers={"User-Agent": UA, "Accept": "text/html"})
    with opener.open(req, timeout=40) as r:
        body = r.read().decode("utf-8", "replace")
        if "/cookiewall" in r.geturl():
            raise Stop("cookie page shown instead of data")
        return body


def consent():
    # the same choice as a visitor: only the essential 'basic functionality' cookies
    data = urllib.parse.urlencode({"ReturnUrl": "/", "SettingsOpen": "true", "CookiePurposes": "1"}).encode()
    fetch("/cookiewall/Save", data)


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).lower().replace("-", " ").split())


def find_profile(names):
    for name in names.split("|"):
        page = fetch("/find/player?q=" + urllib.parse.quote(name))
        hits = {g.upper() for g, n in re.findall(r'player-profile/([0-9A-Fa-f-]{36})"[^>]*>\s*<span class="nav-link__value">([^<]+)', page)
                if norm(html.unescape(n)) == norm(name)}
        if len(hits) == 1:
            return hits.pop()
        if len(hits) > 1:
            print("more than one Tennis Europe profile called", name, "- skipping")
            return None
    return None


def short(full):
    parts = full.split()
    if not parts:
        return ""
    last = " ".join(p.title() if p.isupper() else p for p in parts[1:]) or parts[0]
    return f"{parts[0][0]}. {last}" if len(parts) > 1 else last


def round_label(draw, title):
    t = (title or "").strip()
    r = ROUNDS.get(t.lower())
    if not r:
        m = re.match(r"round (\d+)", t.lower())
        r = f"R{m[1]}" if m else t
    d = (draw or "").strip()
    if d.lower().startswith("group"):
        return f"{d} · {r}"
    if "qualif" in d.lower():
        return "Q-" + r
    if "playoff" in d.lower() or "consolation" in d.lower():
        return "Playoff " + r
    return r


def parse(page, rid, names):
    soup = BeautifulSoup(page, "html.parser")
    mine = [set(norm(n).split()) for n in names.split("|")]
    out = []
    tour = start = end = link = event = draw = None
    category = ""
    for el in soup.find_all(["h4", "h5", "div", "small", "span"]):
        cls = el.get("class") or []
        if el.name == "h4" and "media__title" in cls:
            a = el.find("a")
            tour = (a.get("title") if a else el.get_text(strip=True)) or ""
            link = SITE + a["href"] if a and a.get("href", "").startswith("/") else None
            start = end = None; event = draw = None; category = ""
        elif el.name == "small" and "media__subheading--muted" in cls:
            ts = [t.get("datetime", "")[:10] for t in el.find_all("time")]
            if len(ts) == 2:
                start, end = (datetime.strptime(x, "%Y-%m-%d").date() for x in ts)
        elif el.name == "span" and "tag--soft" in cls and tour:
            category = el.get_text(" ", strip=True)
        elif el.name == "h4" and "module-divider" in cls:
            event = el.get_text(" ", strip=True).replace("Event:", "").strip(); draw = None
        elif el.name == "h5" and "module-divider" in cls:
            draw = el.get_text(" ", strip=True)
        elif el.name == "div" and "match" in cls and tour and event:
            if not re.match(r"^[BG]S", event):
                continue  # singles only
            rows = el.select(".match__row")
            if len(rows) != 2:
                continue
            players = [[n.get_text(" ", strip=True) for n in r.select(".match__row-title-value-content .nav-link__value")] for r in rows]
            side = next((i for i, ps in enumerate(players) if any(any(set(norm(p).split()) >= m for m in mine) for p in ps)), None)
            if side is None or not players[1 - side] or players[1 - side][0].lower() == "bye":
                continue
            opp = short(players[1 - side][0])
            foot = [x.get_text(" ", strip=True) for x in el.select(".match__footer-list-item .nav-link__value")]
            dm = re.search(r"(\d{2})/(\d{2})/(\d{4})(?:\s+(\d{1,2}:\d{2}))?", " ".join(foot))
            date = datetime(int(dm[3]), int(dm[2]), int(dm[1])).date() if dm else None
            court = next((f for f in foot if not re.search(r"\d{2}/\d{2}/\d{4}", f)), "")
            status = rows[side].select_one(".match__status")
            res = (status.get_text(strip=True).upper() if status else "")
            text = el.get_text(" ", strip=True).lower()
            base = {"matchId": f"te-{rid}-{tour}-{event}-{draw}-{(el.select_one('.match__header-title') or el).get_text(' ', strip=True)}",
                    "source": "te", "tournament": tour, "link": link, "time": "",
                    "category": f"Tennis Europe · U{re.sub(r'[^0-9]', '', event)} · {category}".strip(" ·"),
                    "round": round_label(draw, (el.select_one(".match__header-title") or el).get_text(" ", strip=True))}
            if res in ("W", "L"):
                if not date:
                    continue
                won = res == "W"
                sets = []
                for ul in el.select(".match__result ul.points"):
                    cells = [c.get_text(strip=True) for c in ul.select("li")]
                    if len(cells) == 2 and all(c.isdigit() for c in cells):
                        a, b = (cells[side], cells[1 - side])
                        sets.append(f"{a}-{b}" if won else f"{b}-{a}")
                score = ", ".join(sets)
                if "retired" in text:
                    score += " ret."
                if "walkover" in text:
                    base["round"] += " (walkover)"
                sides = dict(p1="", p1Id=rid, p2=opp, p2Id=None) if won else dict(p1=opp, p1Id=None, p2="", p2Id=rid)
                out.append(dict(base, date=date.isoformat(), status="finished", score=score, winner=1, **sides,
                                **({"court": court} if court else {})))
            else:
                if not date:
                    if start and end and start <= T <= end:
                        date = T
                    elif start and start > T:
                        date = start
                    else:
                        continue
                if date < T:
                    continue  # never got a result: leave it out
                slot = ", ".join(x for x in [court, dm[4] if dm and dm[4] else ""] if x)
                out.append(dict(base, date=date.isoformat(), status="scheduled", score="", winner=None,
                                p1="", p1Id=rid, p2=opp, p2Id=None, slot=slot))
    return out


def ranking(pid):
    """The Tennis Europe Ranking table on the profile (not the Race to Monte-Carlo table below it).
    Also returns the link to the player's own page in that ranking (used for past weeks), or None."""
    page = fetch(f"/player-profile/{pid}/ranking")
    soup = BeautifulSoup(page, "html.parser")
    links = sorted(set(re.findall(r'href="/ranking/player\.aspx\?id=(\d+)&(?:amp;)?player=(\d+)"', page)))
    week = None
    for tbl in soup.find_all("table"):
        trs = tbl.find_all("tr")
        cells = [[c.get_text(" ", strip=True).lower() for c in tr.find_all(["th", "td"])] for tr in trs]
        hi = next((i for i, c in enumerate(cells) if "rank" in c), None)
        if hi is None:
            continue
        # the table's own title: a heading inside it, or the rows above the column names, else the heading before it
        inner = tbl.find(["caption", "h2", "h3", "h4", "h5"])
        title = (inner.get_text(" ", strip=True) if inner else "") or " ".join(" ".join(c) for c in cells[:hi])
        if not title:
            prev = tbl.find_previous(["h2", "h3", "h4", "h5", "caption"])
            title = prev.get_text(" ", strip=True) if prev else ""
        if "tennis europe ranking" not in title.lower() or "race" in title.lower():
            continue
        heads = cells[hi]
        wk = re.search(r"\b(\d{1,2})-(\d{4})\b", title)
        if wk:
            week = date.fromisocalendar(int(wk[2]), int(wk[1]), 1).isoformat()
        rows = []
        for tr in trs[hi + 1:]:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if len(cells) != len(heads):
                continue
            row = dict(zip(heads, cells))

            def num(k):
                m = re.match(r"\d+", row.get(k) or "")
                return int(m[0]) if m else None
            best = re.match(r"(\d+)\s+(\d{1,2})-(\d{4})", row.get("best") or "")
            rows.append({"cat": row.get("category") or cells[0], "rank": num("rank"), "week": week,
                         "high": int(best[1]) if best else num("best"),
                         "highWeek": date.fromisocalendar(int(best[3]), int(best[2]), 1).isoformat() if best else None,
                         "pts": num("total points") or num("points")})
        return [r for r in rows if r["rank"]], links
    return [], links


def main():
    try:
        data = json.load(open("te.json"))
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    previous = {m["matchId"]: m for m in data.get("matches") or []}
    # a full check once a day, from 07:30 UK. In between, a quick check every hour (until 22:00 UK) re-reads only
    # the juniors in the middle of an event (a match yesterday or later), as the next day's matches are often
    # listed after the morning check (Junior Masters round robin).
    only = None
    if (UK_NOW.hour, UK_NOW.minute) < (7, 30):
        print("Tennis Europe: before 07:30 UK"); return
    if data.get("day") == T.isoformat():
        busy = {m.get("p1Id") or m.get("p2Id") for m in previous.values() if m["date"] >= (T - timedelta(days=1)).isoformat()}
        quick = data.get("quick")
        due = not quick or NOW - datetime.fromisoformat(quick.replace("Z", "+00:00")) >= timedelta(minutes=55)
        if not busy or not due or UK_NOW.hour >= 22:
            print("Tennis Europe already checked today - next check later"); return
        only = busy
        data["quick"] = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
        print("Tennis Europe quick check for", ", ".join(sorted(busy)))
    data["day"] = T.isoformat()
    profiles = data.setdefault("profiles", {})
    found = {}
    try:
        consent()
        for rid, names in PLAYERS.items():
            if only is not None and rid not in only:
                continue
            pid = profiles.get(rid) or KNOWN.get(rid)
            if not pid:
                if profiles.get(rid + ":none") and T.day > 7:
                    continue  # no Tennis Europe profile; looked again on the first days of each month
                pid = find_profile(names)
                if not pid:
                    profiles[rid + ":none"] = T.isoformat(); continue
                profiles[rid] = pid
                profiles.pop(rid + ":none", None)
            profiles[rid] = pid  # also the ids in KNOWN, so te_rank_list.py and schedule.py can match them
            try:
                for m in parse(fetch(f"/player-profile/{pid}/tournaments"), rid, names):
                    if m["date"] >= (T - timedelta(days=7)).isoformat() and m["date"] <= (T + timedelta(days=3)).isoformat():
                        found[m["matchId"]] = m
            except Stop:
                raise
            except Exception as e:
                print("failed", rid, e)
            if only is None:
                # rank and career high per category (profile page); kept as it was if the page can't be read
                try:
                    rows, _ = ranking(pid)
                    if rows:
                        data.setdefault("ranks", {})[rid] = rows
                except Stop:
                    raise
                except Exception as e:
                    print("ranking failed", rid, e)
    except Stop as e:
        print(e, "- keeping yesterday's data")
        with open("te.json", "w") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        return
    keep_from = (T - timedelta(days=7)).isoformat()
    for mid, m in previous.items():
        if only is not None and (m.get("p1Id") or m.get("p2Id")) not in only and m["date"] >= keep_from:
            found.setdefault(mid, m)   # quick check: everyone else's matches stay as they were
        elif mid not in found and m["status"] == "finished" and m["date"] >= keep_from:
            found[mid] = m
    data["matches"] = sorted(found.values(), key=lambda m: (m["date"], m["tournament"]))
    data["checked"] = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    with open("te.json", "w") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"done: {len(data['matches'])} Tennis Europe matches; profiles {sum(1 for k in profiles if ':' not in k)}")


if __name__ == "__main__":
    main()
