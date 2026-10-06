"""One-off check: can past ITF junior / Tennis Europe ranking weeks be read? Prints what each source returns."""
import json, os, re, sys, time, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import te_matches as TE

ITF = "https://www.itftennis.com/tennis/api"
UA = "72HubRankings/1.0 (+https://github.com/tlock72/72-central; one-off check, one request every few seconds)"
ITF_ID, TE_ID = 800480856, "F9773361-4868-4A44-9558-4C366AEB8AF9"  # Dylan Dietrich


def get(url):
    time.sleep(5)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json, text/html"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, str(e)


def show(label, st, body, n=2500):
    print(f"\n===== {label} -> HTTP {st}, {len(body)} chars")
    print(body[:n])


# ITF: the overview the site already uses, then likely names for a history call
st, body = get(f"{ITF}/PlayerApi/GetPlayerOverview?circuitCode=JT&matchTypeCode=S&playerId={ITF_ID}")
show("ITF overview", st, body, 4000)
for path in ("PlayerApi/GetPlayerRankingHistory", "PlayerApi/GetPlayerRankings", "PlayerApi/GetRankingHistory",
             "PlayerRankApi/GetPlayerRankings", "PlayerRankApi/GetPlayerRankHistory", "RankingsApi/GetPlayerRankingHistory"):
    st, body = get(f"{ITF}/{path}?circuitCode=JT&matchTypeCode=S&playerId={ITF_ID}")
    show("ITF " + path, st, body, 1200)
# ITF full ranking list for a past week (the rankings page has a date picker)
for path in ("RankApi/GetDatesForRankings?circuitCode=JT&matchTypeCode=S&ageCategoryCode=&nationCode=",
             "RankApi/GetPlayerRankings?circuitCode=JT&matchTypeCode=S&ageCategoryCode=&take=5&skip=0&isOrderAscending=true"):
    st, body = get(f"{ITF}/{path}")
    show("ITF " + path, st, body, 1500)
# the profile page itself, to find the real API names in its scripts
st, body = get(f"https://www.itftennis.com/en/players/dylan-dietrich/{ITF_ID}/sui/jt/s/rankings/")
show("ITF profile page", st, body, 600)
print("API paths seen:", sorted(set(re.findall(r"tennis/api/[A-Za-z]+/[A-Za-z]+", body))))
for js in sorted(set(re.findall(r'src="([^"]+\.js[^"]*)"', body)))[:15]:
    st, src = get(urllib.parse.urljoin("https://www.itftennis.com/", js))
    paths = sorted(set(re.findall(r"[A-Za-z]+Api/[A-Za-z]+", src)))
    if paths:
        print("JS", js, "->", paths)

# Tennis Europe: the ranking page the site already reads, looking for week pickers / history
TE.consent()
for path in (f"/player-profile/{TE_ID}/ranking", f"/player-profile/{TE_ID}/ranking/history", "/ranking"):
    try:
        page = TE.fetch(path)
    except Exception as e:
        print("\n===== TE", path, "failed:", e); continue
    print(f"\n===== TE {path}: {len(page)} chars")
    text = re.sub(r"\s+", " ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S))
    i = text.lower().find("tennis europe ranking")
    print(re.sub(r"<[^>]+>", " | ", text[max(0, i - 500):i + 3000]) if i >= 0 else text[:1500])
    print("links:", sorted(set(re.findall(r'href="([^"]*(?:rank|history|week)[^"]*)"', page, flags=re.I)))[:40])
    print("selects:", [re.sub(r"\s+", " ", s)[:600] for s in re.findall(r"<select.*?</select>", page, flags=re.S | re.I)][:5])
