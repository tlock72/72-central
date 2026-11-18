// 72 Central visit log. Not run by GitHub: paste this into your Google Sheet
// (Extensions > Apps Script) and follow VISIT_LOG.md.
// The site sends each visit here; each visit is one row on the "Visits" tab,
// updated about once a minute while the person has the site on screen.
// Scouting Corner's "Add a prospect" box also sends names here (the "Prospects" tab); GitHub reads
// that list (doGet, ?kind=prospects) and links each name to Tennis Europe, the ITF and the ATP/WTA.
// To remove a prospect added on the site, delete their row on the "Prospects" tab.
// Each Scouting Corner card also has a "Request removal" button: the request goes on the "Removals" tab and
// Tobey gets an email with a link to approve or decline it. Approved = taken off the Scouting Corner
// (their row on the "Prospects" tab is deleted, and GitHub stops showing anyone from prospects.json too).
// Whoever asked can undo their request from the same device while it's still waiting ("Withdrawn").
// Comments on players (Scouting Corner cards and Filtered Rankings rows) go on the "Comments" tab (made
// automatically with the first comment). The writer can undo one from the same device for an hour ("Undone");
// anyone can ask for one to be deleted, and Tobey gets an email to approve ("Deleted") or decline ("Kept").
// To delete a comment straight away yourself, set its Status to "Deleted".
// Filtered Rankings' "12 months" button asks GitHub for a player's last 12 months of results: each request is a row
// on the "Lookups" tab (made automatically), GitHub reads the last 3 days of them (?kind=lookups) and, if GH_TOKEN
// is set, is started straight away. Rows older than 3 days can be deleted at any time.
// Scouting Corner traffic lights (green / amber / red on each watch list prospect): every change is a row on the
// "Lights" tab (made automatically), and the newest row for a player is the light shown. "Cleared" = no light.
// To change one by hand, add a row (or edit the newest one) with Green, Amber, Red or Cleared in the Light column.
// Scouting reports (Scouting Corner's "Add scouting report" form): every save is a row on the "Reports" tab (made
// automatically), so the history of each report is kept; the site shows the newest "Live" row for each Report ID.
// "Draft" rows are unfinished reports, shown only to the person who started them (same first name or same device),
// who is also the only one who can edit the report. To delete a report, set the Status of its newest row to "Deleted".
// Comments on reports go on the "Report comments" tab (set Status to "Deleted" to take one down).
// Event recaps (Scouting reports "By event"): one write-up per event; every save is a row on the "Event recaps" tab
// (made automatically) and the newest row for an event is the one shown. Set its Status to "Deleted" to take it down.
// Scouting videos: the clips go into a Google Drive folder, "72 Central scouting videos" (made automatically, one
// folder per player), and each is a row on the "Videos" tab. Anyone with the link can watch a clip (the links are
// only on the passcode-protected site). To take a clip down, set its Status to "Removed" (and delete the file in
// Drive if you like). The person who added it can also remove it from the same device for a day.
// Video links (YouTube, Instagram, TikTok, Vimeo or any other page) pasted on the site go on the same tab: their
// File ID starts with "L", the link is in the Link column and Sharing says "Link". Take one down the same way.
// The person who added a video can edit its description (Caption) from the site.
// The videos need Google Drive access: after pasting this script, run setupReports once by hand and allow it.

const TZ = "Europe/London";

// Run once by hand: creates the "Visits" and "By person" tabs.
function setup() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  ss.setSpreadsheetTimeZone(TZ);
  const v = ss.getSheetByName("Visits") || ss.insertSheet("Visits", 0);
  v.getRange(1, 1, 1, 7).setValues([["Date", "Started", "Name", "Minutes", "Device", "Pages", "Visit ID"]]).setFontWeight("bold");
  v.setFrozenRows(1);
  v.getRange("A:A").setNumberFormat("ddd d mmm yyyy");
  v.getRange("B:B").setNumberFormat("HH:mm");
  v.getRange("D:D").setNumberFormat("0.0");
  v.hideColumns(7);
  const s = ss.getSheetByName("By person") || ss.insertSheet("By person");
  s.clear();
  const q = where => `=IFERROR(QUERY(Visits!A2:F, "select C, count(C), sum(D) where C is not null${where} group by C order by sum(D) desc label C 'Name', count(C) 'Visits', sum(D) 'Minutes'", 0), "No visits yet")`;
  s.getRange("A1").setValue("Last 7 days").setFontWeight("bold");
  s.getRange("A2").setFormula(q(` and A >= date '"&TEXT(TODAY()-6,"yyyy-mm-dd")&"'`));
  s.getRange("E1").setValue("All time").setFontWeight("bold");
  s.getRange("E2").setFormula(q(""));
  setupProspects();
}

// Run once by hand (setup() runs it too): creates the "Prospects" tab.
function setupProspects() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const p = ss.getSheetByName("Prospects") || ss.insertSheet("Prospects");
  p.getRange(1, 1, 1, 6).setValues([["Added", "Name", "Boy/Girl", "Nation", "Born", "Added by"]]).setFontWeight("bold");
  p.setFrozenRows(1);
  p.getRange("A:A").setNumberFormat("ddd d mmm yyyy HH:mm");
  setupRemovals();
}

// Run once by hand (setupProspects() runs it too): creates the "Removals" tab.
function setupRemovals() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const r = ss.getSheetByName("Removals") || ss.insertSheet("Removals");
  r.getRange(1, 1, 1, 9).setValues([["Asked", "Name", "Asked by", "Reason", "Status", "Decided", "Request ID", "Code", "Undo code"]]).setFontWeight("bold");
  r.setFrozenRows(1);
  r.getRange("A:A").setNumberFormat("ddd d mmm yyyy HH:mm");
  r.getRange("F:F").setNumberFormat("ddd d mmm yyyy HH:mm");
  r.hideColumns(7, 3);
}

// Called by the site. Adds a row for a new visit, or updates the row of a visit already logged.
function doPost(e) {
  let d;
  try { d = JSON.parse(e.postData.contents); } catch (err) { return out("bad"); }
  if (d.kind === "prospect") return addProspect(d);
  if (d.kind === "removal") return askRemoval(d);
  if (d.kind === "unremoval") return undoRemoval(d);
  if (d.kind === "comment") return addComment(d);
  if (d.kind === "uncomment") return undoComment(d);
  if (d.kind === "delcomment") return askDeleteComment(d);
  if (d.kind === "results") return askResults(d);
  if (d.kind === "light") return setLight(d);
  if (d.kind === "report") return saveReport(d);
  if (d.kind === "rpnote") return addReportNote(d);
  if (d.kind === "evrecap") return saveEventRecap(d);
  if (d.kind === "vidstart") return videoStart(d);
  if (d.kind === "vidchunk") return videoChunk(d);
  if (d.kind === "unvideo") return videoRemove(d);
  if (d.kind === "vidlink") return videoLink(d);
  if (d.kind === "vidcap") return videoCaption(d);
  const id = String(d.id || "").slice(0, 40), start = new Date(Number(d.start));
  if (!id || isNaN(start)) return out("bad");
  // text starting with = + - @ would be read as a formula, so it's kept as plain text
  const txt = (x, n) => { const t = String(x || "").trim().slice(0, n); return /^[=+\-@]/.test(t) ? "'" + t : t; };
  const row = [start, start, txt(d.name, 30) || "(no name)", Math.round((Number(d.secs) || 0) / 6) / 10,
    txt(d.device, 20), txt(d.pages, 200), id];
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Visits");
    const hit = sh.getRange("G:G").createTextFinder(id).matchEntireCell(true).findNext();
    if (hit) sh.getRange(hit.getRow(), 1, 1, 7).setValues([row]);
    else sh.appendRow(row);
  } finally {
    lock.releaseLock();
  }
  return out("ok");
}

