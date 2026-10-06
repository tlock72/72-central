"""One-off: the new Tennis Europe list check must find Kurylova at last week's World TEC Cup (read-only)."""
import json, sys
sys.path.insert(0, "scripts")
import schedule as S

S.in_window = lambda start, end: True
TE = S.te_session()
ev = {"tour": "te", "src": "te", "name": "WORLD TEC CUP", "start": "2026-09-26", "end": "2026-10-04",
      "teId": "D7456117-0012-4B95-AC0A-04EC993CC621"}
failed = S.te_lists(TE, [ev], json.load(open("te.json"))["profiles"], {})
print("RESULT list:", ev.get("list"), "72:", ev.get("e72"), "failed:", failed)
