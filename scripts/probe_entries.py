"""One-off: what Spazio and Tick Tock say for Shanghai."""
import sys, json, re, html
sys.path.insert(0, "scripts")
import schedule as S
S.PAUSE["other"] = 0
posts = json.loads(S.get(S.SP_API + "/posts?search=shanghai&per_page=10&_fields=id,date,modified,link,title,content"))
for p in posts:
    c = p["content"]["rendered"]
    print("\n###", p["date"], p["modified"], p["title"]["rendered"], p["link"], len(c))
    for n in ["Minaur", "Rublev", "Buse", "Altmaier", "ENTRY LIST", "ALTERNATE"]:
        for m in list(re.finditer(n, c))[:2]:
            print(f"  [{n}]", repr(c[max(0, m.start() - 150): m.start() + 120]))
events = json.load(open("schedule.json"))["events"]
men = {S.pkey(n): rid for rid, (n, t) in S.ROSTER.items() if t == "atp"}
lt, everyone, first = S.lt_entries(events, men, 15)
tt = S.tt_entries(events, men, 15, everyone)
sp = S.sp_entries(events, men, everyone)
print("TT shanghai:", {k[0]: v for k, v in tt.items() if "Shanghai" in k[1][1]})
print("SP shanghai:", {k[0]: v for k, v in sp.items() if "Shanghai" in k[1][1]})
print("everyone shanghai size:", {k[1]: len(v) for k, v in everyone.items() if "Shanghai" in k[1]})