function out(s) { return ContentService.createTextOutput(s); }

// Scouting Corner: a name typed into the "Add a prospect" box. One row each; a name already on the list is skipped.
function addProspect(d) {
  const clean = x => String(x || "").replace(/[\u0000-\u001f]/g, "").trim();
  const name = clean(d.name).replace(/\s+/g, " ").slice(0, 60);
  if (name.length < 3 || !/^[\p{L}][\p{L} .'\-|]+$/u.test(name)) return out("bad");
  const g = { M: "Boy", F: "Girl" }[clean(d.g).toUpperCase()] || "";
  const nat = /^[A-Za-z]{3}$/.test(clean(d.nat)) ? clean(d.nat).toUpperCase() : "";
  const born = /^(19|20)\d\d$/.test(clean(d.born)) ? Number(clean(d.born)) : "";
  const by = clean(d.by).slice(0, 30).replace(/^[=+\-@]/, "'$&");
  const key = s => String(s).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z]/g, "");
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Prospects");
    if (!sh) return out("no tab");
    const names = sh.getLastRow() > 1 ? sh.getRange(2, 2, sh.getLastRow() - 1, 1).getValues().map(r => key(r[0])) : [];
    if (names.includes(key(name))) return out("dup");
    sh.appendRow([new Date(), name, g, nat, born, by]);
    // added again after a removal was approved: the old removal no longer applies
    const rm = removalRows_().filter(x => x.status === "Approved" && key(x.name) === key(name));
    rm.forEach(x => x.sheet.getRange(x.row, 5).setValue("Re-added"));
  } finally {
    lock.releaseLock();
  }
  startLookup();
  return out("ok");
}

// Optional: starts the Scouting Corner update straight away, so a new name is looked up within a few minutes
// instead of at the next half-hourly run. Needs a GitHub token saved as the script property GH_TOKEN
// (see SCOUTING_CORNER.md); without one, nothing happens here.
function startLookup() {
  const token = PropertiesService.getScriptProperties().getProperty("GH_TOKEN");
  if (!token) return;
  try {
    UrlFetchApp.fetch("https://api.github.com/repos/tlock72/72-central/actions/workflows/prospects.yml/dispatches", {
      method: "post", contentType: "application/json", muteHttpExceptions: true,
      headers: { Authorization: "Bearer " + token, Accept: "application/vnd.github+json" },
      payload: JSON.stringify({ ref: "main" })
    });
  } catch (err) {}
}

// Scouting Corner: someone pressed "Request removal" on a card. One open request per name; Tobey is emailed.
function askRemoval(d) {
  const clean = x => String(x || "").replace(/[\u0000-\u001f]/g, "").trim();
  const plain = t => /^[=+\-@]/.test(t) ? "'" + t : t;  // never read as a formula
  const name = clean(d.name).replace(/\s+/g, " ").slice(0, 60);
  if (name.length < 3 || !/^[\p{L}][\p{L} .'\-|]+$/u.test(name)) return out("bad");
  const by = plain(clean(d.by).slice(0, 30)), why = plain(clean(d.reason).slice(0, 300));
  const undo = /^[a-f0-9]{16,64}$/.test(String(d.undo || "")) ? String(d.undo) : "";  // secret kept on the asker's device
  const key = s => String(s).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z]/g, "");
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  let id, code;
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const sh = ss.getSheetByName("Removals");
    if (!sh) return out("no tab");
    if (removalRows_().some(x => x.status === "Waiting" && key(x.name) === key(name))) return out("dup");
    id = Utilities.getUuid().slice(0, 8);
    code = Utilities.getUuid().replace(/-/g, "");  // secret: only in Tobey's email, so only Tobey can decide
    sh.appendRow([new Date(), name, by, why, "Waiting", "", id, code, undo]);
  } finally {
    lock.releaseLock();
  }
  try { removalEmail_(name, by, why, id, code); } catch (err) {}  // e.g. Google's daily email limit: the request is still on the "Removals" tab
  return out("ok");
}

// Where the emails go: the script property EMAIL if set (Project Settings > Script properties), else the Sheet owner's Google account.
function mailTo_() {
  return PropertiesService.getScriptProperties().getProperty("EMAIL") || Session.getEffectiveUser().getEmail();
}

