/** @OnlyCurrentDoc */
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
  if (d.kind === "brand") return addBrand(d);
  if (d.kind === "unbrand") return removeBrand(d);
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

// News > Market map > Brands: the team's shortlist of brands to approach, one row per brand and market, on the
// "Brands" tab (made automatically). "Shortlist" adds a row (or brings back one taken off); pressing it again takes
// it off (Status "Removed", who and when kept). Nothing else is ever deleted.
function brandsTab_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName("Brands");
  if (!sh) {
    sh = ss.insertSheet("Brands");
    sh.getRange(1, 1, 1, 10).setValues([["Added", "Brand", "Market", "Sector", "Why", "Headline", "Link", "By", "Status", "Changed"]]).setFontWeight("bold");
    sh.setFrozenRows(1);
    sh.getRange("A:A").setNumberFormat("ddd d mmm yyyy HH:mm");
    sh.getRange("J:J").setNumberFormat("ddd d mmm yyyy HH:mm");
  }
  return sh;
}
function brandText_(x, n) {
  const t = String(x || "").replace(/[\u0000-\u001f]/g, "").replace(/\s+/g, " ").trim().slice(0, n);
  return /^[=+\-@]/.test(t) ? "'" + t : t;  // never read as a formula
}
function addBrand(d) {
  const brand = brandText_(d.brand, 60), market = brandText_(d.market, 40), by = brandText_(d.by, 30);
  if (brand.length < 2 || market.length < 2 || !by) return out("bad");
  const link = /^https:\/\/[^\s"<>]{1,500}$/.test(String(d.link || "")) ? String(d.link) : "";
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const sh = brandsTab_();
    const rows = sh.getLastRow() > 1 ? sh.getRange(2, 1, sh.getLastRow() - 1, 10).getValues() : [];
    const i = rows.findIndex(r => String(r[1]).replace(/^'/, "") === brand.replace(/^'/, "") && String(r[2]) === market);
    if (i >= 0) {
      if (rows[i][8] === "Shortlisted") return out("dup");
      sh.getRange(i + 2, 8, 1, 3).setValues([[by, "Shortlisted", new Date()]]);
      return out("ok");
    }
    sh.appendRow([new Date(), brand, market, brandText_(d.sector, 40), brandText_(d.why, 120), brandText_(d.headline, 300), link, by, "Shortlisted", ""]);
  } finally {
    lock.releaseLock();
  }
  return out("ok");
}
function removeBrand(d) {
  const brand = brandText_(d.brand, 60), market = brandText_(d.market, 40), by = brandText_(d.by, 30);
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const sh = brandsTab_();
    const rows = sh.getLastRow() > 1 ? sh.getRange(2, 1, sh.getLastRow() - 1, 10).getValues() : [];
    const i = rows.findIndex(r => String(r[1]).replace(/^'/, "") === brand.replace(/^'/, "") && String(r[2]) === market && r[8] === "Shortlisted");
    if (i < 0) return out("none");
    sh.getRange(i + 2, 9, 1, 2).setValues([["Removed by " + by.replace(/^'/, ""), new Date()]]);
  } finally {
    lock.releaseLock();
  }
  return out("ok");
}
// Read by the site: every brand still shortlisted.
function listBrands() {
  const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Brands");
  const rows = sh && sh.getLastRow() > 1 ? sh.getRange(2, 1, sh.getLastRow() - 1, 10).getValues() : [];
  const plain = x => String(x || "").replace(/^'/, "");
  const list = rows.filter(r => r[8] === "Shortlisted").map(r => ({
    brand: plain(r[1]), market: plain(r[2]), sector: plain(r[3]), why: plain(r[4]), headline: plain(r[5]), link: plain(r[6]),
    by: plain(r[7]), at: r[0] instanceof Date ? r[0].toISOString() : ""
  }));
  return ContentService.createTextOutput(JSON.stringify({ brands: list })).setMimeType(ContentService.MimeType.JSON);
}

// Read by GitHub (scripts/prospects.py) and by the site: the names added on the site, plus removal requests
// (names only; the request IDs and codes never leave the Sheet).
function doGet(e) {
  const kind = (e && e.parameter && e.parameter.kind) || "";
  if (kind === "decide") return decidePage(e);
  if (kind === "decidecomment") return decideCommentPage(e);
  if (kind === "comments") return listComments();
  if (kind === "lookups") return listLookups();
  if (kind === "brands") return listBrands();
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
