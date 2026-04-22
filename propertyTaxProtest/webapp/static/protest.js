function downloadProtest() {
  var p = window._prop;
  if (!p || !_compsData) return alert('Please select a property first.');

  var val = parseFloat(p.TOT_VAL);
  var sqft = parseFloat(p.TOT_LIVING_AREA_SF) || 0;
  var fb = parseInt(p.NUM_FULL_BATHS) || 0;
  var hb = parseInt(p.NUM_HALF_BATHS) || 0;
  var bath = hb > 0 ? fb + ' full, ' + hb + ' half' : fb + ' full';
  var repairs = getTotalRepairs();
  var disclosures = getDisclosures();
  var recommended = _baseMedian - repairs;
  var reduction = val - recommended;
  var addr = p.STREET_NUM + ' ' + p.FULL_STREET_NAME + ', ' + p.PROPERTY_CITY + ', TX ' + p.ZIP;
  var owner = p.OWNER_NAME1 || 'Property Owner';
  var today = new Date().toLocaleDateString('en-US', {year:'numeric', month:'long', day:'numeric'});
  var ppsf = sqft > 0 ? fmt(val / sqft) : 'N/A';
  var nbhd = _compsData.neighborhood_stats;
  var zs = _compsData.zip_stats;
  var als = _compsData.all_similar_stats;

  function compRows(comps) {
    return comps.map(function(r) {
      var v = parseFloat(r.TOT_VAL);
      var sf = parseFloat(r.TOT_LIVING_AREA_SF) || 0;
      var cfb = parseInt(r.NUM_FULL_BATHS) || 0;
      var chb = parseInt(r.NUM_HALF_BATHS) || 0;
      var cb = chb > 0 ? cfb + '/' + chb : String(cfb);
      return '<tr><td>' + (r.ADDRESS||'') + '</td><td>' + (r.DEED_TXFR_DATE||'') +
        '</td><td>' + fmt(v) + '</td><td>' + (r.NUM_BEDROOMS||'') + '</td><td>' + cb +
        '</td><td>' + (sf ? sf.toLocaleString() : '') + '</td><td>' +
        (r.AREA_SIZE ? parseInt(r.AREA_SIZE).toLocaleString() : '') + '</td><td>' +
        (r.YR_BUILT||'') + '</td><td>' + (sf > 0 ? fmt(v/sf) : '') + '</td></tr>';
    }).join('');
  }

  var repairItems = [];
  document.querySelectorAll('.repair-row').forEach(function(row) {
    var desc = row.querySelector('.repair-desc').value || 'Repair';
    var cost = parseFloat(row.querySelector('.repair-cost').value) || 0;
    if (cost > 0) repairItems.push({desc: desc, cost: cost});
  });

  // --- Build the document ---
  var h = '<!DOCTYPE html><html><head><meta charset="UTF-8">';
  h += '<title>Property Tax Protest - ' + addr + '</title>';
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
  h += '.narrative{background:#fefce8;border-left:4px solid #f59e0b;padding:12px 16px;margin:16px 0;font-style:italic;color:#555}';
  h += 'ul{margin:8px 0 8px 20px}li{margin:4px 0}';
  h += '.sig-line{margin-top:50px;border-top:1px solid #333;width:300px;padding-top:4px;font-size:13px}';
  h += '@media print{body{margin:0;font-size:12px}.val-banner{break-inside:avoid}}';
  h += '</style></head><body>';

  // Header
  h += '<h1>Property Tax Protest</h1>';
  h += '<div class="subtitle">2026 Appraisal Year &mdash; Dallas County Appraisal District<br>' + today + '</div>';

  // Addressed to
  h += '<p><strong>To:</strong> Dallas County Appraisal Review Board<br>';
  h += 'Dallas County Appraisal District<br>';
  h += '2949 N. Stemmons Freeway, Dallas, TX 75247</p>';

  h += '<p><strong>From:</strong> ' + owner + '<br>';
  h += 'Re: Account ' + p.ACCOUNT_NUM + ' &mdash; ' + addr + '</p>';

  h += '<hr style="border:none;border-top:1px solid #ccc;margin:20px 0">';

  // Opening statement
  h += '<p>Dear Members of the Appraisal Review Board,</p>';
  h += '<p>I am writing to formally protest the 2026 appraised value of <strong>' + fmt(val) + '</strong> ';
  h += 'for my property at <strong>' + addr + '</strong>. After careful review of comparable sales ';
  h += 'in my neighborhood and zip code, along with property-specific conditions documented below, ';
  h += 'I respectfully request that the appraised value be reduced to <strong>' + fmt(recommended) + '</strong>.</p>';

  // Basis
  h += '<p>This protest is based on the following grounds:</p>';
  h += '<ol>';
  h += '<li><strong>The appraised value exceeds market value</strong> as demonstrated by comparable recent sales in my neighborhood and zip code</li>';
  h += '<li><strong>The appraisal is unequal</strong> compared to similar properties &mdash; my property carries the highest $/sqft despite having one of the smallest lots</li>';
  if (disclosures.length > 0) h += '<li><strong>Property-specific conditions</strong> including documented issues and external factors that negatively affect value</li>';
  if (repairs > 0) h += '<li><strong>Verified repair costs</strong> totaling ' + fmt(repairs) + ' that reduce the effective market value</li>';
  h += '</ol>';

  // Property info grid
  h += '<h2>Subject Property</h2>';
  h += '<div class="info-grid">';
  h += '<div class="lbl">Property Address</div><div>' + addr + '</div>';
  h += '<div class="lbl">Account Number</div><div>' + p.ACCOUNT_NUM + '</div>';
  h += '<div class="lbl">Owner</div><div>' + owner + '</div>';
  h += '<div class="lbl">Bedrooms / Bathrooms</div><div>' + (p.NUM_BEDROOMS||'—') + ' bed / ' + bath + '</div>';
  h += '<div class="lbl">Living Area</div><div>' + (sqft ? sqft.toLocaleString() + ' sq ft' : '—') + '</div>';
  h += '<div class="lbl">Lot Size</div><div>' + (p.AREA_SIZE ? parseInt(p.AREA_SIZE).toLocaleString() + ' sq ft' : '—') + '</div>';
  h += '<div class="lbl">Year Built</div><div>' + (p.YR_BUILT||'—') + '</div>';
  h += '<div class="lbl">Current Appraisal</div><div><strong>' + fmt(val) + '</strong> (' + ppsf + '/sqft)</div>';
  h += '<div class="lbl" style="background:#e8f5e9">Requested Value</div><div style="background:#e8f5e9"><strong style="color:#059669">' + fmt(recommended) + '</strong></div>';
  h += '<div class="lbl" style="background:#fef2f2">Reduction Requested</div><div style="background:#fef2f2"><strong style="color:#dc2626">' + fmt(reduction) + ' (' + (reduction/val*100).toFixed(1) + '%)</strong></div>';
  h += '</div>';

  // Value banner
  h += '<div class="val-banner">';
  h += '<div style="font-size:13px;color:#555;margin-bottom:4px">Opinion of Value</div>';
  h += '<div class="amount">' + fmt(recommended) + '</div>';
  h += '<div class="note">Reduction of ' + fmt(reduction) + ' from current appraisal of ' + fmt(val) + '</div>';
  h += '</div>';

  // Evidence 1: Neighborhood
  if (_compsData.neighborhood_comps.length > 0) {
    h += '<h2>Evidence 1: Neighborhood Comparable Sales</h2>';
    h += '<p>The following ' + nbhd.count + ' properties in my immediate neighborhood (code ' + p.NBHD_CD + ') ';
    h += 'sold within the last 12 months. The <strong>median appraised value is ' + fmt(nbhd.median) + '</strong>';
    if (val > nbhd.median) {
      h += ', which is <strong>' + fmt(val - nbhd.median) + ' below</strong> my current appraisal';
    }
    h += '.</p>';
    h += '<table><thead><tr><th>Address</th><th>Sold Date</th><th>Appraised</th><th>Bed</th><th>Bath</th><th>SqFt</th><th>Lot</th><th>Year</th><th>$/SqFt</th></tr></thead><tbody>';
    h += '<tr class="subject-row"><td>' + p.STREET_NUM + ' ' + p.FULL_STREET_NAME + ' (subject)</td><td>&mdash;</td><td>' + fmt(val) + '</td><td>' + (p.NUM_BEDROOMS||'') + '</td><td>' + (fb + '/' + hb) + '</td><td>' + (sqft?sqft.toLocaleString():'') + '</td><td>' + (p.AREA_SIZE?parseInt(p.AREA_SIZE).toLocaleString():'') + '</td><td>' + (p.YR_BUILT||'') + '</td><td>' + ppsf + '</td></tr>';
    h += compRows(_compsData.neighborhood_comps);
    h += '</tbody></table>';
    h += '<div class="narrative">My property carries the highest price per square foot among all neighborhood comps, ';
    h += 'despite having one of the smallest lots. Properties with larger lots and comparable features ';
    h += 'are consistently appraised lower.</div>';
  }

  // Evidence 2: Zip comps
  if (_compsData.zip_comps.length > 0) {
    h += '<h2>Evidence 2: ZIP Code Comparable Sales &mdash; Similar Specifications</h2>';
    h += '<p>Expanding the search to all of ZIP ' + p.ZIP + ', I identified <strong>' + zs.count + ' properties</strong> ';
    h += 'with similar specifications that sold in the last 12 months. ';
    h += 'The <strong>median appraised value is ' + fmt(zs.median) + '</strong>';
    if (val > zs.median) {
      h += ' &mdash; my property is <strong>' + fmt(val - zs.median) + ' above this median</strong>';
    }
    h += '.</p>';
    h += '<table><thead><tr><th>Address</th><th>Sold Date</th><th>Appraised</th><th>Bed</th><th>Bath</th><th>SqFt</th><th>Lot</th><th>Year</th><th>$/SqFt</th></tr></thead><tbody>';
    h += compRows(_compsData.zip_comps);
    h += '</tbody></table>';
  }

  // Evidence 3: All similar
  if (als.count > 0) {
    h += '<h2>Evidence 3: All Similar Properties in ZIP (Current Appraisals)</h2>';
    h += '<p>Looking beyond just recent sales, there are <strong>' + als.count + ' properties</strong> in ZIP ' + p.ZIP;
    h += ' with matching specifications currently on the DCAD rolls. ';
    h += 'The median appraisal is <strong>' + fmt(als.median) + '</strong>, ';
    h += 'with a range of ' + fmt(als.low) + ' to ' + fmt(als.high) + '.</p>';
  }

  // Disclosures
  if (disclosures.length > 0) {
    h += '<h2>Property-Specific Conditions Affecting Value</h2>';
    h += '<p>The following conditions apply to my property and are not adequately reflected in the current appraisal:</p>';
    h += '<ul>';
    disclosures.forEach(function(d) { h += '<li>' + d + '</li>'; });
    h += '</ul>';
    h += '<p>These factors reduce the desirability and effective market value of the property ';
    h += 'relative to comparable homes that do not share these conditions.</p>';
  }

  // Repair costs
  if (repairs > 0) {
    h += '<h2>Documented Repair Costs</h2>';
    h += '<p>The following repair needs have been identified and estimated. These costs represent ';
    h += 'a direct reduction in the property\'s effective market value:</p>';
    h += '<table><thead><tr><th>Description</th><th style="text-align:right">Estimated Cost</th></tr></thead><tbody>';
    repairItems.forEach(function(item) {
      h += '<tr><td>' + item.desc + '</td><td style="text-align:right;color:#dc2626">-' + fmt(item.cost) + '</td></tr>';
    });
    h += '<tr class="subject-row"><td><strong>Total Repair Deductions</strong></td><td style="text-align:right"><strong>' + fmt(repairs) + '</strong></td></tr>';
    h += '</tbody></table>';
    h += '<p><em>Supporting estimates and documentation are available upon request.</em></p>';
  }

  // Value summary
  h += '<h2>Summary of Requested Value</h2>';
  h += '<table><thead><tr><th>Method</th><th style="text-align:right">Indicated Value</th></tr></thead><tbody>';
  if (nbhd.count > 0) h += '<tr><td>Neighborhood comp median (' + nbhd.count + ' sales)</td><td style="text-align:right">' + fmt(nbhd.median) + '</td></tr>';
  if (zs.count > 0) h += '<tr><td>ZIP ' + p.ZIP + ' comp median (' + zs.count + ' similar sales)</td><td style="text-align:right">' + fmt(zs.median) + '</td></tr>';
  if (als.count > 0) h += '<tr><td>All similar properties median (' + als.count + ' properties)</td><td style="text-align:right">' + fmt(als.median) + '</td></tr>';
  h += '<tr><td>Average of comp medians</td><td style="text-align:right">' + fmt(_baseMedian) + '</td></tr>';
  if (repairs > 0) h += '<tr><td>Less: documented repair costs</td><td style="text-align:right;color:#dc2626">-' + fmt(repairs) + '</td></tr>';
  h += '<tr class="subject-row"><td><strong>Requested Appraised Value</strong></td><td style="text-align:right"><strong>' + fmt(recommended) + '</strong></td></tr>';
  h += '</tbody></table>';

  // Closing
  h += '<h2>Conclusion</h2>';
  h += '<p>Based on the comparable sales evidence, property-specific conditions, ';
  if (repairs > 0) h += 'documented repair costs, ';
  h += 'and the analysis presented above, I respectfully request that the Appraisal Review Board ';
  h += 'reduce the appraised value of my property from ' + fmt(val) + ' to <strong>' + fmt(recommended) + '</strong>.</p>';
  h += '<p>I appreciate the Board\'s time and consideration in reviewing this protest. I am available ';
  h += 'to provide additional documentation or answer any questions.</p>';

  h += '<p style="margin-top:30px">Respectfully submitted,</p>';
  h += '<div class="sig-line">' + owner + '<br>' + addr + '</div>';

  h += '<hr style="margin-top:40px;border:none;border-top:1px solid #ccc">';
  h += '<p style="font-size:11px;color:#999;margin-top:8px"><em>Data source: Dallas County Appraisal District &mdash; 2026 Certified Values. ';
  h += 'Generated ' + today + '. This document was prepared for the Appraisal Review Board of Dallas County.</em></p>';
  h += '</body></html>';

  // Download
  var blob = new Blob([h], {type: 'text/html'});
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = 'Property_Tax_Protest_' + p.ACCOUNT_NUM + '.html';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
