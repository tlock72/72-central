"""
Notifications for 72 results, free, no Claude.

After each score update, every newly finished match with a 72 player (ATP/WTA, Challengers and ITF from
data.json, ITF juniors from itfm.json, Tennis Europe from te.json) is sent once to:
  - every phone/computer that pressed "Turn on result alerts" in the site's Settings (Web Push, no app needed;
    on iPhone the site has to be added to the Home Screen first). Needs the secrets VAPID_PRIVATE and ALERTS_KEY.
  - optionally, the free ntfy app, if the secret NTFY_TOPIC is set.
Setup: see NOTIFICATIONS.md. With no secrets set, this does nothing.

Only "finished" results are sent: the feeds' own final result, never a guess (a match where ESPN and the
Live Tennis API disagree on the winner is never "finished"). notified.json remembers what was sent.
"""
import json, os, sys, unicodedata, urllib.parse, urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(__file__))
from update import ROSTER  # roster id -> (full name, tour)
import webpush

TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
VAPID = os.environ.get("VAPID_PRIVATE", "").strip()
ALERTS_KEY = os.environ.get("ALERTS_KEY", "").strip()
SHEET = "https://script.google.com/macros/s/AKfycbwzEb0YNoDmZaaJ5fQg05ubEe_lowMLiGoYaXuclycqQikOngLQEmENPN5KoL_KJXu1kA/exec"  # LOG_URL in index.html
SITE = "https://tlock72.github.io/72-central/"
STATE = "notified.json"
TODAY = datetime.now(ZoneInfo("Europe/London")).date()
RECENT = (TODAY - timedelta(days=2)).isoformat()  # never send old results (e.g. a feed filling in a past match)
MAX_SINGLE = 5  # more new results than this in one run = one combined alert


def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def surname(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return s.replace(".", " ").split()[-1] if s.split() else ""


def name(m, side):
    rid = m.get(f"p{side}Id")
    return ROSTER[rid][0] if rid in ROSTER else (m.get(f"p{side}") or "")


def key(m):
    # Same match from two feeds = same key: 72 player(s), opponent's surname, round, tournament week
    ids = sorted(r for r in (m.get("p1Id"), m.get("p2Id")) if r in ROSTER)
    opp = surname(m.get("p2") if m.get("p1Id") in ROSTER else m.get("p1"))
    return "|".join([",".join(ids), opp, m.get("round") or "", (m.get("date") or "")[:7], surname(m.get("tournament"))])


def text(m):
    w = m.get("winner")
    if w not in (1, 2) or not m.get("score"):
        return None
    win, lose = name(m, w), name(m, 3 - w)
    ours_won = m.get(f"p{w}Id") in ROSTER
    title = f"✅ {win} d. {lose}" if ours_won else f"❌ {lose} lost to {win}"
    where = " · ".join(x for x in (m.get("tournament"), m.get("category"), m.get("round")) if x)
    return title, f"{m['score']}\n{where}"


def sheet(payload=None):
    """The visit-log Sheet: read the sign-ups ("Alerts" tab), or drop one that has expired."""
    if payload is None:
        url = SHEET + "?" + urllib.parse.urlencode({"kind": "alerts", "key": ALERTS_KEY})
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)["alerts"]
    req = urllib.request.Request(SHEET, method="POST", data=json.dumps(payload).encode())
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def deliver(msgs):
    """Sends every (title, body). Raises if a whole channel can't be reached, so nothing is marked sent."""
    if VAPID and ALERTS_KEY:
        subs, ok = sheet(), 0
        for sub in subs:
            gone = False
            for title, body in msgs:
                code = webpush.send(sub, {"title": title, "body": body, "url": SITE}, VAPID)
                ok += code in (200, 201, 202)
                if code in (404, 410):  # this phone turned alerts off or the sign-up expired
                    gone = True
                    break
                if code not in (200, 201, 202):
                    print(f"push to {sub.get('name') or 'a device'} failed: {code}")
            if gone:
                print(f"sign-up from {sub.get('name') or 'a device'} has expired, removing it")
                try:
                    sheet({"kind": "alertsoff", "endpoint": sub["endpoint"]})
                except Exception as e:
                    print("could not remove it:", e)
        print(f"web push: {ok} sent to {len(subs)} device(s)")
    if TOPIC:
        for title, body in msgs:
            req = urllib.request.Request("https://ntfy.sh/", method="POST", headers={"Content-Type": "application/json"},
                                         data=json.dumps({"topic": TOPIC, "title": title, "message": body,
                                                          "tags": ["tennis"], "click": SITE}).encode())
            urllib.request.urlopen(req, timeout=20).close()


def main():
    if not TOPIC and not (VAPID and ALERTS_KEY):
        print("no notification secrets set - notifications off")
        return
    matches = []
    for f in ("data.json", "itfm.json", "te.json"):
        matches += load(f, {}).get("matches") or []
    done = {}
    for m in matches:
        if m.get("status") == "finished" and (m.get("date") or "") >= RECENT and text(m) \
                and (m.get("p1Id") in ROSTER or m.get("p2Id") in ROSTER):
            done.setdefault(key(m), m)

    state = load(STATE, None)
    if state is None:  # first run: remember what's already finished, don't send a flood of old results
        state = {"sent": {k: m["date"] for k, m in done.items()}}
        print(f"first run: {len(done)} existing results remembered, nothing sent")
    else:
        new = [(k, m) for k, m in done.items() if k not in state["sent"]]
        if len(new) > MAX_SINGLE:
            msgs = [(f"🎾 {len(new)} new 72 results", "\n".join(text(m)[0] for _, m in new))]
        else:
            msgs = [text(m) for _, m in new]
        try:
            if msgs:
                deliver(msgs)
                for t, _ in msgs:
                    print("sent:", t)
            state["sent"].update((k, m["date"]) for k, m in new)
        except Exception as e:  # not marked as sent, so the next run tries again
            print("alerts could not be sent:", e)
    state["sent"] = {k: d for k, d in state["sent"].items() if d >= (TODAY - timedelta(days=14)).isoformat()}
    with open(STATE, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
