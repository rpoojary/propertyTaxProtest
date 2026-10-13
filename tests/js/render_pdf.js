// Render letter blocks JSON (stdin) to a PDF file with site/js/pdf.js, for tests/test_static_parity.py.
'use strict';
const fs = require('fs');
const P = require('../../site/js/pdf.js');
const letter = JSON.parse(fs.readFileSync(0, 'utf8'));
fs.writeFileSync(process.argv[2], Buffer.from(P.renderLetter(letter)));
