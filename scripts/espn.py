"""
ESPN's free public scoreboard: the main source for ATP and WTA matches (tour events, their qualifying, and
WTA 125s). No key, no sign-up and no daily limit. Challengers, ITF events and juniors aren't on it, so those stay
on the Live Tennis API (update.py). Tested 6 Oct 2026: every recent ATP/WTA match of ours was there, and the
finished scores matched the Live Tennis API exactly.

fetch() returns {"e<ESPN id>": match} in the same shape update.py uses, for singles matches with a 72 player.
A match is only "finished" when ESPN marks it final with a winner; nothing is guessed from a live score.
"""
import json, re, unicodedata, urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

SITE = "https://site.api.espn.com/apis/site/v2/sports/tennis"
UK = ZoneInfo("Europe/London")
ROUNDS = {"final": "Final", "semifinal": "SF", "quarterfinal": "QF", "round 1": "1R", "round 2": "2R", "round 3": "3R",
          "round 4": "4R", "round of 16": "R16", "qualifying 1st round": "Q1", "qualifying 2nd round": "Q2",
          "qualifying 3rd round": "Q3", "qualifying final": "Q final"}

# Hand corrections for ESPN mistakes, by ESPN match id (the "apiId" in data.json, e.g. "e184927").
#   "winner": surname of who really won (e.g. the player who got a walkover ESPN gave the wrong way round)
#   "drop": True leaves the match off the site (e.g. a next round ESPN made up from its own mistake)
# Delete a line once the match is more than a week old.
FIXES = {
    "e184927": {"winner": "Molcan"},  # Shanghai 2R, 9 Oct 2026: De Minaur withdrew, ESPN gave him the walkover
    "e184929": {"drop": True},        # Shanghai 3R: ESPN still has De Minaur v Sakamoto
}


def fold(s):
    """Lower-case words without accents; umlauts written as 'ae' count as the plain letter (Schwaerzler = Schwärzler)."""
    s = unicodedata.normalize("NFKD", (s or "").lower().replace("ß", "ss")).encode("ascii", "ignore").decode()
    s = re.sub(r"(?<=[a-z])(ae|oe|ue)", lambda m: m.group(1)[0], s)
    return re.findall(r"[a-z]+", s)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (72Central score updater)", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def short(name):
    p = (name or "").split()
    return f"{p[0][0]}. {' '.join(p[1:])}" if len(p) > 1 else (name or "")


def category(city, women, day, events, known):
    """'ATP 500', 'WTA 1000', 'WTA 125'... from the Tour Schedule calendar (schedule.json), by city and date, or else
    from what the site already recorded for that tournament (the calendar only starts from the current week)."""
    want = set(fold(city))
    for e in events:
        ok_tour = e.get("tour") == ("wta" if women else "atp") or (women and e.get("tour") == "itfw" and "125" in (e.get("cat") or ""))
        if not ok_tour or not want or not want <= set(fold(f'{e.get("place")} {e.get("name")}')):
            continue
        if not e.get("start") or not e.get("end"):
            continue
        # ATP events only give their first week, so allow for qualifying before and a second week after
        if (date.fromisoformat(e["start"]) - timedelta(days=3)).isoformat() <= day <= (date.fromisoformat(e["end"]) + timedelta(days=7)).isoformat():
            return e.get("cat") or ("WTA" if women else "ATP")
    return known.get((" ".join(fold(city)), "wta" if women else "atp")) or ("WTA" if women else "ATP")


def score(c1, c2):
    """'7-6(4), 6-3' from player 1's side; a tiebreak shows the loser's points, as on the rest of the site."""
    out = []
    for a, b in zip(c1.get("linescores") or [], c2.get("linescores") or []):
        s = f'{int(a.get("value", 0))}-{int(b.get("value", 0))}'
        tbs = [x.get("tiebreak") for x in (a, b) if x.get("tiebreak") not in (None, "")]
        if tbs:
            s += f"({int(min(float(t) for t in tbs))})"
        out.append(s)
    return ", ".join(out)


