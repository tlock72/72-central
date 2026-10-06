# Visit log: setup (about 5 minutes, done once)

The site can record each visit (name, date, start time, minutes on screen, phone or computer, and pages viewed)
in a Google Sheet that only you can see. It's free and runs without Claude. Until step 5 is done, nothing is sent.

1. **Make the Sheet.** Create a new Google Sheet (e.g. "72 Central visits").
2. **Add the script.** In the Sheet, go to **Extensions > Apps Script**. Delete what's in the editor, paste in all of
   `scripts/visit_log.gs` from this repo, and click **Save** (the disk icon).
3. **Set up the tabs.** In the function dropdown at the top, pick `setup` and click **Run**. Google asks for permission:
   choose your account, then **Advanced > Go to (project name) > Allow**. (The warning appears because you wrote the
   script yourself rather than Google checking it.) Your Sheet now has a **Visits** tab and a **By person** tab.
4. **Publish it.** Click **Deploy > New deployment**, click the cog next to "Select type", and pick **Web app**. Set
   **Execute as: Me** and **Who has access: Anyone**, then click **Deploy**. Copy the **Web app URL** (it ends in `/exec`).
5. **Connect the site.** In GitHub, open `index.html`, search for `const LOG_URL = "";`, paste the URL between the
   quotes (e.g. `const LOG_URL = "https://script.google.com/macros/s/.../exec";`) and commit.

Open the site, wait a minute and the first row appears.

## Good to know
- **Visits:** one row per visit, updated about once a minute. Only time with the site on screen counts. If someone
  leaves the tab for over 30 minutes and comes back, that's a new visit.
- **By person:** total visits and minutes for each name, for the last 7 days and for all time.
- Names are what people type on the passcode screen, so they aren't checked. The passcode screen tells people
  that visits are logged.
- Anyone who reads `index.html` can see the URL. The worst they can do with it is add fake rows. If that happens, do
  **Deploy > Manage deployments**, archive the old one, make a new one and update `LOG_URL`.
- If you change the script later, use **Deploy > Manage deployments > Edit > Version: New version**, which keeps the
  same URL.
