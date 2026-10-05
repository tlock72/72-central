"""One-off: run the ATP / Challenger entries step against the real sites (reads only, saves nothing)."""
import sys, json
sys.path.insert(0, "scripts")
import schedule as S
events = json.load(open("schedule.json"))["events"]
S.PAUSE["other"] = 0
errs = {}
for k, v in sorted(S.atp_entries(events, errs).items(), key=lambda kv: kv[0][2]):
    print("SHOWN:", k[2], k[1], v)
print("ERRORS:", errs)
posts = json.loads(S.get(S.SP_API + "/posts?search=shanghai%20entry&per_page=10&_fields=id,date,link,title,categories,content"))
import re
for p in posts:
    c = p["content"]["rendered"]
    print("POST", p["date"], p["categories"], p["title"]["rendered"], p["link"], [re.sub(r"<[^>]+>", "", h)[:80] for h in re.findall(r"<h[23][^>]*>(.*?)</h[23]>", c, re.S)][:6])