function removalEmail_(name, by, why, id, code) {
  const link = ScriptApp.getService().getUrl() + "?kind=decide&id=" + id + "&code=" + code;
  MailApp.sendEmail(mailTo_(), "72 Central: remove " + name + " from Scouting Corner?",
    (String(by).replace(/^'/, "") || "Someone") + " asked for " + name + " to be removed from the Scouting Corner.\n" +
    (why ? "Reason given: " + String(why).replace(/^'/, "") + "\n" : "") +
    "\nOpen this link to approve or decline it:\n" + link + "\n\nNothing is removed until you approve. All requests are on the \"Removals\" tab of the visit-log Sheet.");
}

// Run by hand (pick it in the function dropdown, click Run): emails the approve/decline link again for every request still waiting.
function resendRemovals() {
  const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Removals");
  let n = 0;
  for (const x of removalRows_().filter(r => r.status === "Waiting" && r.id && r.code)) {
    const r = sh.getRange(x.row, 1, 1, 4).getValues()[0];
    removalEmail_(x.name, r[2], r[3], x.id, x.code);
    n++;
  }
  Logger.log(n + " email(s) sent to " + mailTo_());
}

// Scouting Corner: the person who asked pressed "Undo" on the card. Only their device has the undo code,
// so nobody else can withdraw it. Only a request still waiting can be withdrawn; Tobey gets a short email.
function undoRemoval(d) {
  const undo = String(d.undo || "");
  if (!/^[a-f0-9]{16,64}$/.test(undo)) return out("bad");
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  let name;
  try {
    const x = removalRows_().find(r => r.status === "Waiting" && r.undo && r.undo === undo);
    if (!x) return out("none");
    name = x.name;
    x.sheet.getRange(x.row, 5, 1, 2).setValues([["Withdrawn", new Date()]]);
  } finally {
    lock.releaseLock();
  }
  try {
    MailApp.sendEmail(mailTo_(), "72 Central: removal request for " + name + " withdrawn",
      "The person who asked for " + name + " to be removed from the Scouting Corner has withdrawn the request.\n" +
      "Nothing to do: " + name + " stays on the Scouting Corner.");
  } catch (err) {}
  return out("ok");
}

// Every row on the "Removals" tab, with its row number. (The _ at the end keeps it private: the page can't call it.)
function removalRows_() {
  const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Removals");
  if (!sh || sh.getLastRow() < 2) return [];
  return sh.getRange(2, 1, sh.getLastRow() - 1, 9).getValues().map((r, i) => ({
    sheet: sh, row: i + 2, name: String(r[1]).replace(/^'/, "").trim(), status: String(r[4]), id: String(r[6]), code: String(r[7]),
    undo: String(r[8] || "")
  })).filter(x => x.name);
}

// The page Tobey opens from the email. It only shows the request; nothing changes until a button is pressed
// (so an email link-scanner opening the link can't approve anything).
function decidePage(e) {
  const p = e.parameter, x = removalRows_().find(r => r.id === p.id && r.code && r.code === p.code);
  const t = HtmlService.createTemplate(
    '<div style="font-family:sans-serif;max-width:480px;margin:40px auto;line-height:1.5">' +
    '<h2>Scouting Corner: removal request</h2><p id="m"><?= msg ?></p>' +
    '<? if (open) { ?><button onclick="go(true)" style="padding:10px 18px;margin-right:8px">Approve: remove <?= name ?></button>' +
    '<button onclick="go(false)" style="padding:10px 18px">Decline: keep them</button><? } ?></div>' +
    '<script>function go(yes){document.querySelectorAll("button").forEach(b=>b.disabled=true);' +
    'google.script.run.withSuccessHandler(t=>{document.getElementById("m").textContent=t;document.querySelectorAll("button").forEach(b=>b.remove())})' +
    '.decideRemoval(<?!= JSON.stringify(id) ?>,<?!= JSON.stringify(code) ?>,yes)}</script>');
  t.open = !!x && x.status === "Waiting";
  t.name = x ? x.name : "";
  t.id = x ? x.id : ""; t.code = x ? x.code : "";  // only the Sheet's own values go into the page
  t.msg = !x ? "This request wasn't found (the link may be incomplete)."
    : t.open ? "Remove " + x.name + " from the Scouting Corner?"
    : x.status === "Withdrawn" ? x.name + ": the person who asked has withdrawn this request. Nothing to do."
    : x.name + ": already decided (" + x.status + ").";
  return t.evaluate().setTitle("72 Central: removal request");
}

// Called by the Approve / Decline buttons. Approved: the request is marked, their "Prospects" row is deleted and
// GitHub is asked to update the Scouting Corner (prospects.py also leaves out anyone approved here).
function decideRemoval(id, code, yes) {
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  let name;
  try {
    const x = removalRows_().find(r => r.id === String(id) && r.code && r.code === String(code));
    if (!x) return "This request wasn't found.";
    if (x.status === "Withdrawn") return x.name + ": the person who asked has withdrawn this request. Nothing to do.";
    if (x.status !== "Waiting") return x.name + ": already decided (" + x.status + ").";
    name = x.name;
    x.sheet.getRange(x.row, 5, 1, 2).setValues([[yes ? "Approved" : "Declined", new Date()]]);
    if (!yes) return "Declined: " + name + " stays on the Scouting Corner.";
    const key = s => String(s).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z]/g, "");
    const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Prospects");
    if (sh && sh.getLastRow() > 1) {
      const names = sh.getRange(2, 2, sh.getLastRow() - 1, 1).getValues();
      for (let i = names.length - 1; i >= 0; i--) if (key(String(names[i][0]).split("|")[0]) === key(name.split("|")[0])) sh.deleteRow(i + 2);
    }
  } finally {
    lock.releaseLock();
  }
  startLookup();
  return "Approved: " + name + " is taken off the Scouting Corner (the site updates within about 30 minutes, often sooner).";
}

// ---------- Comments on players ----------
// Creates the "Comments" tab (also made automatically by the first comment). Run by hand only if you want it before then.
function setupComments() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const c = ss.getSheetByName("Comments") || ss.insertSheet("Comments");
  c.getRange(1, 1, 1, 11).setValues([["Written", "Player", "Comment", "By", "Status", "Decided", "Delete asked by", "Reason",
    "Comment ID", "Code", "Undo code"]]).setFontWeight("bold");
  c.setFrozenRows(1);
  c.getRange("A:A").setNumberFormat("ddd d mmm yyyy HH:mm");
  c.getRange("F:F").setNumberFormat("ddd d mmm yyyy HH:mm");
  c.setColumnWidth(3, 420);
  c.getRange("C:C").setWrap(true);
  c.hideColumns(9, 3);
  return c;
}

// Every row on the "Comments" tab, with its row number.
function commentRows_() {
  const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Comments");
  if (!sh || sh.getLastRow() < 2) return [];
  return sh.getRange(2, 1, sh.getLastRow() - 1, 11).getValues().map((r, i) => ({
    sheet: sh, row: i + 2, at: r[0], name: String(r[1]).replace(/^'/, "").trim(), text: String(r[2]).replace(/^'/, ""),
    by: String(r[3]).replace(/^'/, ""), status: String(r[4]), askedBy: String(r[6]).replace(/^'/, ""), why: String(r[7]).replace(/^'/, ""),
    id: String(r[8]), code: String(r[9]), undo: String(r[10] || "")
  })).filter(x => x.name && x.id);
}

// Someone wrote a comment on the site. The id comes from the page (so it can show it straight away); the undo
// code is a secret only the writer's device has.
function addComment(d) {
  const clean = x => String(x || "").replace(/[\u0000-\u0009\u000b-\u001f]/g, "").trim();
  const plain = t => /^[=+\-@]/.test(t) ? "'" + t : t;  // never read as a formula
  const name = clean(d.name).replace(/\s+/g, " ").slice(0, 60);
  if (name.length < 3 || !/^[\p{L}][\p{L} .'\-|]+$/u.test(name)) return out("bad");
  const text = clean(d.text).slice(0, 1000), by = clean(d.by).slice(0, 30);
  const id = String(d.id || ""), undo = String(d.undo || "");
  if (!text || !by || !/^[a-f0-9]{8}$/.test(id) || !/^[a-f0-9]{16,64}$/.test(undo)) return out("bad");
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Comments") || setupComments();
    if (commentRows_().some(x => x.id === id)) return out("dup");
    sh.appendRow([new Date(), plain(name), plain(text), plain(by), "Live", "", "", "", id, "", undo]);
  } finally {
    lock.releaseLock();
  }
  return out("ok");
}

// The writer pressed "Undo": only their device has the undo code, and only within an hour of writing it.
function undoComment(d) {
  const undo = String(d.undo || "");
  if (!/^[a-f0-9]{16,64}$/.test(undo)) return out("bad");
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const x = commentRows_().find(r => r.undo && r.undo === undo);
    if (!x || x.status === "Deleted" || x.status === "Undone") return out("none");
    if (!(x.at instanceof Date) || Date.now() - x.at.getTime() > 65 * 60 * 1000) return out("late");  // an hour, plus a few minutes for slow connections
    x.sheet.getRange(x.row, 5, 1, 2).setValues([["Undone", new Date()]]);
  } finally {
    lock.releaseLock();
  }
  return out("ok");
}

// Someone pressed "Request deletion" on a comment. One open request per comment; Tobey is emailed.
function askDeleteComment(d) {
  const clean = x => String(x || "").replace(/[\u0000-\u001f]/g, "").trim();
  const plain = t => /^[=+\-@]/.test(t) ? "'" + t : t;
  const id = String(d.id || "");
  if (!/^[a-f0-9]{8}$/.test(id)) return out("bad");
  const by = plain(clean(d.by).slice(0, 30)), why = plain(clean(d.reason).slice(0, 300));
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  let x, code;
  try {
    x = commentRows_().find(r => r.id === id);
    if (!x || x.status === "Deleted" || x.status === "Undone") return out("none");
    if (x.status === "Delete requested") return out("dup");
    code = Utilities.getUuid().replace(/-/g, "");  // secret: only in Tobey's email, so only Tobey can decide
    x.sheet.getRange(x.row, 5, 1, 6).setValues([["Delete requested", "", by, why, id, code]]);
  } finally {
    lock.releaseLock();
  }
  try { deleteCommentEmail_(x, String(by).replace(/^'/, ""), String(why).replace(/^'/, ""), code); } catch (err) {}  // e.g. Google's daily email limit: it's still on the "Comments" tab
  return out("ok");
}

function deleteCommentEmail_(x, by, why, code) {
  const link = ScriptApp.getService().getUrl() + "?kind=decidecomment&id=" + x.id + "&code=" + code;
  const when = x.at instanceof Date ? Utilities.formatDate(x.at, TZ, "d MMM yyyy HH:mm") : "";
  MailApp.sendEmail(mailTo_(), "72 Central: delete a comment on " + x.name + "?",
    (by || "Someone") + " asked for this comment on " + x.name + " to be deleted:\n\n" +
    "\"" + x.text + "\"\n(written by " + (x.by || "someone") + (when ? ", " + when : "") + ")\n\n" +
    (why ? "Reason given: " + why + "\n\n" : "") +
    "Open this link to approve or decline it:\n" + link + "\n\nNothing is deleted until you approve. All comments are on the \"Comments\" tab of the visit-log Sheet.");
}

// The page Tobey opens from the email. Nothing changes until a button is pressed.
function decideCommentPage(e) {
  const p = e.parameter, x = commentRows_().find(r => r.id === p.id && r.code && r.code === p.code);
  const t = HtmlService.createTemplate(
    '<div style="font-family:sans-serif;max-width:480px;margin:40px auto;line-height:1.5">' +
    '<h2>Delete a comment?</h2><p id="m"><?= msg ?></p><? if (text) { ?><blockquote style="border-left:3px solid #D0A579;margin:0 0 16px;padding:4px 12px;white-space:pre-wrap"><?= text ?></blockquote><? } ?>' +
    '<? if (open) { ?><button onclick="go(true)" style="padding:10px 18px;margin-right:8px">Approve: delete it</button>' +
    '<button onclick="go(false)" style="padding:10px 18px">Decline: keep it</button><? } ?></div>' +
    '<script>function go(yes){document.querySelectorAll("button").forEach(b=>b.disabled=true);' +
    'google.script.run.withSuccessHandler(t=>{document.getElementById("m").textContent=t;document.querySelectorAll("button").forEach(b=>b.remove())})' +
    '.decideComment(<?!= JSON.stringify(id) ?>,<?!= JSON.stringify(code) ?>,yes)}</script>');
  t.open = !!x && x.status === "Delete requested";
  t.text = x ? x.text : "";
  t.id = x ? x.id : ""; t.code = x ? x.code : "";
  t.msg = !x ? "This request wasn't found (the link may be incomplete)."
    : t.open ? (x.askedBy || "Someone") + " asked to delete this comment on " + x.name + " by " + (x.by || "someone") + (x.why ? ". Reason: " + x.why : "") + "."
    : x.status === "Undone" ? "The writer took this comment back themselves. Nothing to do."
    : "Already decided (" + x.status + ").";
  return t.evaluate().setTitle("72 Central: delete a comment?");
}

// Called by the Approve / Decline buttons.
function decideComment(id, code, yes) {
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const x = commentRows_().find(r => r.id === String(id) && r.code && r.code === String(code));
    if (!x) return "This request wasn't found.";
    if (x.status === "Undone") return "The writer took this comment back themselves. Nothing to do.";
    if (x.status !== "Delete requested") return "Already decided (" + x.status + ").";
    x.sheet.getRange(x.row, 5, 1, 2).setValues([[yes ? "Deleted" : "Kept", new Date()]]);
    return yes ? "Deleted: the comment on " + x.name + " is gone from the site (within about 10 minutes for anyone with it open)."
      : "Declined: the comment on " + x.name + " stays.";
  } finally {
    lock.releaseLock();
  }
}

// ---------- Last 12 months on request (Filtered Rankings) ----------
const LOOKUP_TOURS = ["atp", "wta", "itfb", "itfg", "teb14", "teg14"];

// Someone pressed "12 months" on a Filtered Rankings row for a player with no results saved yet (or not today).
// One row per request; the same player asked again within 10 minutes is skipped. GitHub checks the name against
// its own ranking list, so nothing typed here is trusted.
function askResults(d) {
  const clean = x => String(x || "").replace(/[\u0000-\u001f]/g, "").trim();
  const tour = clean(d.tour);
  const name = clean(d.name).replace(/\s+/g, " ").slice(0, 80);
  if (!LOOKUP_TOURS.includes(tour) || name.length < 2 || !/^[\p{L}][\p{L} .'\-]+$/u.test(name)) return out("bad");
  const url = /^https:\/\/(www\.itftennis\.com|www\.tennisabstract\.com|te\.tournamentsoftware\.com|www\.wtatennis\.com)\/[^\s"<>]{1,200}$/.test(clean(d.url)) ? clean(d.url) : "";
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    let sh = ss.getSheetByName("Lookups");
    if (!sh) {
      sh = ss.insertSheet("Lookups");
      sh.getRange(1, 1, 1, 4).setValues([["Asked", "List", "Player", "Link"]]).setFontWeight("bold");
      sh.setFrozenRows(1);
      sh.getRange("A:A").setNumberFormat("ddd d mmm yyyy HH:mm");
    }
    const n = sh.getLastRow() - 1, recent = n > 0 ? sh.getRange(Math.max(2, n - 48), 1, Math.min(n, 50), 3).getValues() : [];
    if (recent.some(r => r[0] instanceof Date && Date.now() - r[0] < 6e5 && r[1] === tour && r[2] === name)) return out("dup");
    sh.appendRow([new Date(), tour, name, url]);
  } finally {
    lock.releaseLock();
  }
  startResults();
  return out("ok");
}

// Starts GitHub's look-up straight away (needs GH_TOKEN, as for the Scouting Corner); without it, GitHub's
// half-hourly run picks the request up.
function startResults() {
  const token = PropertiesService.getScriptProperties().getProperty("GH_TOKEN");
  if (!token) return;
  try {
    UrlFetchApp.fetch("https://api.github.com/repos/tlock72/72-central/actions/workflows/results.yml/dispatches", {
      method: "post", contentType: "application/json", muteHttpExceptions: true,
      headers: { Authorization: "Bearer " + token, Accept: "application/vnd.github+json" },
      payload: JSON.stringify({ ref: "main" })
    });
  } catch (err) {}
}

// Read by GitHub (scripts/lookup_results.py): the requests of the last 3 days.
function listLookups() {
  const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Lookups");
  const rows = sh && sh.getLastRow() > 1 ? sh.getRange(2, 1, sh.getLastRow() - 1, 4).getValues() : [];
  const list = rows.filter(r => r[0] instanceof Date && Date.now() - r[0] < 3 * 864e5)
    .map(r => ({ at: Utilities.formatDate(r[0], "UTC", "yyyy-MM-dd'T'HH:mm:ss'Z'"), tour: String(r[1]), name: String(r[2]), url: String(r[3] || "") }));
  return ContentService.createTextOutput(JSON.stringify({ lookups: list })).setMimeType(ContentService.MimeType.JSON);
}

// Read by the site: every comment still showing (not undone or deleted). Undo and approval codes never leave the Sheet.
function listComments() {
  const list = commentRows_().filter(x => x.status !== "Undone" && x.status !== "Deleted" && x.at instanceof Date).map(x => ({
    id: x.id, name: x.name, text: x.text, by: x.by, at: x.at.toISOString(), status: x.status === "Delete requested" ? "asked" : "live"
  }));
  return ContentService.createTextOutput(JSON.stringify({ comments: list })).setMimeType(ContentService.MimeType.JSON);
}

// Scouting Corner traffic lights: one row per change on the "Lights" tab, so there's a history of who set what.
const LIGHTS = { g: "Green", a: "Amber", r: "Red", x: "Cleared" };
function setupLights() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const t = ss.getSheetByName("Lights") || ss.insertSheet("Lights");
  t.getRange(1, 1, 1, 4).setValues([["Set", "Player", "Light", "Set by"]]).setFontWeight("bold");
  t.setFrozenRows(1);
  t.getRange("A:A").setNumberFormat("ddd d mmm yyyy HH:mm");
  return t;
}
function setLight(d) {
  const clean = x => String(x || "").replace(/[\u0000-\u001f]/g, "").trim();
  const plain = t => /^[=+\-@]/.test(t) ? "'" + t : t;
  const name = clean(d.name).replace(/\s+/g, " ").slice(0, 60);
  if (name.length < 3 || !/^[\p{L}][\p{L} .'\-|]+$/u.test(name)) return out("bad");
  const light = LIGHTS[clean(d.light)];
  if (!light) return out("bad");
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Lights") || setupLights();
    sh.appendRow([new Date(), plain(name), light, plain(clean(d.by).slice(0, 30))]);
  } finally {
    lock.releaseLock();
  }
  return out("ok");
}
// Read by the site (?kind=lights): the newest light for each player (any accents or word order count as the same name)
function listLights() {
  const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Lights");
  const rows = sh && sh.getLastRow() > 1 ? sh.getRange(2, 1, sh.getLastRow() - 1, 4).getValues() : [];
  const code = { green: "g", amber: "a", red: "r", cleared: "x" };
  const key = s => String(s).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().split(/[^a-z]+/).filter(Boolean).sort().join(" ");
  const last = {};
  rows.forEach(r => {
    const name = String(r[1]).replace(/^'/, "").trim(), l = code[String(r[2]).trim().toLowerCase()];
    if (!name || !l || !(r[0] instanceof Date)) return;
    const k = key(name);
    if (!last[k] || r[0] >= last[k].d) last[k] = { d: r[0], name, light: l, by: String(r[3] || "").replace(/^'/, ""), at: r[0].toISOString() };
  });
  const list = Object.values(last).map(x => ({ name: x.name, light: x.light, by: x.by, at: x.at }));
  return ContentService.createTextOutput(JSON.stringify({ lights: list })).setMimeType(ContentService.MimeType.JSON);
}

// Read by GitHub (scripts/prospects.py) and by the site: the names added on the site, plus removal requests
// (names only; the request IDs and codes never leave the Sheet).
function doGet(e) {
  const kind = (e && e.parameter && e.parameter.kind) || "";
  if (kind === "decide") return decidePage(e);
  if (kind === "decidecomment") return decideCommentPage(e);
  if (kind === "comments") return listComments();
  if (kind === "lookups") return listLookups();
  if (kind === "lights") return listLights();
  if (kind === "reports") return listReports(e);
  if (kind !== "prospects") return out("72 Central");
  const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Prospects");
  const rows = sh && sh.getLastRow() > 1 ? sh.getRange(2, 1, sh.getLastRow() - 1, 6).getValues() : [];
  const list = rows.filter(r => String(r[1]).trim()).map(r => ({
    name: String(r[1]).replace(/^'/, "").trim(), g: { Boy: "M", Girl: "F" }[r[2]] || "", nat: String(r[3] || ""),
    born: r[4] ? Number(r[4]) : null, by: String(r[5] || "").replace(/^'/, ""),
    at: r[0] instanceof Date ? Utilities.formatDate(r[0], TZ, "yyyy-MM-dd") : ""
  }));
  const rm = removalRows_();
  const removed = rm.filter(x => x.status === "Approved").map(x => x.name);
  const asked = rm.filter(x => x.status === "Waiting").map(x => x.name);
  return ContentService.createTextOutput(JSON.stringify({ prospects: list, removed, asked })).setMimeType(ContentService.MimeType.JSON);
}

// ---------- Scouting reports and videos (Scouting Corner) ----------
// Choice answers the form can send (the same lists as RP_FIELDS in index.html); anything else is left blank.
const REPORT_FIELDS = [
  ["seen", "Seen at"], ["seenOn", "Date seen"], ["light", "Traffic light", ["Green", "Amber", "Red"]],
  ["hand", "Plays", ["Right-handed", "Left-handed"]], ["bh", "Backhand", ["One-handed", "Two-handed"]],
  ["style", "Style", ["Aggressive baseliner", "Counter-puncher", "All-court", "Big server", "Serve and volley", "Other"]],
  ["win", "Winning potential", ["1", "2", "3", "4", "5"]],
  ["rank", "Peak ranking", ["Top 5", "Top 10", "Top 20", "Top 50", "Top 100", "Top 200", "Top 500", "Outside 500"]],
  ["major", "Can win a Major", ["Yes", "Possibly", "Unlikely", "No"]],
  ["game", "Game style"], ["plan", "Game plan"], ["str", "Strengths"], ["weak", "Weaknesses"],
  ["tech", "Technical"], ["phys", "Physical"], ["pers", "Personality"], ["team", "Team structure"],
  ["fam", "Family involvement"], ["comm", "Commercial in place"], ["mkt", "Marketability", ["1", "2", "3", "4", "5"]],
  ["agency", "Agency", ["No agency", "Has an agency", "Not sure"]], ["agName", "Agency name"], ["other", "Other comments"]
];
const REPORT_FIXED = ["Saved", "Report ID", "Player", "Male/Female", "Nation", "Born", "Saved by", "Status"];
const clean_ = x => String(x == null ? "" : x).replace(/[\u0000-\u0009\u000b-\u001f]/g, "").trim();
const plain_ = t => /^[=+\-@]/.test(t) ? "'" + t : t;  // never read as a formula
const unplain_ = t => String(t == null ? "" : t).replace(/^'/, "");
const json_ = o => ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
const okName_ = n => n.length >= 3 && /^[\p{L}][\p{L} .'\-|]+$/u.test(n);

// Run once by hand after pasting this script: makes the "Reports" and "Videos" tabs and the Drive folder, and asks
// for Google Drive access (needed for the videos).
function setupReports() {
  reportSheet_(); videoSheet_(); videoFolder_();
}
// Hidden last column: a secret code from the device that started the report. That device can always edit it; any
// other device can only if it's signed in with the same first name as the person who started it.
const REPORT_OWN_COL = REPORT_FIXED.length + REPORT_FIELDS.length + 1;
// Answers added later (Nov 2026) go after the Owner code column, so the columns already on the Sheet never move
const REPORT_MORE = [["insta", "Instagram"], ["contact", "Contacts"]];
const REPORT_COLS = REPORT_OWN_COL + REPORT_MORE.length;
const igHandle_ = t => { const m = clean_(t).replace(/^(https?:\/\/)?(www\.)?instagram\.com\//i, "").replace(/^@/, "").split(/[/?#\s]/)[0]; return /^[A-Za-z0-9._]{1,30}$/.test(m) ? "@" + m : ""; };
function reportSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName("Reports");
  if (!sh) {
    sh = ss.insertSheet("Reports");
    const head = REPORT_FIXED.concat(REPORT_FIELDS.map(f => f[1]));
    sh.getRange(1, 1, 1, head.length).setValues([head]).setFontWeight("bold");
    sh.setFrozenRows(1); sh.setFrozenColumns(3);
    sh.getRange("A:A").setNumberFormat("ddd d mmm yyyy HH:mm");
    sh.getRange(2, REPORT_FIXED.length + 1, sh.getMaxRows() - 1, REPORT_FIELDS.length).setWrap(true).setVerticalAlignment("top");
    sh.hideColumns(2);
  }
  if (sh.getMaxColumns() < REPORT_OWN_COL) sh.insertColumnsAfter(sh.getMaxColumns(), REPORT_OWN_COL - sh.getMaxColumns());
  if (!sh.getRange(1, REPORT_OWN_COL).getValue()) { sh.getRange(1, REPORT_OWN_COL).setValue("Owner code").setFontWeight("bold"); sh.hideColumns(REPORT_OWN_COL); }
  if (sh.getMaxColumns() < REPORT_COLS) sh.insertColumnsAfter(sh.getMaxColumns(), REPORT_COLS - sh.getMaxColumns());
  REPORT_MORE.forEach(([, h], i) => { const c = sh.getRange(1, REPORT_OWN_COL + 1 + i); if (!c.getValue()) { c.setValue(h).setFontWeight("bold"); sh.getRange(2, REPORT_OWN_COL + 1 + i, sh.getMaxRows() - 1, 1).setWrap(true).setVerticalAlignment("top"); } });
  return sh;
}
// Every row of every report, oldest first per report: { id: [rows] }
function reportRows_() {
  const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Reports");
  const rows = sh && sh.getLastRow() > 1 ? sh.getRange(2, 1, sh.getLastRow() - 1, Math.min(REPORT_COLS, sh.getMaxColumns())).getValues() : [];
  const by = {};
  rows.forEach(r => { const id = String(r[1]); if (id && r[0] instanceof Date) (by[id] = by[id] || []).push(r); });
  Object.values(by).forEach(l => l.sort((a, b) => a[0] - b[0]));
  return by;
}
const sameName_ = (a, b) => !!String(a || "").trim() && String(a).trim().toLowerCase() === String(b || "").trim().toLowerCase();

// A report saved on the site: "Draft" (unfinished, only its author sees it), "Live" (published), or "Discarded"
// (the author threw away an unfinished draft; a published version stays). Every save is a new row. Only the person
// who started a report can save it again: same first name, or the device that started it (owner code).
function saveReport(d) {
  const name = clean_(d.name).replace(/\s+/g, " ").slice(0, 60);
  const id = String(d.id || "");
  if (!okName_(name) || !/^[a-f0-9]{12}$/.test(id)) return out("bad");
  const status = { Draft: "Draft", Discarded: "Discarded" }[d.status] || "Live";
  const own = /^[a-f0-9]{16,64}$/.test(String(d.own || "")) ? String(d.own) : "";
  const by = clean_(d.by).slice(0, 30);
  const g = { M: "Male", F: "Female" }[clean_(d.g).toUpperCase()] || "";
  const nat = /^[A-Za-z]{3}$/.test(clean_(d.nat)) ? clean_(d.nat).toUpperCase() : "";
  const born = /^(19|20)\d\d$/.test(clean_(d.born)) ? Number(clean_(d.born)) : "";
  const f = d.f || {};
  const vals = REPORT_FIELDS.map(([k, , opts]) => {
    const v = clean_(f[k]);
    if (k === "style" && /^Other(: .+)?$/s.test(v)) return plain_(v.slice(0, 210));  // "Other: <their own words>"
    if (opts) return opts.includes(v) ? v : "";
    if (k === "seenOn") return /^20\d\d-\d\d-\d\d$/.test(v) ? v : "";
    return plain_(v.slice(0, 4000));
  });
  const more = REPORT_MORE.map(([k]) => k === "insta" ? igHandle_(f[k]) : plain_(clean_(f[k]).slice(0, 1000)));
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const sh = reportSheet_(), old = reportRows_()[id] || [];
    let code = own;
    if (old.length) {
      const first = old[0], last = old[old.length - 1];
      if (String(last[7]).trim() === "Deleted") return out("deleted");
      if (!(sameName_(by, unplain_(first[6])) || (own && own === String(first[REPORT_OWN_COL - 1])))) return out("notyours");
      code = String(first[REPORT_OWN_COL - 1] || own);
    }
    sh.appendRow([new Date(), id, plain_(name), g, nat, born, plain_(by), status].concat(vals, [code], more));
  } finally {
    lock.releaseLock();
  }
  return out("ok");
}

// Read by the site (?kind=reports&by=<first name>&own=<codes>): the newest published version of every report that
// isn't deleted, the asker's own unfinished drafts, the comments on reports, and every clip still up.
// Owner codes and undo codes never leave the Sheet.
function listReports(e) {
  const p = (e && e.parameter) || {}, me = clean_(p.by), mine = new Set(String(p.own || "").split(",").filter(x => /^[a-f0-9]{16,64}$/.test(x)));
  const rep = (r, first, firstLive) => {
    const f = {};
    REPORT_FIELDS.forEach(([k], i) => {
      let v = r[REPORT_FIXED.length + i];
      if (v instanceof Date) v = Utilities.formatDate(v, TZ, "yyyy-MM-dd");  // a typed date the Sheet turned into a date
      v = unplain_(v).trim(); if (v) f[k] = v;
    });
    REPORT_MORE.forEach(([k], i) => { const v = unplain_(r[REPORT_OWN_COL + i]).trim(); if (v) f[k] = v; });
    return { id: String(r[1]), name: unplain_(r[2]).trim(), g: { Male: "M", Female: "F" }[r[3]] || "", nat: String(r[4] || ""), born: r[5] ? Number(r[5]) : null,
      by: unplain_(r[6]), at: r[0].toISOString(), firstBy: unplain_(first[6]), firstAt: (firstLive || r)[0].toISOString(), f };
  };
  const reports = [], drafts = [];
  Object.values(reportRows_()).forEach(rows => {
    const st = r => String(r[7]).trim(), last = rows[rows.length - 1], first = rows[0];
    if (st(last) === "Deleted") return;
    const live = rows.filter(r => st(r) !== "Draft" && st(r) !== "Discarded"), pub = live[live.length - 1];
    if (pub) reports.push(rep(pub, first, live[0]));
    if (st(last) === "Draft" && (sameName_(me, unplain_(first[6])) || mine.has(String(first[REPORT_OWN_COL - 1]))))
      drafts.push(Object.assign(rep(last, first, live[0]), { pub: !!pub }));
  });
  const ns = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Report comments");
  const nrows = ns && ns.getLastRow() > 1 ? ns.getRange(2, 1, ns.getLastRow() - 1, 7).getValues() : [];
  const notes = nrows.filter(r => r[0] instanceof Date && String(r[5]).trim() !== "Deleted").map(r => ({
    id: String(r[6]), rid: String(r[1]), name: unplain_(r[2]), text: unplain_(r[3]), by: unplain_(r[4]), at: r[0].toISOString()
  }));
  const vs = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Videos");
  const vrows = vs && vs.getLastRow() > 1 ? vs.getRange(2, 1, vs.getLastRow() - 1, 11).getValues() : [];
  const videos = vrows.filter(r => r[6] && String(r[4]).trim() === "Live" && r[0] instanceof Date).map(r => ({
    id: String(r[6]), name: unplain_(r[1]).trim(), cap: unplain_(r[2]), by: unplain_(r[3]), rid: String(r[5] || ""), at: r[0].toISOString(), mb: Number(r[10]) || null,
    url: /^L[a-f0-9]{16}$/.test(String(r[6])) ? unplain_(r[7]) : ""
  }));
  // event recaps: the newest row for each event (event words + year); none if that row says "Deleted"
  const es = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Event recaps");
  const erows = es && es.getLastRow() > 1 ? es.getRange(2, 1, es.getLastRow() - 1, 8).getValues() : [];
  const newest = {};
  erows.filter(r => r[0] instanceof Date).forEach(r => { const k = String(r[1]) + "|" + String(r[3]); if (!newest[k] || r[0] >= newest[k][0]) newest[k] = r; });
  const recaps = Object.values(newest).filter(r => String(r[6]).trim() !== "Deleted").map(r => ({
    key: String(r[1]), event: unplain_(r[2]), year: String(r[3]), text: unplain_(r[4]), by: unplain_(r[5]), at: r[0].toISOString()
  }));
  return json_({ reports, drafts, notes, videos, recaps });
}

// A comment on someone's report (the "Comments from the team" box under a report). One row each on the
// "Report comments" tab; set its Status to "Deleted" to take it down.
function addReportNote(d) {
  const rid = String(d.rid || ""), id = String(d.id || "");
  const name = clean_(d.name).replace(/\s+/g, " ").slice(0, 60), text = clean_(d.text).slice(0, 2000), by = clean_(d.by).slice(0, 30);
  if (!/^[a-f0-9]{12}$/.test(rid) || !/^[a-f0-9]{8}$/.test(id) || !text || !okName_(name)) return out("bad");
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    let sh = ss.getSheetByName("Report comments");
    if (!sh) {
      sh = ss.insertSheet("Report comments");
      sh.getRange(1, 1, 1, 7).setValues([["Added", "Report ID", "Player", "Comment", "By", "Status", "Comment ID"]]).setFontWeight("bold");
      sh.setFrozenRows(1);
      sh.getRange("A:A").setNumberFormat("ddd d mmm yyyy HH:mm");
      sh.getRange("D:D").setWrap(true);
      sh.hideColumns(2); sh.hideColumns(7);
    }
    if (sh.getLastRow() > 1 && sh.getRange("G:G").createTextFinder(id).matchEntireCell(true).findNext()) return out("dup");
    sh.appendRow([new Date(), rid, plain_(name), plain_(text), plain_(by || "Someone"), "Live", id]);
  } finally {
    lock.releaseLock();
  }
  return out("ok");
}

// An event recap (Scouting reports > By event). Anyone on the team can write or update one; each save is a new row
// on the "Event recaps" tab and the newest row for the event is shown. Set Status to "Deleted" to take it down.
function saveEventRecap(d) {
  const key = clean_(d.key).slice(0, 120), year = String(d.year || ""), id = String(d.id || "");
  const event = clean_(d.event).replace(/\s+/g, " ").slice(0, 80), text = clean_(d.text).slice(0, 6000), by = clean_(d.by).slice(0, 30);
  if (!/^[a-z0-9]+( [a-z0-9]+)*$/.test(key) || !/^20\d\d$/.test(year) || !/^[a-f0-9]{8}$/.test(id) || !event || !text) return out("bad");
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    let sh = ss.getSheetByName("Event recaps");
    if (!sh) {
      sh = ss.insertSheet("Event recaps");
      sh.getRange(1, 1, 1, 8).setValues([["Saved", "Event key", "Event", "Year", "Recap", "By", "Status", "Recap ID"]]).setFontWeight("bold");
      sh.setFrozenRows(1);
      sh.getRange("A:A").setNumberFormat("ddd d mmm yyyy HH:mm");
      sh.getRange("D:D").setNumberFormat("@");
      sh.getRange("E:E").setWrap(true);
      sh.hideColumns(2); sh.hideColumns(8);
    }
    if (sh.getLastRow() > 1 && sh.getRange("H:H").createTextFinder(id).matchEntireCell(true).findNext()) return out("ok");
    sh.appendRow([new Date(), key, plain_(event), year, plain_(text), plain_(by || "Someone"), "Live", id]);
  } finally {
    lock.releaseLock();
  }
  return out("ok");
}

function videoSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName("Videos");
  if (sh) return sh;
  sh = ss.insertSheet("Videos");
  sh.getRange(1, 1, 1, 11).setValues([["Added", "Player", "Caption", "Added by", "Status", "Report ID", "File ID", "Link", "Sharing", "Undo code", "Size (MB)"]]).setFontWeight("bold");
  sh.setFrozenRows(1);
  sh.getRange("A:A").setNumberFormat("ddd d mmm yyyy HH:mm");
  sh.hideColumns(6, 2); sh.hideColumns(10);
  return sh;
}
// The "72 Central scouting videos" folder in Drive (its id is remembered, so renaming or moving it is fine)
function videoFolder_() {
  const props = PropertiesService.getScriptProperties(), id = props.getProperty("VIDEO_FOLDER");
  if (id) { try { const f = DriveApp.getFolderById(id); if (!f.isTrashed()) return f; } catch (e) {} }
  const f = DriveApp.createFolder("72 Central scouting videos");
  props.setProperty("VIDEO_FOLDER", f.getId());
  return f;
}
function playerFolder_(name) {
  const root = videoFolder_(), it = root.getFoldersByName(name);
  return it.hasNext() ? it.next() : root.createFolder(name);
}

// Upload step 1: the site sends the clip's details; this opens a Google Drive upload for it and returns an upload id.
// The clip then comes in pieces (videoChunk), so a big phone video never has to fit in one message.
const VIDEO_MAX_MB = 300;
function videoStart(d) {
  const name = clean_(d.name).replace(/\s+/g, " ").slice(0, 60);
  const type = clean_(d.type).toLowerCase(), size = Number(d.size), undo = String(d.undo || "");
  if (!okName_(name) || !/^video\/[a-z0-9.+\-]+$/.test(type) || !(size > 0) || size > VIDEO_MAX_MB * 1048576 || !/^[a-f0-9]{16,64}$/.test(undo)) return json_({ ok: false, why: "bad" });
  const rid = /^[a-f0-9]{12}$/.test(String(d.rid || "")) ? String(d.rid) : "";
  const by = clean_(d.by).slice(0, 30), cap = clean_(d.cap).slice(0, 120);
  const ext = (clean_(d.file).match(/\.([A-Za-z0-9]{2,5})$/) || [, type.split("/")[1].replace("quicktime", "mov")])[1].toLowerCase();
  const stamp = Utilities.formatDate(new Date(), TZ, "yyyy-MM-dd HHmm");
  const folder = playerFolder_(name);
  const res = UrlFetchApp.fetch("https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&supportsAllDrives=true", {
    method: "post", contentType: "application/json; charset=UTF-8", muteHttpExceptions: true,
    headers: { Authorization: "Bearer " + ScriptApp.getOAuthToken(), "X-Upload-Content-Type": type, "X-Upload-Content-Length": String(size) },
    payload: JSON.stringify({ name: `${name} ${stamp}${by ? " (" + by + ")" : ""}.${ext}`, parents: [folder.getId()], description: cap })
  });
  const h = res.getAllHeaders(), loc = h.Location || h.location;
  if (res.getResponseCode() !== 200 || !loc) return json_({ ok: false, why: "drive " + res.getResponseCode() });
  const up = Utilities.getUuid().replace(/-/g, "");
  CacheService.getScriptCache().put("vid:" + up, JSON.stringify({ loc, name, by, cap, rid, size, type, undo }), 21600);
  return json_({ ok: true, up });
}

// Upload step 2, once per piece (in order): passes it on to Drive. The last piece finishes the file: it is shared
// as "anyone with the link can view" and gets its row on the "Videos" tab.
function videoChunk(d) {
  const cache = CacheService.getScriptCache(), raw = cache.get("vid:" + String(d.up || ""));
  if (!raw) return json_({ ok: false, why: "expired" });
  const u = JSON.parse(raw), start = Number(d.start);
  let bytes;
  try { bytes = Utilities.base64Decode(String(d.data || "")); } catch (e) { return json_({ ok: false, why: "bad" }); }
  if (!(start >= 0) || !bytes.length || start + bytes.length > u.size) return json_({ ok: false, why: "bad" });
  const res = UrlFetchApp.fetch(u.loc, {
    method: "put", contentType: u.type, payload: bytes, muteHttpExceptions: true, followRedirects: false,
    headers: { "Content-Range": `bytes ${start}-${start + bytes.length - 1}/${u.size}` }
  });
  const code = res.getResponseCode();
  if (code === 308) {
    const r = res.getAllHeaders().Range || res.getAllHeaders().range || "";
    const m = String(r).match(/-(\d+)$/);
    return json_({ ok: true, next: m ? Number(m[1]) + 1 : 0 });
  }
  if (code !== 200 && code !== 201) return json_({ ok: false, why: "drive " + code });
  const fid = JSON.parse(res.getContentText()).id;
  let sharing = "Anyone with the link";
  const file = DriveApp.getFileById(fid);
  try { file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW); }
  catch (e) {
    // some Google Workspace accounts don't allow sharing outside the organisation
    try { file.setSharing(DriveApp.Access.DOMAIN_WITH_LINK, DriveApp.Permission.VIEW); sharing = "Organisation with the link"; }
    catch (e2) { sharing = "Not shared: " + String(e2).slice(0, 80); }
  }
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    videoSheet_().appendRow([new Date(), plain_(u.name), plain_(u.cap), plain_(u.by), "Live", u.rid, fid,
      "https://drive.google.com/file/d/" + fid + "/view", sharing, u.undo, Math.round(u.size / 104857.6) / 10]);
  } finally {
    lock.releaseLock();
  }
  cache.remove("vid:" + d.up);
  return json_({ ok: true, done: true, id: fid, sharing });
}

// "Remove" on a clip: only the device that added it has the undo code, and only for a day. The file goes to Drive's bin.
function videoRemove(d) {
  const undo = String(d.undo || ""), id = String(d.id || "");
  if (!/^[a-f0-9]{16,64}$/.test(undo) || !id) return out("bad");
  const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Videos");
  if (!sh || sh.getLastRow() < 2) return out("none");
  const rows = sh.getRange(2, 1, sh.getLastRow() - 1, 10).getValues();
  const i = rows.findIndex(r => String(r[6]) === id && String(r[9]) === undo);
  if (i < 0) return out("none");
  if (!(rows[i][0] instanceof Date) || Date.now() - rows[i][0] > 864e5) return out("late");
  sh.getRange(i + 2, 5).setValue("Removed");
  if (!/^L/.test(id)) { try { DriveApp.getFileById(id).setTrashed(true); } catch (e) {} }  // a pasted link has no file
  return out("ok");
}

// "Edit" on a video's description: only the person who added it (same first name, or the device that added it, by
// its undo code). Changes the Caption column of its row.
function videoCaption(d) {
  const id = String(d.id || ""), undo = String(d.undo || ""), by = clean_(d.by).slice(0, 30), cap = clean_(d.cap).replace(/\s+/g, " ").slice(0, 120);
  if (!id || id.length > 100) return out("bad");
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Videos");
    if (!sh || sh.getLastRow() < 2) return out("none");
    const rows = sh.getRange(2, 1, sh.getLastRow() - 1, 10).getValues();
    const i = rows.findIndex(r => String(r[6]) === id && String(r[4]).trim() === "Live");
    if (i < 0) return out("none");
    const mine = (/^[a-f0-9]{16,64}$/.test(undo) && String(rows[i][9]) === undo) || sameName_(by, unplain_(rows[i][3]));
    if (!mine) return out("notyours");
    sh.getRange(i + 2, 3).setValue(plain_(cap));
  } finally {
    lock.releaseLock();
  }
  return out("ok");
}

// A link to a video somewhere else (YouTube, Instagram, TikTok, Vimeo, any web page), pasted on the site's
// "Paste a link" box: a row on the "Videos" tab like an uploaded clip, with the link in the Link column.
function videoLink(d) {
  const name = clean_(d.name).replace(/\s+/g, " ").slice(0, 60), id = String(d.id || ""), undo = String(d.undo || "");
  const url = clean_(d.url).slice(0, 500);
  if (!okName_(name) || !/^L[a-f0-9]{16}$/.test(id) || !/^[a-f0-9]{16,64}$/.test(undo) || !/^https?:\/\/[^\s"<>]+\.[^\s"<>]+$/i.test(url)) return out("bad");
  const rid = /^[a-f0-9]{12}$/.test(String(d.rid || "")) ? String(d.rid) : "";
  const by = clean_(d.by).slice(0, 30), cap = clean_(d.cap).slice(0, 120);
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const sh = videoSheet_();
    if (sh.getLastRow() > 1 && sh.getRange("G:G").createTextFinder(id).matchEntireCell(true).findNext()) return out("ok");
    sh.appendRow([new Date(), plain_(name), plain_(cap), plain_(by), "Live", rid, id, plain_(url), "Link", undo, ""]);
  } finally {
    lock.releaseLock();
  }
  return out("ok");
}
