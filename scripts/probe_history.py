"""One-off check of the Tennis Europe fix and past-week fill-in in prospects.py (reads only, saves nothing)."""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import te_matches as TE
import prospects as P

TE.consent()
for name, tid in (("Giulia Luchetti", "2F65EB7D-F034-4088-A2F5-86292F475429"), ("Srishti Kiran", "3AA20B4E-0678-45E7-9F2A-985D2787BF3E")):
    ranks, links = P.te_ranking(tid)
    print(f"\n===== {name}\nnow:", ranks)
    H = {}
    for r in ranks:
        P.remember(H.setdefault("te:" + r["cat"], {}), r["week"], r["rank"])
    P.te_backfill(H, ranks, links, name)
    print("history:", json.dumps(H))
    for r in ranks:
        print("moves", r["cat"], P.moves(H.get("te:" + r["cat"]) or {}, r["week"]))
