"""Temporary probe 5 (deleted after use)."""
import re, sys, urllib.parse, urllib.request
sys.path.insert(0, "scripts")
import te_matches as T
T.consent()
h = T.fetch("/find/tournament")
for nm in ("TournamentExtendedFilter.GradingID", "TournamentExtendedFilter.AgeGroupID", "TournamentExtendedFilter.SportID", "TournamentFilter.DateFilterType"):
    i = h.find(f'name="{nm}"'); seg = h[max(0, i-300): i+3000]
    print("\nFIELD", nm, re.findall(r'<option[^>]*value="([^"]*)"[^>]*>([^<]*)<', seg)[:30] or re.sub(r"\s+", " ", seg)[:600])
def post(page):
    data = urllib.parse.urlencode({"Page": page, "TournamentFilter.StartDate": "2026-10-05", "TournamentFilter.EndDate": "2026-12-31",
                                   "TournamentFilter.DateFilterType": "0", "TournamentFilter.Q": "", "LoadMoreResults": "true" if page > 1 else "false"}).encode()
    req = urllib.request.Request(T.SITE + "/find/tournament/DoSearch", data=data, headers={"User-Agent": T.UA, "X-Requested-With": "XMLHttpRequest",
                                 "Content-Type": "application/x-www-form-urlencoded"})
    with T.opener.open(req, timeout=40) as r:
        return r.status, r.read().decode("utf-8", "replace")
for pg in (1, 2):
    st, b = post(pg); items = re.findall(r'<li class="list__item">(.*?)</li>\s*(?=<li class="list__item">|$)', b, re.S)
    print("\nPOST page", pg, st, len(b), "items~", b.count("media__title"))
    txt = re.sub(r"\s+", " ", re.sub(r"<(?!time)[^>]+>", " ", b))
    print(txt[:2500])
    print("HREFS", re.findall(r'href="(/sport/tournament\?id=[^"]+)"', b)[:5])
