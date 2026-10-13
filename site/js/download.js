// Builds the protest letter PDF in the browser: letter content from
// ProtestEngine.letterBlocks (same blocks as app/letter.py), drawn by
// LetterPdf. Nothing the owner types leaves the browser.
function downloadProtest() {
  var p = window._prop;
  if (!p || !_compsData || !_equity) return;
  var msg = $('downloadMsg');
  var owner = ProtestEngine.cleanOwnerInput({
    owner_name: $('ownerName').value.trim(),
    conditions: getDisclosures(),
    repairs: getRepairItems()
  });
  var letter;
  try {
    letter = ProtestEngine.letterBlocks(_county, p, _equity, _compsData, owner, ProtestEngine.todayText());
  } catch (e) {
    if (!(e instanceof ProtestEngine.NoReduction)) throw e;
    msg.textContent = 'No protest letter: ' + e.message + '.';
    return;
  }
  var blob = new Blob([LetterPdf.renderLetter(letter)], {type: 'application/pdf'});
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = 'Property_Tax_Protest_' + String(p.account).replace(/[^A-Za-z0-9_-]/g, '') + '.pdf';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  msg.textContent = 'Downloaded. Sign it, attach any repair estimates, and file it with your appraisal district.';
}
