// Downloads the protest letter PDF. The server builds it from the county data
// (app/letter.py); the browser only sends what the owner typed.
function downloadProtest() {
  var p = window._prop;
  if (!p || !_compsData) return;
  var btn = $('downloadBtn'), msg = $('downloadMsg');
  var body = {
    owner_name: $('ownerName').value.trim(),
    conditions: getDisclosures(),
    repairs: getRepairItems()
  };
  btn.disabled = true;
  msg.textContent = 'Preparing your letter…';
  fetch('/api/' + encodeURIComponent(_county.id) + '/letter/' + encodeURIComponent(p.account), {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  }).then(function(r) {
    if (!r.ok) return r.json().then(function(j) { throw new Error(j.error || 'The letter could not be created.'); });
    return r.blob();
  }).then(function(blob) {
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'Property_Tax_Protest_' + String(p.account).replace(/[^A-Za-z0-9_-]/g, '') + '.pdf';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    msg.textContent = 'Downloaded. Sign it, attach any repair estimates, and file it with your appraisal district.';
  }).catch(function(err) {
    msg.textContent = err.message;
  }).then(function() {
    btn.disabled = false;
  });
}
