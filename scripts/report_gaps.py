"""
72 Central - tells Tobey when information has been missed (no Claude).

Runs at the end of each update, and every few hours on GitHub's own timer as a watchdog
(.github/workflows/watchdog.yml), so it still speaks up if the 30-minute timer stops altogether.
Looks for anything missing or broken - a match with no result, a check that was blocked, rankings
or Scouting HQ that could not be refreshed, a part of the update that failed, updates that have
stopped, or the website not publishing - and posts it to an open GitHub issue called
"72 Central: missing info" (GitHub emails the repository owner). Each problem is only reported once.
"""
import json, os, subprocess, sys, unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

UK = ZoneInfo("Europe/London")
NOW = datetime.now(timezone.utc)
UK_NOW = NOW.astimezone(UK)
TODAY = UK_NOW.date()
TITLE = "72 Central: missing info"
OWNER = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
REPO = os.environ.get("GITHUB_REPOSITORY", "tlock72/72-central")
ACTIONS_URL = f"https://github.com/{REPO}/actions"
STEP_NAMES = {
    "scores": "live scores and ATP/WTA rankings (Live Tennis API)",
    "itfrank": "ITF junior rankings",
    "scouting": "Scouting HQ",
    "itfm": "ITF junior matches",
    "titles": "ITF World Tennis Tour titles",
    "te": "Tennis Europe matches",
    "save": "saving the new data (this usually sorts itself out on the next run)",
    "schedule": "the tour schedule",
    "corner": "Scouting Corner",
    "terank": "the Tennis Europe U14 rankings (Filtered Rankings)",
}


def load(f):
    try:
        return json.load(open(f))
    except Exception:
        return {}


