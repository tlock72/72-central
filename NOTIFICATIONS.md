# Result alerts (notifications for 72 results)

Every time the scores update (about every 30 minutes, 07:00–23:45 UK), each newly finished match with a
72 player is sent as a notification, for example:

> ✅ Daniel Altmaier d. H. Rune
> 1-6, 7-6(5), 6-4 · Shanghai · ATP 1000 · 1R

Covers ATP/WTA, Challengers, ITF, ITF juniors and Tennis Europe. Tapping it opens 72 Central.
**No app to download**: it comes from the site itself (iPhone needs iOS 16.4 or newer). Free, no Claude.

How it fits together: a device presses **Turn on result alerts** in Settings → its sign-up goes on the
"Alerts" tab of the visit-log Sheet → GitHub (`scripts/notify.py`) sends each new result to everyone on
that tab → the site's `sw.js` shows it. `notified.json` remembers what has been sent.

## One-time setup (Tobey, about 10 minutes)

You need two secret values (Claude made them for you; or ask Claude to make new ones):
`VAPID_PRIVATE` (the site's private key: it pairs with `ALERT_KEY` in `index.html`) and `ALERTS_KEY`.

1. **GitHub:** repo **Settings → Secrets and variables → Actions → New repository secret**. Add both:
   name `VAPID_PRIVATE` with its value, and name `ALERTS_KEY` with its value.
2. **Google Sheet script:** open the visit-log Sheet → **Extensions → Apps Script**. Replace the code
   with the new `scripts/visit_log.gs` and save.
   Then **Project Settings (cog) → Script properties → Add script property**: `ALERTS_KEY` with the
   **same** value as in step 1. Save.
   Then **Deploy → Manage deployments → Edit (pencil) → Version: New version → Deploy**
   (keeps the same web address, so nothing else changes).

## Turning alerts on (each person, each phone)

**iPhone/iPad:**
1. Open the site in **Safari**, tap the **Share** button, then **Add to Home Screen**.
2. Open **72 Central from the Home Screen** (not Safari), enter the passcode.
3. Tap the **cog** (top corner) → **Turn on result alerts** → **Allow**.

**Android / computer (Chrome, Edge, Firefox):** cog → **Turn on result alerts** → **Allow**.

To stop: cog → **Turn off result alerts**, or delete that person's row on the Sheet's "Alerts" tab.

## Good to know
- Results arrive up to about 30 minutes after the match ends (when the next update runs).
- If more than 5 results finish at once, they come as one combined alert.
- The first run after setup only remembers results already on the site, so nobody gets a flood.
- If a phone deletes the Home Screen icon or turns notifications off, its row is removed automatically.
- Optional extra: the free ntfy app also works (add a secret `NTFY_TOPIC` with a long random name and
  subscribe to it in the app). Not needed for the above.
