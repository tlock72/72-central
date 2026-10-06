"""One-off: why de Minaur / Rublev / Buse aren't on Shanghai."""
import sys, json, re
sys.path.insert(0, "scripts")
import schedule as S
S.PAUSE["other"] = 0
body = S.get(S.TT_URL)
print(re.search(r"Data updated[^<]{0,40}", body).group(0))
i = body.find('name: "Shanghai')
print("TT SHANGHAI BLOCK:", body[i:i + 700])
events = json.load(open("schedule.json"))["events"]
men = {S.pkey(n): rid for rid, (n, t) in S.ROSTER.items() if t == "atp"}
lt, everyone, first = S.lt_entries(events, men, 15)
tt = S.tt_entries(events, men, 15, everyone)
sp = S.sp_entries(events, men, everyone)
print("TT:", {k[0]: v for k, v in tt.items() if "Shanghai" in k[1][1]})
print("SP:", {k[0]: v for k, v in sp.items() if "Shanghai" in k[1][1]})
for u in ["https://www.protennislive.com/posting/2026/5014/mds.pdf"]:
    try:
        b = urllib_req = __import__("urllib.request").request.urlopen(__import__("urllib.request").request.Request(u, headers={"User-Agent": S.UA}), timeout=30).read()
        print("PDF", u, len(b))
    except Exception as e:
        print("PDF failed", e)
import shutil; print("pdftotext:", shutil.which("pdftotext"))