def when(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")) if iso else None


def ukday(iso):
    return when(iso).astimezone(UK).date() if iso else None


def gaps():
    out = []
    ago = lambda days: (TODAY - timedelta(days=days)).isoformat()
    # 1) matches from the last two days that never got a result (checked after 10:00, once each day's checks have run)
    if UK_NOW.hour >= 10:
        for f, src in (("data.json", "score feed"), ("itfm.json", "ITF"), ("te.json", "Tennis Europe")):
            for m in load(f).get("matches") or []:
                if m.get("status") == "scheduled" and ago(2) <= (m.get("date") or "") < TODAY.isoformat():
                    who = " v ".join(x for x in (m.get("p1") or m.get("p1Id"), m.get("p2") or m.get("p2Id")) if x)
                    out.append(f"No result found for {who} ({m.get('tournament')}, {m.get('round') or ''}, {m.get('date')}) "
                               f"from the {src}. Check SofaScore / the event page.")
    # 2) ITF junior matches: last attempt was blocked or failed
    im = load("itfm.json")
    if im.get("tried") and im.get("tried") != im.get("checked"):
        out.append(f"ITF junior matches could not be updated on {ukday(im['tried'])} (the ITF site blocked or failed the check). "
                   "Junior draws and results may be missing until the next check.")
    # 3) Tennis Europe: today's scan failed, or hasn't run by mid-morning
    te = load("te.json")
    if te.get("day") == TODAY.isoformat() and ukday(te.get("checked")) != TODAY:
        out.append(f"Tennis Europe matches could not be updated on {TODAY} (the scan was blocked or failed). "
                   "U14/U16 matches may be missing until tomorrow.")
    elif UK_NOW.hour >= 10 and te.get("day") and te["day"] < TODAY.isoformat():
        out.append(f"The Tennis Europe scan didn't run on {TODAY}.")
    # 4) ITF junior rankings: players the Monday update couldn't refresh, or the update hasn't run
    it = load("itf.json")
    if it.get("pending"):
        out.append(f"ITF junior rankings (week of {it.get('rankDate')}) could not be refreshed for: {', '.join(it['pending'])}. "
                   "Their old ranking is still shown.")
    if it.get("checked") and it["checked"] < ago(8):
        out.append(f"ITF junior rankings haven't been updated since {it['checked']}.")
    # 4b) ITF World Tennis Tour titles: players the daily check couldn't read, or the check hasn't run
    ti = load("titles.json")
    if ti.get("pending"):
        out.append(f"ITF World Tennis Tour titles could not be checked on {ti.get('tried', '')[:10]} for: {', '.join(ti['pending'])} "
                   "(the ITF site blocked or failed the check, or a final couldn't be read). Their saved titles are still counted.")
    if ti.get("checked") and ti["checked"] < ago(3):
        out.append(f"ITF World Tennis Tour titles haven't been checked since {ti['checked']}.")
    # 4c) career highs that don't fit the official rankings or the typed profile (itf_titles.py leaves them blank)
    for rid, b in sorted((ti.get("best") or {}).items()):
        if b.get("issue"):
            out.append(b["issue"])
    # 4d) current ATP/WTA ranking: the live-score feed (data.json) against the official weekly list (scouting.json)
    dj, so = load("data.json"), load("scouting.json")
    try:
        from update import ROSTER
    except Exception:
        ROSTER = {}
    for tour in ("atp", "wta"):
        week = (so.get(tour) or {}).get("week")
        if not week or (dj.get("rankingsTourWeek") or {}).get(tour) != week:
            continue  # only compare the same ranking week
        rows = (so.get(tour) or {}).get("players") or []
        key = lambda n: "".join(c for c in unicodedata.normalize("NFKD", n).lower() if c.isalpha() and c.isascii())
        for rid, (name, t) in ROSTER.items():
            have = ((dj.get("rankings") or {}).get(rid) or {}).get("rank")
            if t != tour or not have:
                continue
            k = key(name.split("|")[0])
            hit = [r for r in rows if key(r[1]) == k] or [r for r in rows if key(r[1]).startswith(k) or k.startswith(key(r[1]))]
            if len(hit) == 1 and hit[0][0] != have:
                out.append(f"Current ranking for {name.split('|')[0]}: the site shows {tour.upper()} No. {have}, but the official "
                           f"{tour.upper()} list for the week of {week} says No. {hit[0][0]}.")
    # 5) ATP/WTA rankings
    d = load("data.json")
    if d.get("quotaHit") and ukday(d["quotaHit"]) == TODAY:
        out.append(f"The live-score feed's free daily allowance ran out on {TODAY}. "
                   "Today's results and 'In progress' updates will be late until it resets overnight.")
    if d.get("espnError") and ukday(d["espnError"].get("at")) == TODAY:
        out.append(f"ESPN's scoreboard (the source for ATP and WTA matches) couldn't be read on {TODAY} "
                   f"({d['espnError'].get('msg')}). The Live Tennis API is covering ATP/WTA until it's back.")
    if (d.get("conflicts") or {}).get("date") == TODAY:
        out.append(f"ESPN and the Live Tennis API disagree on who won: {'; '.join(d['conflicts']['matches'])}. "
                   "No result is shown for these until it's checked. Check SofaScore / the event page.")
    # a tour has published a newer official week (seen by Scouting HQ) but the site still hasn't got it by Wednesday
    tw = d.get("rankingsTourWeek") or {}
    sqw = load("scouting.json")
    for t, name in (("atp", "ATP"), ("wta", "WTA")):
        ow = (sqw.get(t) or {}).get("week")
        if ow and tw.get(t) and ow > tw[t] and (TODAY - datetime.fromisoformat(ow).date()).days >= 2:
            out.append(f"72 Rankings: the {name} ranking of {ow} is out officially, but the site still shows {tw[t]} "
                       "(the score feed hasn't caught up or ran out of calls).")
    # 6) Scouting HQ: a list could not be refreshed today, or is stuck on an old ranking week
    #    (16 days allows for the two-week events, when the tours publish no new ranking)
    sq = load("scouting.json")
    for t, name in (("atp", "ATP"), ("wta", "WTA")):
        e = (sq.get("errors") or {}).get(t)
        wk = (sq.get(t) or {}).get("week")
        if e and ukday(e.get("at")) == TODAY:
            out.append(f"Scouting HQ: the {name} list couldn't be refreshed on {TODAY} ({e.get('msg')}). "
                       f"It still shows the ranking week of {wk or 'an earlier week'}.")
        if wk and wk < ago(16):
            out.append(f"Scouting HQ: the {name} list is still on the ranking week of {wk} - no newer week has been picked up.")
    if not sq:
        out.append("Scouting HQ has no data file (scouting.json is missing or unreadable).")
    # 6a) Filtered Rankings' ITF junior lists (itfjr.json, Mondays) and Tennis Europe U14 lists (terank.json): a list that failed today, or stuck on an old week
    jr = load("itfjr.json")
    te = load("terank.json")
    for src, t, name in ((jr, "b", "ITF junior boys"), (jr, "g", "ITF junior girls"),
                         (te, "b14", "Tennis Europe U14 boys"), (te, "g14", "Tennis Europe U14 girls")):
        e = (src.get("errors") or {}).get(t)
        wk = (src.get(t) or {}).get("week")
        if e and ukday(e.get("at")) == TODAY:
            out.append(f"Filtered Rankings: the {name} list couldn't be refreshed on {TODAY} ({e.get('msg')}). "
                       + (f"It still shows the ranking week of {wk}." if wk else "Nothing is shown for it yet."))
        if wk and wk < ago(16):
            out.append(f"Filtered Rankings: the {name} list is still on the ranking week of {wk} - no newer week has been picked up.")
    # 6b) Tour schedule (schedule.json, once a day): a source that failed today, or no update for 3 days
    sc = load("schedule.json")
    parts = {"atp": "the ATP Tour calendar (Wikipedia)", "challenger": "the Challenger calendar (Wikipedia)", "wta": "the WTA calendar",
             "itf-men": "the ITF men's calendar", "itf-women": "the ITF women's calendar", "itf-juniors": "the ITF junior calendar",
             "te": "the Tennis Europe calendar", "itf-entries": "the ITF acceptance lists (72 entries)", "te-entries": "the Tennis Europe entries",
             "atp-entries": "the ATP and Challenger entries (live-tennis.eu, Tick Tock Tennis and Spazio Tennis all failed)",
             "atp-entries-livetennis": "live-tennis.eu (one of three ATP entry sources; entries the other two list still show)",
             "atp-entries-ticktock": "Tick Tock Tennis (one of three ATP entry sources; entries the other two list still show)",
             "espn-draws": "ESPN's published ATP/WTA draws (entry lists from the other sites still show)",
             "atp-entries-spazio": "Spazio Tennis (one of three ATP entry sources; entries the other two list still show)"}
    for k, e in (sc.get("errors") or {}).items():
        if ukday(e.get("at")) == TODAY:
            out.append(f"Tour schedule: {parts.get(k, k)} couldn't be refreshed on {TODAY} ({e.get('msg')}). The page still shows the previous list.")
    for c in sc.get("checks") or []:  # e.g. a Masters 1000 entry list without one of our top men on it
        out.append(f"Tour schedule: {c}")
    if sc.get("updated") and ukday(sc["updated"]) < TODAY - timedelta(days=3):
        out.append(f"Tour schedule: not updated since {ukday(sc['updated'])}. Check the 'Tour schedule' job: {ACTIONS_URL}")
    # 6b) Scouting Corner: links a person needs to check (unsure, name only, not found), and the site's list not readable
    co = load("corner.json")
    for c in co.get("checks") or []:
        out.append(f"Scouting Corner: {c}")
    for k, e in (co.get("errors") or {}).items():
        if ukday(e.get("at")) == TODAY:
            out.append(f"Scouting Corner: the {(e.get('msg') or '').split(' (')[0]} on {TODAY}. Names on prospects.json still update.")
    # 7) updates have stopped: live scores normally refresh every 30 minutes from 07:13 to 23:43 UK
    lc = when(d.get("lastChecked"))
    if UK_NOW.hour >= 9 and lc and NOW - lc > timedelta(hours=2):
        out.append(f"Live scores haven't updated since {lc.astimezone(UK):%H:%M} UK on {lc.astimezone(UK):%a %d %b}. "
                   "The 30-minute timer seems to have stopped: check the jobs on cron-job.org and that the GitHub "
                   "token it uses hasn't expired (GitHub > Settings > Developer settings > Personal access tokens).")
    # 8) a part of this update run failed (step outcomes are passed in by update-scores.yml)
    try:
        steps = json.loads(os.environ.get("STEPS_JSON") or "{}")
    except Exception:
        steps = {}
    for sid, st in steps.items():
        if (st or {}).get("outcome") == "failure":
            what = STEP_NAMES.get(sid, sid)
            out.append(f"Part of the update failed on {TODAY}: {what}. Details: {ACTIONS_URL}")
    # 9) watchdog only: repeated failed runs, and the website not publishing
    if os.environ.get("WATCHDOG") == "1":
        try:
            runs = json.loads(gh("run", "list", "--workflow", "update-scores.yml", "--limit", "4", "--json", "conclusion,status"))
            done = [r for r in runs if r.get("status") == "completed"]
            if len(done) >= 3 and all(r.get("conclusion") == "failure" for r in done):
                out.append(f"The 'Update scores' job has failed {len(done)} times in a row (seen on {TODAY}). Details: {ACTIONS_URL}")
        except Exception as e:
            print("couldn't read recent runs:", e)
        try:
            b = json.loads(gh("api", f"repos/{REPO}/pages/builds/latest"))
            if b.get("status") == "errored":
                out.append(f"The website didn't publish its latest update (GitHub Pages build failed, seen on {TODAY}). Details: {ACTIONS_URL}")
        except Exception as e:
            print("couldn't read the Pages build:", e)
    return out


def gh(*args):
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=True).stdout


def main():
    problems = gaps()
    if not problems:
        print("nothing missing"); return
    issues = json.loads(gh("issue", "list", "--state", "open", "--search", f'"{TITLE}" in:title', "--json", "number,title,body,comments"))
    issue = next((i for i in issues if i["title"] == TITLE), None)
    said = "" if not issue else issue["body"] + "\n".join(c["body"] for c in issue["comments"])
    new = [p for p in problems if p not in said]
    if not new:
        print("already reported"); return
    text = "\n".join(f"- {p}" for p in new)
    if issue:
        gh("issue", "comment", str(issue["number"]), "--body", f"@{OWNER} more missing info ({UK_NOW:%a %d %b, %H:%M} UK):\n\n{text}")
    else:
        gh("issue", "create", "--title", TITLE, "--body",
           f"@{OWNER} 72 Central couldn't get everything ({UK_NOW:%a %d %b, %H:%M} UK):\n\n{text}\n\n"
           "Close this issue once you've seen it - a new one opens if anything else is missed.")
    print("reported", len(new))


if __name__ == "__main__":
    main()
