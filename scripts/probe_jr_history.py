"""One-off check (safe to delete): the exact ITF draw request, one 2024 junior draw, and one official points
breakdown. 3-4 ITF requests; stops at the bot check."""
import json, subprocess, time, urllib.parse, urllib.request

UA = "72HubRankings/1.0 (+https://github.com/tlock72/72-central; one-off check)"
ITF = "https://www.itftennis.com/tennis/api"
d = "/tmp/new"; subprocess.run(["git", "clone", "-q", "--depth", "1", "https://github.com/genaromoraes/itf-juniors-live-ranking.git", d], check=True)
sh = lambda c: subprocess.run(["bash", "-c", c], capture_output=True, text=True).stdout
print("===== drawsheet request in 05_fetch_week_results.mjs\n" + sh(f"grep -n -A40 'async function fetchDrawsheet\\|function buildDrawsheet\\|DRAWSHEET_URL' {d}/scripts/05_fetch_week_results.mjs | head -160"))
print("===== GetRankingPoints params\n" + sh(f"grep -n -B12 'GetRankingPoints' {d}/scripts/lib/player_breakdown.mjs | head -30"))
print("===== drawsheet parsing (rounds/koGroups)\n" + sh(f"grep -n 'koGroups\\|rounds\\|roundNumber\\|matches\\|teams\\|players\\|winningSide\\|resultStatusCode\\|isBye\\|bye' {d}/scripts/05_fetch_week_results.mjs | head -60"))
