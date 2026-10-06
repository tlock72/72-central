"""One-off: run the new Tennis Europe entry list check (read-only, prints to the log, saves nothing)."""
import json, sys, time
sys.path.insert(0, "scripts")
import schedule as S

t0 = time.time()
TE = S.te_session()
evs = S.te_events(TE)
win = [e for e in evs if S.in_window(e["start"], e["end"])]
print(len(evs), "Tennis Europe events,", len(win), "in the entry window")
failed = S.te_lists(TE, evs, json.load(open("te.json"))["profiles"], {})
for e in sorted(win, key=lambda e: e["start"]):
    print(e["start"], e["name"], e.get("ages"), "list:", e.get("list"), "72:", e.get("e72"))
print("failed:", failed, "minutes:", round((time.time() - t0) / 60, 1))
