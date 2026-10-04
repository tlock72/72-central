"""
72 Central - Tennis Europe matches (runs once a day from 07:30 UK inside the 'Update scores' workflow, no Claude).

Used with Tennis Europe's permission, for internal use only. Reads each 72 player's Tennis Europe
profile page (one page per player, a few seconds apart) on Tennis Europe's official results
system and writes te.json: singles matches from the last week and anything scheduled, which the
website shows alongside the other matches.
"""
import html, json, os, re, time, unicodedata, urllib.parse, urllib.request
from http.cookiejar import CookieJar
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

SITE = "https://te.tournamentsoftware.com"
UA = "72SportsGroup-Central/1.0 (internal use, with Tennis Europe's permission; once a day; +https://github.com/tlock72/72-central)"
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
}
KNOWN = {"momot": "84A53D21-B1AC-4757-BE1B-0896A13174DD", "davies": "6B0C03DA-40B9-4FC3-9768-0FCD24CFEA83"}
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
                out.append(dict(base, date=date.isoformat(), status="finished", score=score, winner=1, **sides))
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


def main():
    try:
        data = json.load(open("te.json"))
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    # once a day, from 07:30 UK
    if data.get("day") == T.isoformat() or (UK_NOW.hour, UK_NOW.minute) < (7, 30):
        print("Tennis Europe already checked today or before 07:30 UK"); return
    data["day"] = T.isoformat()
    profiles = data.setdefault("profiles", {})
    previous = {m["matchId"]: m for m in data.get("matches") or []}
    found = {}
    try:
        consent()
        for rid, names in PLAYERS.items():
            pid = profiles.get(rid) or KNOWN.get(rid)
            if not pid:
                if profiles.get(rid + ":none") and T.day > 7:
                    continue  # no Tennis Europe profile; looked again on the first days of each month
                pid = find_profile(names)
                if not pid:
                    profiles[rid + ":none"] = T.isoformat(); continue
                profiles[rid] = pid
                profiles.pop(rid + ":none", None)
            try:
                for m in parse(fetch(f"/player-profile/{pid}/tournaments"), rid, names):
                    if m["date"] >= (T - timedelta(days=7)).isoformat() and m["date"] <= (T + timedelta(days=3)).isoformat():
                        found[m["matchId"]] = m
            except Stop:
                raise
            except Exception as e:
                print("failed", rid, e)
    except Stop as e:
        print(e, "- keeping yesterday's data")
        with open("te.json", "w") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        return
    keep_from = (T - timedelta(days=7)).isoformat()
    for mid, m in previous.items():
        if mid not in found and m["status"] == "finished" and m["date"] >= keep_from:
            found[mid] = m
    data["matches"] = sorted(found.values(), key=lambda m: (m["date"], m["tournament"]))
    data["checked"] = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    with open("te.json", "w") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"done: {len(data['matches'])} Tennis Europe matches; profiles {sum(1 for k in profiles if ':' not in k)}")


if __name__ == "__main__":
    main()
