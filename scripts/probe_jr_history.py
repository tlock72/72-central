"""One-off check (safe to delete): can past ITF junior rankings be rebuilt from the ITF's own results + points?
Reads how a public project computes junior ranking points from ITF data (its code and rules file), and shows the
raw shape of the ITF's results calls for one 72 junior. A handful of ITF requests; stops at the bot check."""
import json, re, subprocess, time, urllib.parse, urllib.request

UA = "72HubRankings/1.0 (+https://github.com/tlock72/72-central; one-off check)"
ITF = "https://www.itftennis.com/tennis/api"
for repo in ("genaromoraes/itf-juniors-live-ranking", "genaromoraes/versaoantiga_itf-juniors-live-ranking"):
    d = "/tmp/" + repo.split("/")[1]
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"https://github.com/{repo}.git", d], check=True)
    out = subprocess.run(["bash", "-c", f"cd {d} && grep -rhoE 'tennis/api/[A-Za-z]+/[A-Za-z]+[^\"\\x27 `]*' --include=*.js --include=*.mjs --include=*.ts --include=*.py --include=*.json . | sed 's/[?].*//' | sort | uniq -c | sort -rn | head -40"], capture_output=True, text=True).stdout
    print(f"===== {repo} ITF calls used:\n{out}")
    out = subprocess.run(["bash", "-c", f"cd {d} && ls -R | head -80; for f in $(find . -name '*rules*' -o -name '*points-table*' -o -name '*points_table*' | grep -v node_modules | head -5); do echo \"--- $f\"; head -c 3000 $f; echo; done"], capture_output=True, text=True).stdout
    print(out)
    out = subprocess.run(["bash", "-c", f"cd {d} && for f in data/clean/points_ledger.csv data/player-points.csv; do [ -f $f ] && echo \"--- $f ($(wc -l < $f) lines)\" && head -4 $f | cut -c1-600; done; grep -rn 'best\\|melhores\\|countin\\|weight\\|0.25\\|25%' --include=*.js --include=*.mjs --include=*.py . 2>/dev/null | grep -v node_modules | head -25"], capture_output=True, text=True).stdout
    print(out)


def get(path, **q):
    time.sleep(4)
    req = urllib.request.Request(f"{ITF}{path}?{urllib.parse.urlencode(q)}", headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            b = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code} {e.read()[:300]}"
    if "_Incapsula_Resource" in b:
        raise SystemExit("ITF bot check - stopping")
    return b


JR = 800570117  # Jamie Mackenzie
b = get("/PlayerApi/GetPlayerActivity", circuitCode="JT", matchTypeCode="S", playerId=JR, skip=0, take=2)
try:
    d = json.loads(b)
    print("===== GetPlayerActivity keys:", list(d) if isinstance(d, dict) else type(d))
    it = (d.get("items") or [])[:1]
    print(json.dumps(it, indent=1)[:4000])
    print("totalItems", d.get("totalItems"))
except Exception:
    print("activity raw:", b[:800])
b = get("/PlayerApi/GetPlayerActivity", circuitCode="JT", matchTypeCode="D", playerId=JR, skip=0, take=1)
print("===== doubles activity:", b[:1500])
b = get("/PlayerApi/GetPlayerActivity", circuitCode="JT", matchTypeCode="S", playerId=JR, skip=0, take=1, year=2023)
print("===== activity year=2023:", b[:1200])
