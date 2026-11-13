"""One-off check (safe to delete): are there dated copies of the ITF junior ranking for 2023-2026 (monthly or
quarterly would do)? Looks in the Wayback Machine's index for (1) saved answers of the ITF's own ranking feed,
(2) ITF junior ranking PDFs on itftennis.com/media, (3) saved CoreTennis junior ranking pages. Read-only."""
import json, re, time, urllib.parse, urllib.request, collections

UA = "72HubRankings/1.0 (+https://github.com/tlock72/72-central; one-off check)"


def cdx(**q):
    time.sleep(4)
    q.setdefault("output", "json")
    url = "https://web.archive.org/cdx/search/cdx?" + urllib.parse.urlencode(q, doseq=True)
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120) as r:
                rows = json.loads(r.read().decode() or "[]")
            return rows[1:] if rows else []
        except Exception as e:
            print("  cdx retry", e); time.sleep(10)
    return []


# 1) the ITF ranking feed itself (juniors): which dates, and how deep (take/skip)
rows = cdx(url="itftennis.com/tennis/api/PlayerRankApi/GetPlayerRankings", matchType="prefix", **{"from": "2023"},
           fl="timestamp,original,statuscode,length", filter="statuscode:200", limit="20000")
jt = [r for r in rows if "circuitCode=JT" in r[1]]
print(f"== ITF feed: {len(rows)} saved answers, {len(jt)} junior")
by = collections.defaultdict(list)
for ts, orig, st, ln in jt:
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(orig).query))
    kind = (q.get("juniorRankingType", "?").strip(), q.get("playerTypeCode", "?").strip(), "zone" if q.get("zoneCode") or q.get("nationCode") else "world")
    by[kind].append((ts[:8], q.get("take"), q.get("skip"), ln))
for kind, v in sorted(by.items()):
    print(kind, len(v), "deep pages (skip>=100):", sum(1 for x in v if (x[2] or "0").isdigit() and int(x[2]) >= 100))
    months = collections.Counter(x[0][:6] for x in v)
    print("   by month:", dict(sorted(months.items())))
    print("   samples:", sorted(v)[:6], sorted(v)[-4:])

# 2) ITF junior ranking PDFs on itftennis.com/media
rows = cdx(url="itftennis.com/media/", matchType="prefix", **{"from": "2022"}, fl="timestamp,original", filter=["statuscode:200", "mimetype:application/pdf"],
           collapse="urlkey", limit="50000")
pdf = sorted({r[1].split("?")[0].lower() for r in rows if re.search(r"rank", r[1], re.I) and re.search(r"boy|girl|junior|jr|wttj", r[1], re.I)})
pdf = [u for u in pdf if not re.search(r"beach|wheelchair|senior|masters-tour|padel", u)]
print(f"\n== ITF media PDFs: {len(rows)} PDFs saved, {len(pdf)} look like junior rankings")
for u in pdf:
    print("  ", u)

# 3) CoreTennis junior ranking pages
for pat in ("coretennis.net/majic/pageServer/", "www.coretennis.net/majic/pageServer/"):
    rows = cdx(url=pat, matchType="prefix", **{"from": "2023"}, fl="timestamp,original", filter="statuscode:200", limit="50000")
    jr = [r for r in rows if re.search(r"ITF-Junior-(Boys|Girls)-Rankings", r[1])]
    print(f"\n== {pat}: {len(rows)} saved pages, {len(jr)} junior ranking pages")
    print("   by month:", dict(sorted(collections.Counter(r[0][:6] for r in jr).items())))