def fetch(roster, events, now, matches=()):
    """roster: {rid: (full name, "atp"|"wta")}; events: schedule.json events; now: aware datetime (UTC);
    matches: the site's current matches, whose categories are reused for tournaments the calendar no longer has."""
    known = {}
    for m in matches:
        c = m.get("category") or ""
        if re.match(r"(ATP|WTA) \d", c):
            known[(" ".join(fold(m.get("tournament"))), c[:3].lower())] = c
    courts = {m["apiId"]: m["court"] for m in matches if m.get("apiId") and m.get("court")}
    names = {}
    for rid, (full, tour) in roster.items():
        names[(tour, " ".join(sorted(fold(full))))] = rid
    today = now.astimezone(UK).date()
    lo, hi = (today - timedelta(days=7)).isoformat(), (today + timedelta(days=7)).isoformat()
    out = {}
    for league in ("atp", "wta"):
        for d in (-1, 0, 6):  # each day's scoreboard holds every match of the events running that day
            day = (today + timedelta(days=d)).strftime("%Y%m%d")
            js = get(f"{SITE}/{league}/scoreboard?dates={day}")
            for ev in js.get("events") or []:
                for g in ev.get("groupings") or []:
                    slug = (g.get("grouping") or {}).get("slug") or ""
                    if slug not in ("mens-singles", "womens-singles"):
                        continue
                    women = slug.startswith("womens")
                    for c in g.get("competitions") or []:
                        key = f'e{c.get("id")}'
                        if key in out:
                            continue
                        cs = sorted(c.get("competitors") or [], key=lambda p: p.get("order") or 0)
                        if len(cs) != 2 or not all((p.get("athlete") or {}).get("displayName") not in (None, "", "TBD") for p in cs):
                            continue  # a draw slot still waiting for its player
                        full = [p["athlete"]["displayName"] for p in cs]
                        ids = [names.get(("wta" if women else "atp", " ".join(sorted(fold(n))))) for n in full]
                        if not any(ids):
                            continue
                        when = datetime.fromisoformat(c["date"].replace("Z", "+00:00")).astimezone(UK)
                        day_uk = when.strftime("%Y-%m-%d")
                        if not lo <= day_uk <= hi:
                            continue
                        st = (c.get("status") or {}).get("type") or {}
                        state, detail = st.get("state"), (st.get("detail") or st.get("description") or "")
                        # play stopped mid-match (rain, light, suspended overnight): still in progress, marked as delayed
                        stopped = re.search(r"suspend|delay|interrupt|rain|halt", f'{st.get("name") or ""} {detail}', re.I)
                        city = ((c.get("venue") or {}).get("fullName") or "").split(",")[0].strip() or ev.get("shortName") or ev.get("name") or ""
                        rnd = ((c.get("round") or {}).get("displayName") or "")
                        m = {"apiId": key, "src": "espn", "date": day_uk, "time": when.strftime("%H:%M") if c.get("timeValid", True) else "",
                             "timeAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                             "tournament": city, "category": category(city, women, day_uk, events, known),
                             "round": ROUNDS.get(rnd.lower(), rnd), "p1": short(full[0]), "p1Id": ids[0],
                             "p2": short(full[1]), "p2Id": ids[1], "status": "scheduled", "score": "", "points": None,
                             "server": None, "winner": None}
                        court = str((c.get("venue") or {}).get("court") or "").strip() or courts.get(key)
                        if court:
                            m["court"] = court
                        won = [i + 1 for i, p in enumerate(cs) if p.get("winner")]
                        if state == "in" or (state == "post" and not won and stopped and score(*cs)):
                            m.update(status="live", score=score(*cs))
                            if stopped:
                                m["delay"] = detail or "Delayed"
                        elif state == "post" and len(won) == 1:
                            sc = "" if re.search(r"walkover", detail, re.I) else score(*cs)
                            if re.search(r"retire|default", detail, re.I) and sc:
                                sc += " ret."
                            if re.search(r"walkover", detail, re.I):
                                m["round"] = (m["round"] + " (walkover)").strip()
                            m.update(status="finished", score=sc, winner=won[0])
                            if won[0] == 2:  # the site always lists the winner first, with the score from their side
                                core = sc[:-5] if sc.endswith(" ret.") else sc
                                flipped = ", ".join(re.sub(r"^(\d+)-(\d+)", r"\2-\1", x) for x in core.split(", ")) if core else ""
                                m.update(p1=m["p2"], p2=m["p1"], p1Id=m["p2Id"], p2Id=m["p1Id"], winner=1,
                                         score=flipped + (" ret." if sc.endswith(" ret.") else ""))
                        elif state == "post" and re.search(r"cancel", detail, re.I):
                            m["status"] = "cancelled"
                        out[key] = m
    for key, fix in FIXES.items():
        m = out.get(key)
        if not m:
            continue
        if fix.get("drop"):
            del out[key]
        elif fix.get("winner") and m["status"] == "finished":
            w = fold(fix["winner"])
            if all(x in fold(m["p2"]) for x in w):  # the site lists the winner first, with the score from their side
                sc = m["score"][:-5] if m["score"].endswith(" ret.") else m["score"]
                sc = ", ".join(re.sub(r"^(\d+)-(\d+)", r"\2-\1", x) for x in sc.split(", ")) if sc else ""
                m.update(p1=m["p2"], p2=m["p1"], p1Id=m["p2Id"], p2Id=m["p1Id"], winner=1,
                         score=sc + (" ret." if m["score"].endswith(" ret.") else ""))
    return out
