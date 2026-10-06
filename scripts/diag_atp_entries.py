"""One-off check (test branch only, removed before merging): what live-tennis.eu, Tick Tock Tennis and Spazio Tennis
publish for the next few weeks, and why Shanghai / Paris 72 entries were missed. No Live Tennis API calls."""
import json, re, html, sys
from datetime import timedelta
sys.path.insert(0, "scripts")
import schedule as S

events = [dict(e, src="atp") for e in S.atp_wiki(f"{S.YEAR}_ATP_Tour", "atp")] + \
         [dict(e, src="challenger") for e in S.atp_wiki(f"{S.YEAR}_ATP_Challenger_Tour", "ch")]
print("FROM", S.FROM, "T", S.T)
for e in events:
    if e["tour"] == "atp" and S.FROM.isoformat() <= e["start"] <= (S.FROM + timedelta(weeks=6)).isoformat():
        print("CAL", e["start"], e["end"], e["cat"], "|", e["name"], "|", e["place"])
men = {S.pkey(n): rid for rid, (n, t) in S.ROSTER.items() if t == "atp"}
TOP = ("deminaur", "rublev", "buse", "altmaier", "monfils")

print("\n==== live-tennis.eu ====")
try:
    body = S.get(S.LT_URL)
    hdr = re.findall(r"(?s)<th[^>]*>(.*?)</th>", body)
    print("headers:", [html.unescape(re.sub(r"<[^>]+>", " ", h)).split() for h in hdr][:15])
    rows = re.findall(r"(?s)<tr[^>]*>\s*<td class=\"?rk\"?>.*?</tr>", body)
    print("rows", len(rows))
    for r in rows:
        nm = re.search(r"<td class=\"?pn\"?>(.*?)</td>", r)
        n = html.unescape(re.sub(r"<[^>]+>", "", nm.group(1))) if nm else ""
        if men.get(S.pkey(n)) in TOP:
            print("LT row", n, "::", re.sub(r"\s+", " ", r.split("</td>", 5)[-1])[:700])
    out, ev, off = S.lt_entries(events, men, 15)
    print("LT offset", off, "72:", {(k[0], k[1][1]): v for k, v in out.items()})
except Exception as x:
    print("LT failed", repr(x))

print("\n==== Tick Tock ====")
try:
    body = S.get(S.TT_URL)
    print("updated:", re.findall(r"Data updated[^<]{0,40}", body)[:2])
    heads = re.findall(r"atpData\.(\w+)\s*=", body)
    print("blocks:", heads)
    blocks = re.split(r"atpData\.\w+\s*=\s*\{\s*\"gs\"", body)[1:]
    for i, b in enumerate(blocks):
        names = re.findall(r"\{\s*name:\s*\"([^\"]*)\"", b.split("};", 1)[0])
        print("TT block", i, heads[i] if i < len(heads) else "?", names)
        for t in re.split(r"\{\s*name:\s*", b.split("};", 1)[0])[1:]:
            tname = (re.match(r'"([^"]*)"', t) or [None, ""])[1]
            if re.search(r"shanghai|paris|basel|vienna|almaty|stockholm|brussels|european|lyon|grand prix", tname, re.I):
                hit = [(men[S.pkey(json.loads("[" + p + "]")[1])], part) for part, arr in re.findall(r"(\w+):\s*(\[\[.*?\]\]|\[\])", t)
                       for p in re.findall(r"\[([^\[\]]*)\]", arr) if p.count('"') >= 2 and S.pkey((re.findall(r'"([^"]*)"', p) or [""])[0]) in men]
                print("   ", tname, "parts:", sorted({part for part, _ in re.findall(r"(\w+):\s*(\[\[.*?\]\]|\[\])", t)}), "72:", hit)
    everyone = {}
    print("TT 72:", {(k[0], k[1][1]): v for k, v in S.tt_entries(events, men, 15, everyone).items()})
except Exception as x:
    print("TT failed", repr(x))

print("\n==== Spazio ====")
try:
    cat = json.loads(S.get(f"{S.SP_API}/categories?slug=ent&_fields=id"))
    after = (S.FROM - timedelta(days=42)).isoformat() + "T00:00:00"
    posts = json.loads(S.get(f"{S.SP_API}/posts?categories={cat[0]['id']}&per_page=100&after={after}&_fields=id,date,title,content"))
    print("posts", len(posts))
    for post in posts:
        body = (post.get("content") or {}).get("rendered") or ""
        heads = [html.unescape(re.sub(r"<[^>]+>", " ", h)).strip() for h in re.findall(r"(?s)<h[23][^>]*>(.*?)</h[23]>", body)]
        print("SP post", post.get("date"), "|", html.unescape((post.get("title") or {}).get("rendered") or "")[:90], "| heads:", heads[:8])
        for k in men:
            last = k.split()
            if all(w in S.pkey(html.unescape(re.sub(r"<[^>]+>", " ", body))) for w in last) and men[k] in TOP:
                print("    mentions", men[k])
    ev2 = {}
    try:
        _, ev2, _ = S.lt_entries(events, men, 15)
    except Exception:
        pass
    S.tt_entries(events, men, 15, ev2)
    print("SP 72:", {(k[0], k[1][1]): v for k, v in S.sp_entries(events, men, ev2).items()})
except Exception as x:
    print("SP failed", repr(x))
