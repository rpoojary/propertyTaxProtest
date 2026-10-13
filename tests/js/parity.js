// Run the static-site engine in Node for tests/test_static_parity.py.
// usage: node parity.js <dataDir> <county> <taxYear> <todayText> <ownerJSON> <account>...
'use strict';
const fs = require('fs');
const path = require('path');
const E = require('../../site/js/engine.js');

const [dataDir, countyId, taxYear, today, ownerJson, ...accounts] = process.argv.slice(2);
const fetchJSON = (p) => Promise.resolve(JSON.parse(fs.readFileSync(path.join(dataDir, p), 'utf8')));

(async () => {
  const county = await new E.County(countyId, fetchJSON).init();
  const cfg = county.meta.county;
  const owner = E.cleanOwnerInput(JSON.parse(ownerJson));
  const out = {};
  for (const account of accounts) {
    const area = Object.keys(county.meta.areas).sort();
    let subject = null;
    for (const a of area) {
      subject = await county.property(account, a);
      if (subject) break;
    }
    if (!subject) { out[account] = { missing: true }; continue; }
    const comps = await county.findComps(subject, Number(taxYear));
    const equity = await county.equity(subject);
    let letter;
    try {
      letter = E.letterBlocks(cfg, subject, equity, comps, owner, today);
    } catch (e) {
      if (!(e instanceof E.NoReduction)) throw e;
      letter = { error: e.message };
    }
    out[account] = { comps, equity, letter };
  }
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
