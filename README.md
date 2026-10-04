# 72 Central

SeventyTwo Sports Group's tennis hub: live scores, schedule, results and ATP/WTA rankings for the 72 roster.

- **Site:** `index.html` (GitHub Pages). It reads `data.json` and refreshes itself every minute.
- **Updates:** the "Update scores" GitHub Action runs `scripts/update.py` every 30 minutes (07:00–23:30 UK). It uses the free Live Tennis API plan (key in the repository secret `LIVETENNIS_API_KEY`). No Claude usage, no computer needed.
- **Run an update by hand:** Actions tab → Update scores → Run workflow.
- **Add or remove a player:** edit `ROSTER` in `scripts/update.py` and the `ROSTER` list in `index.html`.
- **If the key stops working:** get a new free key at livetennisapi.com and replace the `LIVETENNIS_API_KEY` secret (Settings → Secrets and variables → Actions).
