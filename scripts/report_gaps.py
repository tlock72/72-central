"""
72 Central - tells Tobey when information has been missed (no Claude).

Runs at the end of each update. Looks at the saved data for anything missing - a match with no
result, a check that was blocked, rankings that could not be refreshed - and posts it to an open
GitHub issue called "72 Central: missing info" (GitHub emails the repository owner). Each problem
is only reported once.
"""
import json, os, subprocess
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

UK = ZoneInfo("Europe/London")
NOW = datetime.now(timezone.utc)
UK_NOW = NOW.astimezone(UK)
TODAY = UK_NOW.date()
TITLE = "72 Central: missing info"
OWNER = os.environ.get("GITHUB_REPOSITORY_OWNER", "")


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
    # 5) ATP/WTA rankings
    d = load("data.json")
    if d.get("rankingsAsOf") and d["rankingsAsOf"] < ago(9):
        out.append(f"ATP/WTA rankings haven't been fully updated since {d['rankingsAsOf']}.")
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
