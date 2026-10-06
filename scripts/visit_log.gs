// 72 Central visit log. Not run by GitHub: paste this into your Google Sheet
// (Extensions > Apps Script) and follow VISIT_LOG.md.
// The site sends each visit here; each visit is one row on the "Visits" tab,
// updated about once a minute while the person has the site on screen.

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
}

// Called by the site. Adds a row for a new visit, or updates the row of a visit already logged.
function doPost(e) {
  let d;
  try { d = JSON.parse(e.postData.contents); } catch (err) { return out("bad"); }
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
