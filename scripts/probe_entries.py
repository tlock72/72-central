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
