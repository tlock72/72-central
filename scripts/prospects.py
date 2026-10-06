"""
72 Central - Scouting Corner (its own workflow, prospects.yml; free sources only, no Claude, no Live Tennis API).

Builds corner.json: every scouting prospect, followed through every stage of their career and linked to
one person:
  Tennis Europe (U12-U16)  ->  ITF juniors  ->  ITF pro tour / ATP / WTA
Where the prospects come from:
  - prospects.json: the hand-kept watch list (edit it in the GitHub web editor);
  - the "Add a prospect" box on the site, which saves to Tobey's Google Sheet (scripts/visit_log.gs) and is
    read here on every run.
How the stages are linked (never guessed - an unsure link is left empty and alerted instead):
  - ITF: one ITF player id covers a player's junior AND pro career, so it is the anchor. Found by exact
    full name (and nationality, when known). Two or more people that fit = not linked, alerted.
  - Tennis Europe: exact full name, and the nationality on the Tennis Europe profile must be the
    prospect's (or the ITF profile's) nationality. Two or more that fit = not linked, alerted.
  - ATP / WTA: the official ranking the ITF shows for that ITF id, matched to the same rank and surname in
    scouting.json (which also gives birth year and the 1 week / 3 month / 12 month moves).
A link, once made, is kept; stages not linked yet are looked for again (new ones on every run, then once a
week), so a junior who moves up a level is picked up by themselves.
Any id can be pinned by hand in prospects.json ("itf", "te"), which always wins.
Each run refreshes the prospects not refreshed today (new ones first) within a time budget; the next run
carries on. If the ITF or Tennis Europe answers with a bot check / cookie page, that site is left alone for
3 hours and the previous data is kept.
"""
import html, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import te_matches as TE  # Tennis Europe: cookie consent, page fetch and match parsing
_tef = TE.fetch
def _trace(path, data=None):
    print("  TE", path, flush=True); return _tef(path, data)
TE.fetch = _trace  # TEMP trace

LIST, OUT = "prospects.json", "corner.json"
# the same Google Apps Script as the visit log (index.html LOG_URL); '?kind=prospects' lists the names added on the site
SHEET_URL = "https://script.google.com/macros/s/AKfycbwzEb0YNoDmZaaJ5fQg05ubEe_lowMLiGoYaXuclycqQikOngLQEmENPN5KoL_KJXu1kA/exec"
ITF = "https://www.itftennis.com/tennis/api"
UA = "72HubRankings/1.0 (+https://github.com/tlock72/72-central; scouting list, one request every few seconds)"
PAUSE = 5
BUDGET = timedelta(minutes=25)
UK = ZoneInfo("Europe/London")
NOW = datetime.now(timezone.utc)
T = NOW.astimezone(UK).date()
YEAR_AGO = T - timedelta(days=365)
RECHECK = timedelta(days=7)  # a stage not found yet is looked for again after this
STARTED = time.monotonic()


class Blocked(Exception):
    pass


def out_of_time():
    return time.monotonic() - STARTED > BUDGET.total_seconds()


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z ]", " ", s.replace("-", " ")).split())


def same_name(a, b):
    return sorted(norm(a).split()) == sorted(norm(b).split())  # any word order: "MAKAROVA Mariia" = "Mariia Makarova"


def key_of(name):
    return re.sub(r"[^a-z]", "", norm(name))


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def ago(s):
    try:
        return NOW - datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return timedelta(days=9999)


