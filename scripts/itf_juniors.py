"""
72 Hub - weekly ITF junior rankings (runs on GitHub Actions on Mondays, no Claude needed).

For each 72 junior it reads the player's ITF World Tennis Junior Ranking (current and
career-high) from the ITF website, one player at a time with a pause between requests,
and writes itf.json. If the ITF site answers with its bot check instead of data, the
script stops straight away (it never tries to get past the check) and lists the players
it could not refresh under "pending", so the follow-up Claude step can fill them in.
"""
import json, os, time, unicodedata, urllib.parse, urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

BASE = "https://www.itftennis.com/tennis/api"
UA = "72HubRankings/1.0 (+https://github.com/tlock72/72-central; weekly, one request every few seconds)"
PAUSE = 6  # seconds between requests

# id -> (name as the ITF spells it, ITF player id or None to look it up, "B" boys / "G" girls)
JUNIORS = {
    "ivanov": ("Ivan Ivanov", None, "B"), "bonding": ("Oliver Bonding", 800544649, "B"),
    "mackenzie": ("Jamie Mackenzie", 800570117, "B"), "chavez": ("Tito Chavez", 800590474, "B"),
    "qi": ("Hongjin Qi|Hongjing Qi", None, "B"), "fazekas": ("Vencel Fazekas", 800703915, "B"),
    "choi": ("Fu Wang Choi", 800740257, "B"), "drijver": ("Laurens Drijver", 800695508, "B"),
    "daraban": ("Luca Daraban", 800678733, "B"), "tarlazzi": ("Diego Tarlazzi", 800708323, "B"),
    "farkxodov": ("Saidaslam Farkxodov", 800748198, "B"), "mateo": ("Jorge Mateo Moreno", 800740453, "B"),
    "davies": ("Fletcher Davies", None, "B"), "momot": ("Henry Momot", None, "B"), "liu": ("Xichen Liu", None, "B"),
    "rajeshwaran": ("Maaya Rajeshwaran Revathi", None, "G"), "pinera": ("Paola Pinera Celorio", 800656554, "G"),
    "skryp": ("Violetta Skryp", 800733549, "G"), "mmakarova": ("Mariia Makarova", 800644962, "G"),
    "vmakarova": ("Varvara Makarova", 800822494, "G"), "dotsenko": ("Ekaterina Dotsenko", 800677532, "G"),
    "lin": ("Yu Jun Lin", 800739107, "G"), "newman": ("Welles Newman", 800705703, "G"),
    "kanabar": ("Jensi Dipakbhai Kanabar", 800741292, "G"), "kurylova": ("Nicole Kurylova", 800743118, "G"),
    "iwasa": ("Ayaka Iwasa", 800722468, "G"),
}


class Blocked(Exception):
    pass


def get(path, **params):
    time.sleep(PAUSE)
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8", "replace")
    if not body.lstrip().startswith(("{", "[")):
        raise Blocked("ITF answered with its bot check, stopping")
    return json.loads(body)


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).lower().replace("-", " ").split())


def find_id(names):
    for name in names.split("|"):
        res = get("/PlayerApi/GetPlayerSearch", searchString=name)
        want = set(norm(name).split())
        for p in res.get("players") or []:
            have = set(norm(f'{p.get("givenName")} {p.get("familyName")}').split())
            if want <= have or (len(have) >= 2 and have <= want):
                return p["playerId"]
    return None


def main():
    uk = datetime.now(timezone.utc).astimezone(ZoneInfo("Europe/London"))
    today = uk.strftime("%Y-%m-%d")
    try:
        data = json.load(open("itf.json"))
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    players = data.setdefault("players", {})
    if data.get("checked") == today and not data.get("pending") and os.environ.get("FORCE") != "1":
        print("Already refreshed today"); return

    pending = []
    blocked = False
    for pid, (name, itf_id, gender) in JUNIORS.items():
        rec = players.setdefault(pid, {})
        rec["gender"] = gender
        itf_id = rec.get("itfId") or itf_id
        if blocked:
            pending.append(pid); continue
        if rec.get("noItf") and not itf_id and uk.day > 7:
            continue  # confirmed to have no ITF junior profile yet; re-checked on the first Monday of each month
        try:
            if not itf_id:
                itf_id = find_id(name)
                if not itf_id:
                    print("not found on ITF:", name)
                    pending.append(pid); continue
            rec["itfId"] = itf_id
            rec.pop("noItf", None)
            ov = get("/PlayerApi/GetPlayerOverview", circuitCode="JT", matchTypeCode="S", playerId=itf_id)
            cur = next((r for r in ov.get("rankings") or [] if "Junior" in (r.get("name") or "")), None)
            hi = next((r for r in ov.get("careerHighRankings") or [] if "Junior" in (r.get("name") or "")), None)
            prev = rec.get("rank")
            rank = cur.get("rank") if cur else None
            if cur and cur.get("date") and cur.get("date") != rec.get("rankDate"):
                rec["move"] = (prev - rank) if (prev and rank) else None
            rec.update({"rank": rank, "rankDate": cur.get("date") if cur else None,
                        "high": hi.get("rank") if hi else None, "highDate": hi.get("date") if hi else None,
                        "updated": today})
            if cur and cur.get("date"):
                data["rankDate"] = cur["date"]
            print(f"{name}: {rank} (high {rec['high']})")
        except Blocked as e:
            print(e); blocked = True; pending.append(pid)
        except Exception as e:  # network hiccup: leave the old figure, retry on the next run
            print("failed", name, e); pending.append(pid)

    data["checked"] = today
    data["pending"] = pending
    data["source"] = "ITF World Tennis Junior Rankings"
    with open("itf.json", "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"done, {len(pending)} pending")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"pending={'true' if pending else 'false'}\n")


if __name__ == "__main__":
    main()
