# iPhone notifications for 72 results

Every time the scores update (about every 30 minutes, 07:00–23:45 UK), each newly finished match with a
72 player is sent to your phone as a notification, for example:

> ✅ Daniel Altmaier d. H. Rune
> 1-6, 7-6(5), 6-4 · Shanghai · ATP 1000 · 1R

Covers ATP/WTA, Challengers, ITF, ITF juniors and Tennis Europe. Tapping it opens 72 Central.
It uses the free **ntfy** app: no account, no cost, and no Claude. `scripts/notify.py` does the sending
and `notified.json` remembers what has already been sent.

## Setup (once, about 5 minutes)

1. **Pick a secret topic name.** It works like a password: anyone who knows it can read the alerts,
   so make it long and random, e.g. `seventytwo-results-8k3vq9x2mt` (letters, numbers, `-` and `_` only).
2. **Add it to GitHub:** repo **Settings → Secrets and variables → Actions → New repository secret**.
   Name: `NTFY_TOPIC`. Value: your topic name.
3. **On each iPhone:** install **ntfy** from the App Store, open it, tap **+**, type the same topic name,
   tap **Subscribe**, and allow notifications when asked.

The first run after step 2 only remembers the results already on the site (so you don't get a flood);
alerts start from the next finished match.

## Good to know
- Results arrive up to about 30 minutes after the match ends (when the next update runs).
- If more than 5 results finish at once, they come as one combined alert.
- To add a boss, just give them the topic name (step 3). To stop everyone, delete the secret.
  To change who can read them, change the topic name in step 2 and re-subscribe.
- Messages pass through ntfy.sh's servers (only the player names, score and event).