def load(f, default):
    try:
        return json.load(open(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


# ---------- ITF ----------
def itf(path, **params):
    print("  ITF", path, params, flush=True)
    time.sleep(PAUSE)
    req = urllib.request.Request(f"{ITF}{path}?{urllib.parse.urlencode(params)}", headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8", "replace")
    if not body.lstrip().startswith(("{", "[")):
        raise Blocked("ITF answered with its bot check")
    return json.loads(body)


def itf_find(p):
    """Returns (status, id, nat, circuits, note). status: linked / none / unsure."""
    hits = {}
    for name in p["names"]:
        for c in itf("/PlayerApi/GetPlayerSearch", searchString=name).get("players") or []:
            if same_name(f'{c.get("givenName")} {c.get("familyName")}', name):
                hits[c["playerId"]] = c
    circ = lambda c: {x.get("value") for x in c.get("playedCircuits") or []}
    if p.get("nat"):
        hits = {k: c for k, c in hits.items() if (c.get("playerNationalityCode") or "").upper() == p["nat"]}
    if p.get("g"):
        wrong = "WT" if p["g"] == "M" else "MT"
        hits = {k: c for k, c in hits.items() if wrong not in circ(c)}
    if not hits:
        return "none", None, None, [], ""
    if len(hits) > 1:
        return "unsure", None, None, [], "; ".join(f'id {k} ({c.get("playerNationalityCode")})' for k, c in hits.items())
    k, c = hits.popitem()
    return "linked", k, (c.get("playerNationalityCode") or "").upper(), sorted(circ(c)), "" if p.get("nat") else "name only (no nationality given)"


def itf_overview(pid, circuit):
    ov = itf("/PlayerApi/GetPlayerOverview", circuitCode=circuit, matchTypeCode="S", playerId=pid)
    cur = next(iter(ov.get("rankings") or []), None)
    hi = next(iter(ov.get("careerHighRankings") or []), None)
    return {"name": (cur or hi or {}).get("name"), "rank": cur.get("rank") if cur else None, "date": cur.get("date") if cur else None,
            "high": hi.get("rank") if hi else None, "highDate": hi.get("date") if hi else None}


def dates_of(s):
    # "05 Oct to 11 Oct 2026" (also "28 Dec to 03 Jan 2027")
    m = re.match(r"(\d+) (\w+)(?: (\d{4}))? to (\d+) (\w+) (\d{4})", s or "")
    if not m:
        return None, None
    end = datetime.strptime(f"{m[4]} {m[5]} {m[6]}", "%d %b %Y").date()
    start = datetime.strptime(f"{m[1]} {m[2]} {m[3] or m[6]}", "%d %b %Y").date()
    if start > end:
        start = start.replace(year=start.year - 1)
    return start, end


ROUNDS = {"1st round": "R1", "2nd round": "R2", "3rd round": "R3", "4th round": "R4", "round of 128": "R128",
          "round of 64": "R64", "round of 32": "R32", "round of 16": "R16", "quarter-final": "QF", "semi-final": "SF", "final": "F"}


def itf_results(pid, circuit, src):
    """Singles matches of the last 12 months on one ITF circuit (JT juniors, MT men, WT women; MT/WT include ATP/WTA events)."""
    out, skip = [], 0
    while True:
        act = itf("/PlayerApi/GetPlayerActivity", circuitCode=circuit, matchTypeCode="S", playerId=pid, skip=skip, take=20)
        items = act.get("items") or []
        for t in items:
            start, end = dates_of(t.get("dates"))
            if not end or end < YEAR_AGO:
                continue
            for ev in t.get("events") or []:
                qual = "qual" in (ev.get("drawType") or "").lower()
                for m in ev.get("matches") or []:
                    opp = (m.get("opponents") or [None])[0]
                    if not opp or not opp.get("familyName"):
                        continue  # bye, or opponent not decided yet
                    rnd = (m.get("roundGroup") or {}).get("Value") or ""
                    rnd = ROUNDS.get(rnd.lower(), rnd)
                    rc = (m.get("resultCode") or "").upper()
                    code = (m.get("resultStatusCode") or "").upper()
                    sets = []
                    for s in m.get("scores") or []:
                        a, b, tb = s.get("scoreOne"), s.get("scoreTwo"), s.get("losingScore")
                        if a is None or b is None:
                            continue
                        # scoreOne is always this player's games: kept from the prospect's side ("L 4-6, 5-7")
                        sets.append(f"{a}-{b}" + (f"({tb})" if tb is not None and abs(a - b) == 1 and max(a, b) >= 7 else ""))
                    score = ", ".join(sets) + (" ret." if "RET" in code or "DEF" in code else "")
                    if "W" in code and "O" in code:
                        score = "walkover"
                    out.append({"src": src, "start": start.isoformat(), "end": end.isoformat(), "t": re.sub(r"\s*\(.*\)\s*$", "", t.get("tournamentName") or ""),
                                "cat": t.get("tourCode") or t.get("tournamentType") or "", "where": t.get("hostNationCode") or "",
                                "link": "https://www.itftennis.com" + (t.get("tournamentLink") or ""), "r": ("Q-" if qual else "") + rnd,
                                "o": f'{(opp.get("givenName") or "")[:1]}. {opp.get("familyName")}'.strip(". "), "on": opp.get("nationality") or "",
                                "res": rc if rc in ("W", "L") else "", "s": score})
        skip += len(items)
        oldest = min((dates_of(t.get("dates"))[1] or T for t in items), default=YEAR_AGO)
        if not items or skip >= (act.get("totalItems") or 0) or oldest < YEAR_AGO or skip >= 100:
            return out


# ---------- Tennis Europe ----------
def te_nat(page):
    m = re.search(r'class="profile-head__nat"[^>]*src="[^"]*/flags/([A-Z]{3})\.svg', page) or \
        re.search(r'src="[^"]*/flags/([A-Z]{3})\.svg"[^>]*class="profile-head__nat"', page)
    return m[1] if m else None


def te_find(p, nat):
    hits = set()
    for name in p["names"]:
        page = TE.fetch("/find/player?q=" + urllib.parse.quote(name))
        hits |= {g.upper() for g, n in re.findall(r'player-profile/([0-9A-Fa-f-]{36})"[^>]*>\s*<span class="nav-link__value">([^<]+)', page)
                 if same_name(html.unescape(n), name)}
    if not hits:
        return "none", None, ""
    if len(hits) > 6:
        return "unsure", None, f"{len(hits)} Tennis Europe players called {p['name']}"
    if nat:  # read each profile's flag: it must be the same nationality as the prospect / their ITF profile
        hits = {h for h in hits if te_nat(TE.fetch(f"/player-profile/{h}")) == nat}
        if not hits:
            return "none", None, ""
    if len(hits) > 1:
        return "unsure", None, f"{len(hits)} Tennis Europe players called {p['name']}" + (f" ({nat})" if nat else "")
    return "linked", hits.pop(), "" if nat else "name only (no nationality known)"


def te_ranking(pid):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(TE.fetch(f"/player-profile/{pid}/ranking"), "html.parser")
    week = None
    for tbl in soup.find_all("table"):
        title = tbl.find_previous(["h2", "h3", "h4", "h5", "caption"])
        trs = tbl.find_all("tr")
        if not title or not trs or "tennis europe ranking" not in title.get_text(" ", strip=True).lower():
            continue
        heads = [c.get_text(" ", strip=True).lower() for c in trs[0].find_all(["th", "td"])]
        if "rank" not in heads:
            continue
        wk = re.search(r"\b(\d{1,2})-(\d{4})\b", title.get_text(" ", strip=True))
        if wk:
            week = date.fromisocalendar(int(wk[2]), int(wk[1]), 1).isoformat()
        rows = []
        for tr in trs[1:]:
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
        return [r for r in rows if r["rank"]]
    return []


def te_results(pid, names):
    out = {}
    for year in (T.year, T.year - 1) if T.month < 12 else (T.year,):
        path = f"/player-profile/{pid}/tournaments" + ("" if year == T.year else f"/{year}")
        try:
            page = TE.fetch(path)
        except TE.Stop:
            raise
        except Exception as e:
            print("  Tennis Europe", path, "failed:", e); continue
        for m in TE.parse(page, "me", names):
            if m["status"] != "finished" or m["date"] < YEAR_AGO.isoformat():
                continue
            won = m["p1Id"] == "me"
            score = m["score"] if won else re.sub(r"(\d+)-(\d+)", r"\2-\1", m["score"])  # the prospect's games first
            out[m["matchId"]] = {"src": "te", "start": m["date"], "end": m["date"], "t": m["tournament"], "cat": m["category"].replace("Tennis Europe · ", ""),
                                 "where": "", "link": m.get("link") or "", "r": m["round"], "o": m["p2"] if won else m["p1"], "on": "",
                                 "res": "W" if won else "L", "s": score}
    return list(out.values())


# ---------- ranking history (for 1 week / 3 month / 12 month moves) ----------
def remember(hist, week, rank):
    if week and rank:
        hist[week] = rank
        for w in [w for w in hist if w < (T - timedelta(days=400)).isoformat()]:
            del hist[w]


def moves(hist, week):
    """-1 = not tracked then (the history starts when the prospect was added); None = not ranked then."""
    if not week:
        return {}
    w0 = date.fromisoformat(week)
    res = {}
    for k, d in (("w", 7), ("m3", 91), ("m12", 364)):
        near = [w for w in hist if abs((date.fromisoformat(w) - (w0 - timedelta(days=d))).days) <= 3]
        res[k] = hist[near[0]] if near else -1
    return res


def itf_week(s):
    try:
        d = datetime.strptime(s, "%d %B %Y").date()
        return (d - timedelta(days=d.weekday())).isoformat()
    except (TypeError, ValueError):
        return None


# ---------- who is on the list ----------
def prospects():
    """Hand list first (it wins), then names added on the site."""
    out, errors = {}, {}
    for p in load(LIST, {}).get("players") or []:
        if p.get("name"):
            out[key_of(p["name"])] = dict(p, src="list")
    try:
        req = urllib.request.Request(SHEET_URL + "?kind=prospects", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            sheet = json.loads(r.read().decode("utf-8", "replace"))
        for p in sheet.get("prospects") or []:
            k = key_of(p.get("name"))
            if k and k not in out:
                out[k] = {"name": p["name"].strip(), "g": p.get("g"), "nat": p.get("nat"), "born": p.get("born"),
                          "src": "site", "by": p.get("by"), "added": p.get("at")}
    except Exception as e:
        errors["sheet"] = {"at": iso(NOW), "msg": f"names added on the site couldn't be read ({str(e)[:120]})"}
    for p in out.values():
        p["names"] = [n.strip() for n in p["name"].split("|") if n.strip()]
        p["name"] = p["names"][0]
        p["g"] = {"m": "M", "b": "M", "boy": "M", "male": "M", "f": "F", "g": "F", "girl": "F", "female": "F"}.get(str(p.get("g") or "").strip().lower())
        p["nat"] = (str(p.get("nat") or "").strip().upper()[:3]) or None
        try:
            p["born"] = int(p.get("born")) if p.get("born") else None
        except (TypeError, ValueError):
            p["born"] = None
    return out, errors


def pro_row(scout, tour, rank, names, nat, born):
    """The scouting.json row for this player: same official rank and surname, else the only one with this name (+ nationality)."""
    rows = (scout.get(tour) or {}).get("players") or []
    sur = {norm(n).split()[-1] for n in names}
    if rank:
        hit = [r for r in rows if r[0] == rank and sur & set(norm(r[1]).split())]
        if len(hit) == 1:
            return hit[0], "ITF id"
    hit = [r for r in rows if any(same_name(r[1], n) for n in names) and (not nat or r[2] == nat) and (not born or not r[3] or r[3] == born)]
    if len(hit) == 1 and (nat or born):
        return hit[0], "name + " + ("nationality" if nat else "birth year")
    return None, None


def main():
    force = os.environ.get("FORCE") == "1"
    data = load(OUT, {})
    before = json.dumps({k: v for k, v in data.items() if k != "checked"}, sort_keys=True)
    players = data.setdefault("players", {})
    errors = data.setdefault("errors", {})
    plist, errs = prospects()
    old = errors.pop("sheet", None)
    if "sheet" in errs and old and ago(old.get("at")) < timedelta(hours=20):
        errs["sheet"] = old  # same problem as earlier today: keep it as it was (no new commit every run)
    errors.update(errs)
    if "sheet" in errs and not plist:
        print(errs["sheet"]["msg"])
    for k in [k for k in players if k not in plist]:
        if players[k].get("src") == "site" and "sheet" in errs:
            continue  # the Sheet couldn't be read this time: keep the names added on the site
        del players[k]  # taken off the list
    scout = load("scouting.json", {})
    checks = []
    blocked = {s: ago(data.get("blocked", {}).get(s)) < timedelta(hours=3) for s in ("itf", "te")}
    te_ok = False

    def due(k):
        r = players.get(k) or {}
        return force or r.get("day") != T.isoformat()

    todo = sorted((k for k in plist if due(k)), key=lambda k: (k in players, (players.get(k) or {}).get("day") or ""))
    # the daily refresh starts at 05:00 UK; before that only new names are looked up
    if NOW.astimezone(UK).hour < 5 and not force:
        todo = [k for k in todo if k not in players]
    print(f"Scouting Corner: {len(plist)} prospects, {len(todo)} to refresh")

    for k in todo:
        if out_of_time():
            print("time budget used - the next run carries on"); break
        p = plist[k]
        rec = players.setdefault(k, {"links": {}, "hist": {}})
        rec.update({"name": p["name"], "g": p.get("g"), "src": p["src"], "by": p.get("by"), "added": p.get("added") or rec.get("added") or T.isoformat()})
        rec["nat"] = p.get("nat") or rec.get("nat")
        L = rec.setdefault("links", {})
        H = rec.setdefault("hist", {})
        res = {r["src"]: [] for r in rec.get("results") or []}
        for r in rec.get("results") or []:
            res[r["src"]].append(r)
        done_all = True
        print("-", p["name"])

        # 1) ITF: the anchor for juniors and pros
        if not blocked["itf"]:
            try:
                li = L.get("itf") or {}
                if p.get("itf") and li.get("id") != int(p["itf"]):
                    li = {"id": int(p["itf"]), "status": "linked", "how": "pinned in prospects.json"}
                if li.get("status") != "linked" and (force or ago(li.get("tried")) > RECHECK or li.get("q") != [p["name"], p.get("nat"), p.get("g")]):
                    st, pid, nat, circ, note = itf_find(p)
                    li = {"status": st, "tried": iso(NOW), "q": [p["name"], p.get("nat"), p.get("g")]}
                    if pid:
                        li.update({"id": pid, "nat": nat, "circuits": circ, "how": "name + nationality" if p.get("nat") else "name"})
                    if note:
                        li["note"] = note
                L["itf"] = li
                if li.get("status") == "linked":
                    pid = li["id"]
                    rec["nat"] = rec.get("nat") or li.get("nat")
                    if not rec.get("g") and li.get("circuits"):
                        rec["g"] = "M" if "MT" in li["circuits"] else "F" if "WT" in li["circuits"] else None
                    jr = itf_overview(pid, "JT")
                    if jr.get("rank") or jr.get("high"):
                        rec["itfJr"] = jr
                        remember(H.setdefault("itfJr", {}), itf_week(jr.get("date")), jr.get("rank"))
                    res["itf-jr"] = itf_results(pid, "JT", "itf-jr")
                    if rec.get("g"):
                        pro = itf_overview(pid, "MT" if rec["g"] == "M" else "WT")
                        rec["itfPro"] = pro  # official ATP / WTA rank as the ITF shows it
                        res["itf-pro"] = itf_results(pid, "MT" if rec["g"] == "M" else "WT", "itf-pro")
            except Blocked as e:
                print(" ", e, "- ITF left alone for 3 hours")
                blocked["itf"] = True
                data.setdefault("blocked", {})["itf"] = iso(NOW)
                done_all = False
            except Exception as e:
                print("  ITF failed:", e); done_all = False
        else:
            done_all = False

        # 2) ATP / WTA: from the official weekly rankings in scouting.json
        if rec.get("g"):
            tour = "atp" if rec["g"] == "M" else "wta"
            ip = rec.get("itfPro") or {}
            row, how = pro_row(scout, tour, ip.get("rank") if "singles" in (ip.get("name") or "").lower() else None, p["names"], rec.get("nat"), p.get("born"))
            if row:
                L["pro"] = {"status": "linked", "tour": tour, "name": row[1], "url": row[7], "how": how}
                rec["pro"] = {"tour": tour, "rank": row[0], "week": (scout.get(tour) or {}).get("week"), "w": row[4], "m3": row[5], "m12": row[6],
                              "high": ip.get("high"), "highDate": ip.get("highDate")}
                rec["born"] = row[3] or p.get("born")
            else:
                L["pro"] = {"status": "none"}
                rec.pop("pro", None)
        rec["born"] = rec.get("born") or p.get("born")

        # 3) Tennis Europe (U12-U16), checked against the ITF nationality
        if not blocked["te"]:
            try:
                if not te_ok:
                    TE.consent(); te_ok = True
                lt = L.get("te") or {}
                if p.get("te") and lt.get("id") != p["te"].upper():
                    lt = {"id": p["te"].upper(), "status": "linked", "how": "pinned in prospects.json"}
                if lt.get("status") != "linked" and (force or ago(lt.get("tried")) > RECHECK or lt.get("q") != [p["name"], rec.get("nat")]):
                    st, tid, note = te_find(p, rec.get("nat"))
                    lt = {"status": st, "tried": iso(NOW), "q": [p["name"], rec.get("nat")]}
                    if tid:
                        lt.update({"id": tid, "how": "name + nationality" if rec.get("nat") else "name"})
                    if note:
                        lt["note"] = note
                L["te"] = lt
                if lt.get("status") == "linked":
                    ranks = te_ranking(lt["id"])
                    rec["te"] = ranks
                    for r in ranks:
                        remember(H.setdefault("te:" + r["cat"], {}), r["week"], r["rank"])
                    res["te"] = te_results(lt["id"], "|".join(p["names"]))
            except TE.Stop as e:
                print(" ", e, "- Tennis Europe left alone for 3 hours")
                blocked["te"] = True
                data.setdefault("blocked", {})["te"] = iso(NOW)
                done_all = False
            except Exception as e:
                print("  Tennis Europe failed:", e); done_all = False
        else:
            done_all = False

        # moves for the junior rankings, from the history kept here (ATP/WTA moves come from scouting.json)
        if rec.get("itfJr"):
            rec["itfJr"].update(moves(H.get("itfJr") or {}, itf_week(rec["itfJr"].get("date"))))
        for r in rec.get("te") or []:
            r.update(moves(H.get("te:" + r["cat"]) or {}, r.get("week")))
        rec["results"] = sorted((r for rs in res.values() for r in rs), key=lambda r: (r["end"], r["start"]), reverse=True)
        if done_all:
            rec["day"] = T.isoformat()
        rec["updated"] = iso(NOW)

    # anything a person needs to check (report_gaps.py alerts each message once, so no times in the text)
    for k, rec in players.items():
        for stage, label in (("itf", "ITF"), ("te", "Tennis Europe")):
            l = (rec.get("links") or {}).get(stage) or {}
            if l.get("status") == "unsure":
                checks.append(f"{rec['name']}: more than one {label} player fits ({l.get('note')}). "
                              f"Add the right id as \"{stage}\" for them in prospects.json so the right one is linked.")
            elif l.get("status") == "linked" and (l.get("note") or "").startswith("name only"):
                checks.append(f"{rec['name']}: linked to {label} id {l.get('id')} by name only. Add their nationality in prospects.json (or on the site) to confirm it.")
        if not any(((rec.get("links") or {}).get(s) or {}).get("status") in ("linked", "unsure") for s in ("itf", "te", "pro")) and rec.get("day"):
            checks.append(f"{rec['name']}: not found on Tennis Europe, the ITF or the ATP/WTA rankings. Check the spelling.")
    data["checks"] = checks
    for s in ("itf", "te"):
        if not blocked[s]:
            data.get("blocked", {}).pop(s, None)
    if json.dumps({k: v for k, v in data.items() if k != "checked"}, sort_keys=True) == before:
        print("nothing new"); return  # no commit for a run that changed nothing
    data["checked"] = iso(NOW)
    with open(OUT, "w") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"done: {sum(1 for r in players.values() if r.get('day') == T.isoformat())} of {len(players)} refreshed today, {len(checks)} to check")


if __name__ == "__main__":
    main()
