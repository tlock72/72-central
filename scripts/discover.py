"""One-off check of ATP ranking sources for Scouting HQ (no API key used)."""
import re, urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def flat(s):
    return re.sub(r"\s+", " ", s)


def show(label, url, n=400, find=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            st, body = r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        st, body = e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        st, body = 0, repr(e)
    print(f"##### {label} -> HTTP {st}, {len(body)} chars | {flat(body[:n])}")
    if find:
        i = body.find(find)
        print(f"##### {label} at '{find}': {flat(body[max(i, 0):max(i, 0) + 700])}")


show("live-tennis.eu U21", "https://live-tennis.eu/en/atp-ranking-under-21", 200, "<tbody")
show("live-tennis.eu official", "https://live-tennis.eu/en/official-atp-ranking", 200, "<tbody")
show("tennisabstract ATP", "https://www.tennisabstract.com/reports/atpRankings.html", 300, "<tr")
show("tennisabstract WTA", "https://www.tennisabstract.com/reports/wtaRankings.html", 200)
show("sofascore ATP", "https://api.sofascore.com/api/v1/rankings/type/5", 500)
show("sackmann ATP current", "https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master/atp_rankings_current.csv", 60)
show("UTS", "https://www.ultimatetennisstatistics.com/rankingsTableTable?current=1&rowCount=5&sort%5Brank%5D=asc&rankType=RANK", 600)
show("ESPN ATP", "https://site.api.espn.com/apis/site/v2/sports/tennis/atp/rankings", 400)
show("ATP PDF", "https://www.atptour.com/-/media/files/rankings/singles.pdf", 120)
