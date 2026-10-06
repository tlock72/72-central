"""One-off check: can past ITF junior / Tennis Europe ranking weeks be read? Prints what each source returns."""
import json, os, re, sys, time, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import te_matches as TE

UA = "72HubRankings/1.0 (+https://github.com/tlock72/72-central; one-off check, one request every few seconds)"
TE_ID = "2F65EB7D-F034-4088-A2F5-86292F475429"  # Giulia Luchetti (TE U14 #6)


def get(url):
    time.sleep(5)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, str(e)


def flat(page):
    page = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", page))


# ITF: how the site's own script calls the ranking APIs (which parameters, any date)
st, js = get("https://itftennis-ep.azureedge.net/media/assets/bundle.js?key=@assemblyVersion")
print("bundle", st, len(js))
for word in ("PlayerRankApi/GetPlayerRankings", "PlayerRankApi/GetTopCircuitRankings"):
    for m in list(re.finditer(re.escape(word), js))[:2]:
        print(f"\n===== {word} context\n", js[max(0, m.start() - 1500):m.end() + 1500])
for word in ("rankingDate", "RankingDate", "weekDate", "dateId", "DateId", "rankDate", "historic"):
    hits = [js[max(0, m.start() - 200):m.end() + 200] for m in re.finditer(word, js)][:3]
    for h in hits:
        print(f"\n----- {word}:", h)

# Tennis Europe: the ranking list page (week picker) and the prospect's ranking page
TE.consent()
for path in ("/ranking/ranking.aspx?rid=157", f"/player-profile/{TE_ID}/ranking"):
    try:
        page = TE.fetch(path)
    except Exception as e:
        print("\n===== TE", path, "failed:", e); continue
    print(f"\n===== TE {path}: {len(page)} chars")
    print(flat(page)[:5000])
    print("links:", sorted(set(re.findall(r'href="([^"]*(?:rank|categ|week|id=)[^"]*)"', page, flags=re.I)))[:60])
    print("selects:", [re.sub(r"\s+", " ", s)[:1500] for s in re.findall(r"<select.*?</select>", page, flags=re.S | re.I)][:6])
    print("forms:", [re.sub(r"\s+", " ", s)[:400] for s in re.findall(r"<form[^>]*>", page, flags=re.I)][:6])
    print("data urls:", sorted(set(re.findall(r'(?:data-url|data-href|url:)\s*=?\s*["\']([^"\']+)', page)))[:30])
