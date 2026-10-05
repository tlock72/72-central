"""Temporary: show the ATP Tour page's October-December rows (deleted after use)."""
import json, re, sys, urllib.parse
sys.path.insert(0, "scripts")
import schedule as S
w = json.loads(S.get(S.WIKI + "?" + urllib.parse.urlencode({"action": "parse", "page": "2026_ATP_Tour", "prop": "wikitext", "format": "json", "formatversion": 2})))["parse"]["wikitext"]
i = w.find("October"); i = w.find("===October"); j = w.find("==Statistical")
seg = w[i:j if j > i else i + 40000]
for l in seg.split("\n"):
    if l.startswith("|") and not l.startswith(("|-", "|}")) and ("<br" in l or re.match(r"^\|\s*(rowspan=\S+\|)?\s*\d{1,2} [A-Z][a-z]{2}", l)):
        print(l[:260])
    elif l.startswith("==="):
        print(l)
