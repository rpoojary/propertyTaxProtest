// Builds the downloadable protest letter. Every statement in it is either
// computed from the county roll (appraised values) or entered by the owner
// (name, conditions, repair costs). Uses esc/fmt/num/bathStr/addrOf,
// describeCriteria, compSets, getRepairItems, getDisclosures from index.html.
function downloadProtest() {
  var p = window._prop;
  if (!p || !_compsData) return alert('Please select a property first.');
  var c = _county;

  var val = num(p.appraised_val);
  var sqft = num(p.living_sqft);
  var repairItems = getRepairItems();
  var repairs = getTotalRepairs();
  var disclosures = getDisclosures();
  var sets = compSets();
  var recommended = _baseMedian - repairs;
  var reduction = val - recommended;
  if (!sets.length || reduction <= 0) {
    return alert('The comparable appraised values do not support a lower value for this property.');
  }
  var above = sets.filter(function(s) { return val > s.set.stats.median; });

  var addr = addrOf(p) + ', ' + p.city + ', TX ' + p.zip;
  var owner = $('ownerName').value.trim() || 'Property Owner';
  var today = new Date().toLocaleDateString('en-US', {year: 'numeric', month: 'long', day: 'numeric'});
  var ppsf = sqft > 0 ? fmt(val / sqft) : 'N/A';
  var lot = function(r) { return r.lot_sqft ? Math.round(r.lot_sqft).toLocaleString() : ''; };
  var tableHead = '<table><thead><tr><th>Address</th><th>Deed date</th><th>Appraised</th><th>Bed</th><th>Bath</th>' +
    '<th>Living sq ft</th><th>Lot sq ft</th><th>Year</th><th>$/sq ft</th></tr></thead><tbody>';

  function row(r, cls, label) {
    var v = num(r.appraised_val), sf = num(r.living_sqft);
    return '<tr' + (cls ? ' class="' + cls + '"' : '') + '><td>' + esc(label || r.address) + '</td><td>' + esc(r.deed_date || '') +
      '</td><td>' + fmt(v) + '</td><td>' + esc(r.beds ?? '') + '</td><td>' + esc(bathStr(r.full_baths, r.half_baths)) +
      '</td><td>' + (sf ? sf.toLocaleString() : '') + '</td><td>' + lot(r) + '</td><td>' + esc(r.year_built || '') +
      '</td><td>' + (sf > 0 ? fmt(v / sf) : '') + '</td></tr>';
  }

  function evidence(n, title, set) {
    var s = set.stats;
    var h = '<h2>Evidence ' + n + ': ' + title + '</h2>';
    h += '<p>' + s.count + ' properties on the ' + esc(c.cad_abbrev) + ' ' + c.tax_year + ' roll match: ' +
      esc(describeCriteria(set.criteria)) + '. Their <strong>median appraised value is ' + fmt(s.median) + '</strong>';
    if (val > s.median) h += ', which is <strong>' + fmt(val - s.median) + ' less</strong> than my appraised value of ' + fmt(val);
    h += '. Range: ' + fmt(s.low) + ' to ' + fmt(s.high) + '.</p>';
    if (set.comps && set.comps.length) {
      h += tableHead + row(p, 'subject-row', addrOf(p) + ' (subject)');
      h += set.comps.map(function(r) { return row(r); }).join('');
      h += '</tbody></table>';
      if (set.truncated) h += '<p><em>Table lists the ' + set.comps.length + ' lowest-valued of ' + s.count + ' properties; the median uses all ' + s.count + '.</em></p>';
    }
    return h;
  }

  var h = '<!DOCTYPE html><html><head><meta charset="UTF-8">';
  h += '<title>Property Tax Protest - ' + esc(addr) + '</title>';
  h += '<style>';
  h += 'body{font-family:Georgia,"Times New Roman",serif;max-width:820px;margin:40px auto;padding:0 24px;font-size:14px;line-height:1.7;color:#222}';
  h += 'h1{font-size:24px;text-align:center;border-bottom:3px solid #1a365d;padding-bottom:10px;margin-bottom:6px;color:#1a365d}';
  h += '.subtitle{text-align:center;color:#555;font-size:13px;margin-bottom:24px}';
  h += 'h2{font-size:17px;margin-top:30px;color:#1a365d;border-bottom:1px solid #ccc;padding-bottom:4px}';
  h += 'p{margin:8px 0}';
  h += 'table{border-collapse:collapse;width:100%;margin:12px 0;font-size:12px;font-family:Arial,sans-serif}';
  h += 'th,td{border:1px solid #bbb;padding:6px 8px;text-align:left}';
  h += 'th{background:#e8edf3;font-weight:bold;color:#333}';
  h += 'tr:nth-child(even){background:#f7f9fb}';
  h += '.subject-row{background:#e8f5e9!important;font-weight:700}';
  h += '.info-grid{display:grid;grid-template-columns:1fr 1fr;gap:0;border:1px solid #bbb;margin:12px 0}';
  h += '.info-grid div{padding:8px 12px;border-bottom:1px solid #ddd;font-size:13px}';
  h += '.info-grid .lbl{background:#f0f2f5;font-weight:600;color:#555;border-right:1px solid #ddd}';
  h += '.val-banner{background:#f0fdf4;border:2px solid #059669;border-radius:8px;padding:20px;margin:20px 0;text-align:center}';
  h += '.val-banner .amount{font-size:32px;font-weight:800;color:#059669;font-family:Arial,sans-serif}';
  h += '.val-banner .note{font-size:14px;color:#dc2626;margin-top:4px}';
  h += 'ul,ol{margin:8px 0 8px 20px}li{margin:4px 0}';
  h += '.sig-line{margin-top:50px;border-top:1px solid #333;width:300px;padding-top:4px;font-size:13px}';
  h += '@media print{body{margin:0;font-size:12px}.val-banner{break-inside:avoid}}';
  h += '</style></head><body>';

  h += '<h1>Property Tax Protest</h1>';
  h += '<div class="subtitle">' + c.tax_year + ' Appraisal Year &mdash; ' + esc(c.cad_name) + '<br>' + today + '</div>';

  h += '<p><strong>To:</strong> Appraisal Review Board<br>' + esc(c.cad_name) + '<br>' + esc(c.cad_address) + '</p>';
  h += '<p><strong>From:</strong> ' + esc(owner) + '<br>Re: Account ' + esc(p.account) + ' &mdash; ' + esc(addr) + '</p>';
  h += '<hr style="border:none;border-top:1px solid #ccc;margin:20px 0">';

  h += '<p>Dear Members of the Appraisal Review Board,</p>';
  h += '<p>I am protesting the ' + c.tax_year + ' appraised value of <strong>' + fmt(val) + '</strong> for my property at <strong>' +
    esc(addr) + '</strong> and request that it be reduced to <strong>' + fmt(recommended) + '</strong>.</p>';

  h += '<p>This protest is based on the following grounds:</p><ol>';
  if (above.length) {
    h += '<li><strong>Unequal appraisal</strong> (Texas Tax Code &sect;41.41(a)(2)): my appraised value is higher than the median appraised value of ';
    h += above.map(function(s) { return 'the ' + s.set.stats.count + ' comparable properties in Evidence ' + (sets.indexOf(s) + 1) + ' (' + fmt(s.set.stats.median) + ')'; }).join('; ');
    h += '.</li>';
  }
  if (disclosures.length) h += '<li><strong>Property-specific conditions</strong> that I have documented below.</li>';
  if (repairs > 0) h += '<li><strong>Repair costs</strong> totaling ' + fmt(repairs) + ', based on the estimates listed below.</li>';
  h += '</ol>';

  h += '<h2>Subject Property</h2><div class="info-grid">';
  h += '<div class="lbl">Property address</div><div>' + esc(addr) + '</div>';
  h += '<div class="lbl">Account number</div><div>' + esc(p.account) + '</div>';
  h += '<div class="lbl">Bedrooms / bathrooms</div><div>' + esc(p.beds ?? '—') + ' bed / ' + (p.full_baths == null ? '—' : p.full_baths + ' full, ' + (p.half_baths || 0) + ' half bath') + '</div>';
  h += '<div class="lbl">Living area</div><div>' + (sqft ? sqft.toLocaleString() + ' sq ft' : '—') + '</div>';
  h += '<div class="lbl">Lot size</div><div>' + (p.lot_sqft ? lot(p) + ' sq ft' : '—') + '</div>';
  h += '<div class="lbl">Year built</div><div>' + esc(p.year_built || '—') + '</div>';
  h += '<div class="lbl">Current appraised value</div><div><strong>' + fmt(val) + '</strong> (' + ppsf + '/sq ft)</div>';
  h += '<div class="lbl" style="background:#e8f5e9">Requested value</div><div style="background:#e8f5e9"><strong style="color:#059669">' + fmt(recommended) + '</strong></div>';
  h += '<div class="lbl" style="background:#fef2f2">Reduction requested</div><div style="background:#fef2f2"><strong style="color:#dc2626">' +
    fmt(reduction) + ' (' + (reduction / val * 100).toFixed(1) + '%)</strong></div>';
  h += '</div>';

  h += '<div class="val-banner"><div style="font-size:13px;color:#555;margin-bottom:4px">Opinion of Value</div>';
  h += '<div class="amount">' + fmt(recommended) + '</div>';
  h += '<div class="note">Reduction of ' + fmt(reduction) + ' from the current appraised value of ' + fmt(val) + '</div></div>';

  h += '<p><em>All values below are appraised values from the ' + esc(c.cad_name) + ' ' + c.tax_year +
    ' appraisal roll, not sale prices. A deed date shows when ownership last transferred.</em></p>';
  var titles = {
    neighborhood: 'Recently Sold Properties in My Neighborhood (Appraised Value)',
    zip: 'Similar Recently Sold Properties in My ZIP Code (Appraised Value)',
    all_similar: 'All Similar Properties in My ZIP Code (Appraised Value)'
  };
  sets.forEach(function(s, i) { h += evidence(i + 1, titles[s.key], s.set); });

  if (disclosures.length) {
    h += '<h2>Property-Specific Conditions</h2>';
    h += '<p>I am reporting the following conditions affecting my property:</p><ul>';
    disclosures.forEach(function(d) { h += '<li>' + esc(d) + '</li>'; });
    h += '</ul>';
  }

  if (repairs > 0) {
    h += '<h2>Repair Costs</h2>';
    h += '<p>The following repairs are needed, with estimated costs:</p>';
    h += '<table><thead><tr><th>Description</th><th style="text-align:right">Estimated cost</th></tr></thead><tbody>';
    repairItems.forEach(function(item) {
      h += '<tr><td>' + esc(item.desc) + '</td><td style="text-align:right;color:#dc2626">-' + fmt(item.cost) + '</td></tr>';
    });
    h += '<tr class="subject-row"><td><strong>Total</strong></td><td style="text-align:right"><strong>' + fmt(repairs) + '</strong></td></tr>';
    h += '</tbody></table>';
    h += '<p><em>Estimates and supporting documentation are attached.</em></p>';
  }

  h += '<h2>Summary of Requested Value</h2>';
  h += '<table><thead><tr><th>Basis</th><th style="text-align:right">Value</th></tr></thead><tbody>';
  sets.forEach(function(s, i) {
    h += '<tr><td>Evidence ' + (i + 1) + ': median appraised value (' + s.set.stats.count + ' properties)</td><td style="text-align:right">' + fmt(s.set.stats.median) + '</td></tr>';
  });
  h += '<tr><td>Average of these medians (rounded to $1,000)</td><td style="text-align:right">' + fmt(_baseMedian) + '</td></tr>';
  if (repairs > 0) h += '<tr><td>Less: repair costs</td><td style="text-align:right;color:#dc2626">-' + fmt(repairs) + '</td></tr>';
  h += '<tr class="subject-row"><td><strong>Requested appraised value</strong></td><td style="text-align:right"><strong>' + fmt(recommended) + '</strong></td></tr>';
  h += '</tbody></table>';

  h += '<h2>Conclusion</h2>';
  h += '<p>Based on the evidence above, I respectfully request that the Appraisal Review Board reduce the appraised value of my property from ' +
    fmt(val) + ' to <strong>' + fmt(recommended) + '</strong>.</p>';
  h += '<p>Thank you for your time and consideration.</p>';
  h += '<p style="margin-top:30px">Respectfully submitted,</p>';
  h += '<div class="sig-line">' + esc(owner) + '<br>' + esc(addr) + '</div>';

  h += '<hr style="margin-top:40px;border:none;border-top:1px solid #ccc">';
  h += '<p style="font-size:11px;color:#999;margin-top:8px"><em>Data source: ' + esc(c.cad_name) + ', ' + c.tax_year +
    ' appraisal roll. Generated ' + today + ' with a free self-help tool; not legal or appraisal advice.</em></p>';
  h += '</body></html>';

  var blob = new Blob([h], {type: 'text/html'});
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = 'Property_Tax_Protest_' + String(p.account).replace(/[^A-Za-z0-9_-]/g, '') + '.html';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
