# Fill missing results

`data.json` holds the 72 Hub match list. A free feed fills it every 30 minutes but misses some
results. Your job: find the missing results and fix them in `data.json`. Be quick (a few web searches per match).

1. Read `data.json`. Work on matches where:
   - `status` is `"scheduled"` and the match started more than 3 hours ago (`date` + `time` are UK time), or the date is in the past; or
   - `status` is `"finished"` and `score` is empty.
2. For each, WebSearch the result (e.g. "Dotsenko Biolay Monastir result"), using tournament sites, ITF, ATP, WTA,
   tennis.com, flashscore. Confirm the score in two places when you can. Never guess.
3. If you find it: set `status` to `"finished"`, put the **winner as p1** (swap p1/p2 and p1Id/p2Id if needed),
   `winner` to `1`, and `score` from the winner's view like `"6-4, 3-6, 7-6(5)"`. Retirement: add `" ret."`
   after the score. Walkover: `score` `""`, add ` (walkover)` to `round`, and a short `note`.
   If the match was postponed, update `date`/`time` instead.
4. If you can't find it, leave the match as it is.
5. Keep everything else in `data.json` exactly as it is, and keep it valid JSON (one line is fine).
