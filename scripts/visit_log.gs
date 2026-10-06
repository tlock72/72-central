/** @OnlyCurrentDoc */
// 72 Central visit log. Not run by GitHub: paste this into your Google Sheet
// (Extensions > Apps Script) and follow VISIT_LOG.md.
// The site sends each visit here; each visit is one row on the "Visits" tab,
// updated about once a minute while the person has the site on screen.
// Scouting Corner's "Add a prospect" box also sends names here (the "Prospects" tab); GitHub reads
// that list (doGet, ?kind=prospects) and links each name to Tennis Europe, the ITF and the ATP/WTA.
// To remove a prospect added on the site, delete their row on the "Prospects" tab.

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
}

// Called by the site. Adds a row for a new visit, or updates the row of a visit already logged.
function doPost(e) {
  let d;
  try { d = JSON.parse(e.postData.contents); } catch (err) { return out("bad"); }
  if (d.kind === "prospect") return addProspect(d);
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

// Read by GitHub (scripts/prospects.py) and by the site: the names added on the site.
function doGet(e) {
  const kind = (e && e.parameter && e.parameter.kind) || "";
  if (kind !== "prospects") return out("72 Central");
  const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Prospects");
  const rows = sh && sh.getLastRow() > 1 ? sh.getRange(2, 1, sh.getLastRow() - 1, 6).getValues() : [];
  const list = rows.filter(r => String(r[1]).trim()).map(r => ({
    name: String(r[1]).replace(/^'/, "").trim(), g: { Boy: "M", Girl: "F" }[r[2]] || "", nat: String(r[3] || ""),
    born: r[4] ? Number(r[4]) : null, by: String(r[5] || "").replace(/^'/, ""),
    at: r[0] instanceof Date ? Utilities.formatDate(r[0], TZ, "yyyy-MM-dd") : ""
  }));
  return ContentService.createTextOutput(JSON.stringify({ prospects: list })).setMimeType(ContentService.MimeType.JSON);
}
