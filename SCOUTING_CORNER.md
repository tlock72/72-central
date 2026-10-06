# Scouting Corner: setup and how it works

Scouting Corner is the 6th tile. It follows each prospect through every stage of their career and keeps it all
linked to one person: **Tennis Europe → ITF juniors → ITF pro tour / ATP / WTA**. Everything runs free on GitHub,
without Claude, and uses no Live Tennis API calls.

## Adding players
- **On the site:** anyone can type a name into the "Add a prospect" box. It's saved to the "Prospects" tab of the
  visit-log Google Sheet and looked up within about 30 minutes (a few minutes with step 3 below).
  To remove someone added there, delete their row on the "Prospects" tab.
- **In GitHub:** `prospects.json` is the hand-kept list. One line per player:
  `{"name": "Laurens Drijver", "g": "M", "nat": "NED", "born": 2010}`.
  Only the name is needed. `g` (M or F), `nat` (3-letter nation) and `born` make the linking safer.
  To remove someone, delete their line.

## How the stages are linked (never guessed)
- **ITF** is the anchor: one ITF player id covers a player's junior and pro career. It's found by exact full name
  (and nationality, when known).
- **Tennis Europe:** exact full name, and the nationality on their Tennis Europe profile must match.
- **ATP / WTA:** the official ranking the ITF shows for that player, matched to the weekly ATP/WTA list (which also
  gives the 1 week / 3 month / 12 month moves).
- If more than one player fits, nothing is linked. The card says **Check** and you get an alert on the
  "72 Central: missing info" issue. Fix it by adding the right id in `prospects.json`:
  `"itf": 800695508` (the number in their ITF profile link) or `"te": "C9E08DE0-..."` (the long code in their
  Tennis Europe profile link). An id typed there always wins.
- Stages not found yet are looked for again every week. So when a Tennis Europe player first plays ITF juniors, or a
  junior gets an ATP/WTA ranking, it's linked automatically.

## Setup (once, about 5 minutes)
1. **Update the Google Sheet script.** Open the visit-log Sheet, go to **Extensions > Apps Script**, replace
   everything with the new `scripts/visit_log.gs` from this repo and click **Save**.
2. **Make the tab and publish.** In the function dropdown pick `setupProspects` and click **Run** (Google asks for
   permission again, because the script can now start the GitHub update: **Advanced > Go to … > Allow**). Then
   **Deploy > Manage deployments > Edit (pencil) > Version: New version > Deploy**. The URL stays the same.
3. **Optional, for near-instant lookups:** in GitHub go to **Settings > Developer settings > Fine-grained tokens >
   Generate new token**. Pick only the `72-central` repository, and under permissions set **Actions: Read and write**.
   Copy the token. In Apps Script, go to **Project Settings (cog) > Script properties > Add property**, name it
   `GH_TOKEN` and paste the token. Without it, names are still picked up by the half-hourly run.

## Good to know
- Rankings shown: Tennis Europe (each age category), ITF junior, and ATP/WTA, with career best.
  The ATP/WTA moves come from the official weekly rankings. Tennis Europe and ITF junior moves are worked out from
  the history kept here, so they show "—" until that history goes back far enough (1 week, 3 months, 12 months
  after a player is added).
- Results from the last 12 months: Tennis Europe, ITF juniors, and pro matches from the ITF's records (which include
  ATP/WTA Tour events, Challengers, WTA 125s, ITF M/W15-M/W100 and Grand Slams, qualifying too).
- Everyone is refreshed once a day from 05:00 UK (new names straight away), one request every few seconds. If the
  ITF or Tennis Europe shows its bot check, that site is left alone for 3 hours and the previous data stays.
- Tennis Europe data is used with permission, for internal use only.
