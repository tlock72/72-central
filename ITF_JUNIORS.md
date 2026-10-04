# Filling in ITF junior rankings

The weekly script `scripts/itf_juniors.py` reads each 72 junior's ITF World Tennis Junior
Ranking. Sometimes the ITF website shows a bot check instead of data, and the players it
could not read are listed in `itf.json` under `"pending"`.

Your job: fill in the ranking for every player id listed in `"pending"`, then empty that list.

For each pending player (look up their `itfId` in `itf.json`; the names are in
`scripts/itf_juniors.py` under `JUNIORS`):

1. Use WebFetch on
   `https://www.itftennis.com/tennis/api/PlayerApi/GetPlayerOverview?circuitCode=JT&matchTypeCode=S&playerId=<itfId>`.
   Read `rankings` ("World Tennis Junior Ranking": `rank`, `date`) and `careerHighRankings`
   (`rank`, `date`). Fetch ONE player at a time and run `sleep 10` between fetches.
   If the player has no `itfId`, WebFetch
   `https://www.itftennis.com/tennis/api/PlayerApi/GetPlayerSearch?searchString=<name>`
   and pick the exact name match; store it as `itfId`.
2. If a fetch shows a bot/security page, wait (`sleep 30`) and try once more. Never try
   to get around the check. If it still fails, use WebSearch for the player's current ITF
   junior ranking and only use a figure that a page clearly states for this week.
3. Update that player's entry in `itf.json`:
   `rank`, `rankDate` (e.g. "28 September 2026"), `high`, `highDate`, `updated` (today, YYYY-MM-DD),
   and `move` = previous `rank` minus new `rank` (null if either is missing or the date did not change).
   A player with no junior ranking gets `"rank": null`.
   If the ITF search finds no profile for the player at all (common for under-12s), set
   `"noItf": true` and `"rank": null` for them; the script then stops looking until the
   first Monday of next month.
4. Remove the player from `"pending"`. Leave any player you truly cannot confirm in `"pending"`
   and keep their old figures; never guess a number.

Only edit `itf.json`. Make sure it stays valid JSON (`python3 -c "import json;json.load(open('itf.json'))"`).
