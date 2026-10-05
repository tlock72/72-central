# 72 Central: working notes for Claude

Read this first instead of re-reading every script. It is an internal site for SeventyTwo Sports Group, owned by Tobey (tlock72).
It is hosted on GitHub Pages at tlock72.github.io/72-central and protected by a passcode screen in `index.html`.

## Hard rules
- **Zero budget.** Everything runs free on GitHub Actions and cron-job.org. Never add paid services.
- **No Claude dependency.** All updates must run without Claude in case the subscription lapses.
- **Accuracy over completeness.** Bosses use the site, so never guess a score or ranking. Leave it blank and alert instead.
- **Live Tennis API free plan: 100 calls a day.** `update.py` caps each run at 45 (`MAX_CALLS`). A normal day uses about 45–50, and a busy Monday up to about 85. Runs started by hand always run (only timer runs skip if the site updated in the last 20 minutes), so they burn calls.
- **Tennis Europe data:** used with permission from Gregor Kusic (Tennis Europe), internal use only. Keep `robots.txt` blocking indexing.
- Tobey edits in the GitHub web editor, so keep changes small and explain them in plain English.

## Files
| File | What it is |
|---|---|
| `index.html` | The whole site in one file (home portal, Live Scores, 72 Rankings, Age Filtered World Rankings, players). It has its own `ROSTER` list (around line 551), and the passcode gate is near the end. |
| `data.json` | Matches and ATP/WTA rankings, written by `update.py`. Key fields: `matches[]`, `rankings{rid}`, `rankingsTourWeek{atp,wta}`, `rankingsWeek`, `rankingsNext` (holding area), `rankingsTry`, `quotaHit`, `lastChecked`. |
| `players.json` | Roster id → Live Tennis API id, written by `update.py`. |
| `titles.json` | ITF World Tennis Tour titles by year, one line per title with its date. `update.py` adds each final a roster player wins; titles the feed misses can be added by hand. The home "ITF titles" count reads this. |
| `itf.json` | ITF junior rankings, with players that couldn't be read listed under `pending`. |
| `itfm.json` | ITF junior matches. |
| `te.json` | Tennis Europe U14/U16 matches. |
| `scouting.json`, `scouting_history.json` | Age Filtered World Rankings (U21 ATP/WTA, with 1-week, 3-month and 12-month moves). |
| `*.webp` | Player photos, named by roster id. |
| `FILL_GAPS.md`, `ITF_JUNIORS.md` | Manual fallback instructions for Claude, used only when asked. |

Roster ids are short surnames (`deminaur`, `svitolina`, `mmakarova`…). **Adding a player** means updating `ROSTER` in `scripts/update.py` (name + tour) and `ROSTER` in `index.html`. For juniors, also update the lists in `itf_juniors.py` and `te_matches.py` (born 2010+), and add a photo.

## Scripts (`scripts/`)
- `update.py`: Live Tennis API. Runs a live check hourly (the :13 run), upcoming matches every 2 hours, and result lookups capped per run.
  - **Rankings** follow the official week: they only fetch when `scouting.json` shows a newer ATP/WTA week than `rankingsTourWeek`.
  - It first probes 3 top players. If their points are unchanged, the feed is lagging, so it retries in 2 hours (and from Wednesday accepts whatever the feed has).
  - It then publishes each tour all at once.
- `scouting.py`: free sources, no key. ATP comes from Tennis Abstract (`reports/atpRankings.html`, "Last update" date) and WTA from `api.wtatennis.com` (`rankedAt`). It checks hourly on Mondays and Tuesdays and every 3 hours otherwise. **It is also the "is a new ranking week out?" signal.**
- `itf_juniors.py`: ITF junior rankings, weekly. It stops immediately at the ITF bot check and never bypasses it.
- `itf_matches.py`: ITF junior draws and results, about twice a day.
- `te_matches.py`: Tennis Europe matches, once a day from 07:30 UK.
- `report_gaps.py`: alerting. It comments on the GitHub issue "72 Central: missing info" (GitHub emails Tobey) and reports each message once, so **never put times in alert text**. It also runs as the watchdog.

## Workflows (`.github/workflows/`)
- `update-scores.yml`: runs every 30 minutes (cron `13,43 6-22 * * *` UTC, plus cron-job.org dispatches with `source=timer`). It runs update.py, then ITF ranks if due, scouting, ITF matches, TE, save, and alert.
  - Checkout uses `ref: main`, because a run queued behind another must start from the newest data.
  - The save step does `pull --rebase -X theirs`, and on failure aborts and skips (the next run catches up).
- `itf-juniors.yml`: Mondays at 08:20, 11:20 and 14:20 UK.
- `watchdog.yml`: every 3 hours. Alerts if updates stop, runs keep failing, or Pages fails to build.
- `check-api.yml`: a one-off API shape check (`discover.py`).

## Gotchas already hit
- Commits made in the GitHub web editor can land while a run is mid-flight. That's handled by `ref: main` and the rebase fallback.
- Feed rankings lag official rankings by hours on Mondays, which is why rankings use the official-week check and probe.
- Mid-week of two-week events, the tours publish no new ranking. That's normal, and no calls are spent.
- `ubuntu-latest` moves to Ubuntu 26 from 19 Oct 2026. If something breaks after that, check Python/pip first.

## Testing without spending calls
Monkeypatch `update.api` with a fake that returns `{"data": ...}` and run `update.main()` on a copy of the repo. Never run with the real key just to test.
