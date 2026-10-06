"""One-off check (test branch only, removed before merging): the new ATP entry logic on today's real data. Writes nothing."""
import json, re, sys
sys.path.insert(0, "scripts")
import schedule as S

events = [dict(e, src="atp") for e in S.atp_wiki(f"{S.YEAR}_ATP_Tour", "atp")] + \
         [dict(e, src="challenger") for e in S.atp_wiki(f"{S.YEAR}_ATP_Challenger_Tour", "ch")]
events = [e for e in events if e["end"] >= S.FROM.isoformat()]
for e in events:
    e["tier"] = S.tier(e["tour"], e["cat"])
errors = {}
byev = S.atp_entries(events, errors)
print("errors:", errors)
for k, v in sorted(byev.items(), key=lambda x: x[0][2]):
    print("ENTRIES", k[2], k[1], [(p["id"], p["how"]) for p in v])
print("CHECKS:", S.CHECKS)
# Tick Tock list sizes for the big events (is the Paris list out yet?)
body = S.get(S.TT_URL)
for b in re.split(r"atpData\.\w+\s*=\s*\{\s*\"gs\"", body)[1:]:
    for t in re.split(r"\{\s*name:\s*", b.split("};", 1)[0])[1:]:
        tname = (re.match(r'"([^"]*)"', t) or [None, ""])[1]
        if not re.search(r"\(CH|^M\d", tname):
            print("TT", tname, {part: len(re.findall(r"\[([^\[\]]*)\]", arr)) for part, arr in re.findall(r"(\w+):\s*(\[\[.*?\]\]|\[\])", t)})
# carried entries + ESPN draw for events that have started
prev = json.load(open("schedule.json"))
prev_e72 = {(e.get("src"), e.get("name"), e.get("start")): e.get("e72") for e in prev["events"] if e.get("e72")}
for e in events:
    if S.in_window(e["start"], e["end"]) and e["tour"] in ("atp", "ch"):
        e["e72"] = byev.get(S.ev_key(e), [])
        if not e["e72"] and e["start"] <= S.T.isoformat():
            e["e72"] = [dict(p, carried=True) for p in prev_e72.get(S.ev_key(e)) or []]
            if e["e72"]:
                print("CARRIED", e["name"], e["e72"])
S.espn_draws(events)
for e in events:
    if e.get("e72") and e["start"] <= S.T.isoformat():
        print("AFTER ESPN", e["name"], e["e72"])
