"""One-off: print what Tennis Europe and the ITF hold for a new signing (run by hand from check-api.yml).
Reads only; writes nothing to the repo."""
import json, re, sys
import te_matches as TE
import prospects as P

NAME = "Arina Guslinskaia"
names = [NAME, "Arina Guslinskaya"]

try:
    st, pid, nat, circ, note, iname = P.itf_find({"name": NAME, "names": names, "g": "F"})
    print("ITF:", st, pid, nat, circ, note, iname)
    if pid:
        print("ITF born:", P.itf_born(pid, ["JT"]))
except Exception as e:
    print("ITF failed:", e)

TE.consent()
hits = {}
for n in names:
    page = TE.fetch("/find/player?q=" + n.replace(" ", "+"))
    for g, nm in re.findall(r'player-profile/([0-9A-Fa-f-]{36})"[^>]*>\s*<span class="nav-link__value">([^<]+)', page):
        hits[g.upper()] = nm.strip()
print("TE search:", hits)
for pid, nm in hits.items():
    if not P.same_name(nm, NAME) and not P.same_name(nm, names[1]):
        continue
    prof = TE.fetch(f"/player-profile/{pid}")
    print("\n== TE profile", pid, nm, "flag:", P.te_nat(prof), "born:", P.te_born(pid))
    ranks, links = TE.ranking(pid)
    print("ranking:", json.dumps(ranks))
    for year in (2026, 2025, 2024, 2023):
        page = TE.fetch(f"/player-profile/{pid}/tournaments" + ("" if year == 2026 else f"/{year}"))
        tours = re.findall(r'class="media__title[^"]*"[^>]*>\s*<a[^>]*title="([^"]+)"', page)
        print(f"\n-- {year} tournaments ({len(tours)}):", " | ".join(tours))
        for m in sorted(TE.parse(page, "me", NAME + "|" + names[1]), key=lambda m: m["date"]):
            won = m["p1Id"] == "me"
            print(" ", m["date"], m["tournament"], "|", m["category"], "|", m["round"], "|",
                  ("W" if won else "L") if m["status"] == "finished" else "sched",
                  "v", m["p2"] if won else m["p1"], m["score"])
