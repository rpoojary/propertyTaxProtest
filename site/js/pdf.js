// Minimal PDF writer for the protest letter, no dependencies.
//
// Renders the renderer-neutral blocks from engine.js letterBlocks() (the same
// blocks app/letter.py hands to reportlab) on US Letter pages with the
// standard Times and Helvetica fonts. Text is WinAnsi-encoded; characters the
// standard fonts cannot show are replaced with '?'.
(function (root) {
  'use strict';

  var W = typeof module !== 'undefined' && module.exports ? require('./pdf-fonts.js') : root.PdfFontWidths;

  var PAGE_W = 612, PAGE_H = 792, MARGIN = 50.4, CONTENT_W = PAGE_W - 2 * MARGIN;
  var FONTS = { 'Times-Roman': 'F1', 'Times-Bold': 'F2', 'Helvetica': 'F3', 'Helvetica-Bold': 'F4' };
  var STYLES = {
    title: { font: 'Times-Bold', size: 17, leading: 21, before: 0, after: 6, align: 'center' },
    small: { font: 'Times-Roman', size: 8, leading: 10, before: 6, color: [0.333, 0.333, 0.333] },
    h2: { font: 'Times-Bold', size: 12, leading: 14.4, before: 10, after: 6 },
    p: { font: 'Times-Roman', bold: 'Times-Bold', size: 10.5, leading: 14, before: 6 }
  };
  var CELL = { font: 'Helvetica', bold: 'Helvetica-Bold', size: 7, leading: 8.5, padX: 6, padY: 3 };
  var GRID = [0.6, 0.6, 0.6], HEADER_BG = [0.91, 0.929, 0.953], HIGHLIGHT_BG = [0.91, 0.961, 0.914];

  // Unicode -> WinAnsi (cp1252) for the 0x80-0x9F block; 0xA0-0xFF match Latin-1.
  var CP1252 = { 0x20AC: 0x80, 0x201A: 0x82, 0x0192: 0x83, 0x201E: 0x84, 0x2026: 0x85, 0x2020: 0x86, 0x2021: 0x87,
    0x02C6: 0x88, 0x2030: 0x89, 0x0160: 0x8A, 0x2039: 0x8B, 0x0152: 0x8C, 0x017D: 0x8E, 0x2018: 0x91, 0x2019: 0x92,
    0x201C: 0x93, 0x201D: 0x94, 0x2022: 0x95, 0x2013: 0x96, 0x2014: 0x97, 0x02DC: 0x98, 0x2122: 0x99, 0x0161: 0x9A,
    0x203A: 0x9B, 0x0153: 0x9C, 0x017E: 0x9E, 0x0178: 0x9F };

  function encode(text) {
    var out = '';
    for (var i = 0; i < text.length; i++) {
      var c = text.charCodeAt(i);
      if (c >= 0xD800 && c <= 0xDBFF) { i++; out += '?'; continue; }  // astral (emoji etc.)
      if (c >= 32 && c < 127) out += text[i];
      else if (c >= 160 && c <= 255) out += String.fromCharCode(c);
      else if (CP1252[c]) out += String.fromCharCode(CP1252[c]);
      else out += c === 9 ? ' ' : '?';
    }
    return out;
  }

  function width(encoded, font, size) {
    var w = 0, table = W[font];
    for (var i = 0; i < encoded.length; i++) {
      var c = encoded.charCodeAt(i);
      w += c >= 32 ? table[c - 32] : 0;
    }
    return w * size / 1000;
  }

  function pdfString(encoded) { return '(' + encoded.replace(/[\\()]/g, '\\$&') + ')'; }
  function num(v) { return (Math.round(v * 100) / 100).toString(); }
  function rgb(c) { return c.map(num).join(' '); }

  // Word-wrap runs [[text, bold], ...] into lines of [{text, font}] pieces.
  function wrap(runs, maxW, regular, bold, size) {
    var lines = [[]], lineW = 0;
    function push(text, font) {
      var cur = lines[lines.length - 1], last = cur[cur.length - 1];
      if (last && last.font === font) last.text += text; else cur.push({ text: text, font: font });
      lineW += width(text, font, size);
    }
    runs.forEach(function (run) {
      var font = run[1] ? bold : regular;
      String(run[0]).split('\n').map(encode).forEach(function (segment, si) {
        if (si > 0) { lines.push([]); lineW = 0; }
        segment.split(/( +)/).forEach(function (tok) {
          if (!tok) return;
          var w = width(tok, font, size);
          if (/^ +$/.test(tok)) { if (lineW > 0) push(tok, font); return; }
          if (lineW > 0 && lineW + w > maxW) {
            var cur = lines[lines.length - 1];  // drop trailing spaces before breaking
            while (cur.length) {
              var lastPiece = cur[cur.length - 1];
              lastPiece.text = lastPiece.text.replace(/ +$/, '');
              if (lastPiece.text) break;
              cur.pop();
            }
            lines.push([]); lineW = 0;
          }
          while (w > maxW && tok.length > 1) {  // a single word wider than the line
            var n = tok.length;
            while (n > 1 && width(tok.slice(0, n), font, size) > maxW) n--;
            push(tok.slice(0, n), font); lines.push([]); lineW = 0;
            tok = tok.slice(n); w = width(tok, font, size);
          }
          push(tok, font);
        });
      });
    });
    return lines;
  }

  function lineWidth(line, size) {
    return line.reduce(function (t, piece) { return t + width(piece.text, piece.font, size); }, 0);
  }

  function Doc() {
    this.pages = [];
    this.newPage();
  }

  Doc.prototype.newPage = function () {
    this.ops = [];
    this.pages.push(this.ops);
    this.y = PAGE_H - MARGIN;
  };

  Doc.prototype.ensure = function (h) {
    if (this.y - h < MARGIN) { this.newPage(); return true; }
    return false;
  };

  Doc.prototype.text = function (line, x, y, size, color) {
    var ops = this.ops, cx = x;
    if (color) ops.push(rgb(color) + ' rg');
    line.forEach(function (piece) {
      ops.push('BT /' + FONTS[piece.font] + ' ' + num(size) + ' Tf ' + num(cx) + ' ' + num(y) + ' Td ' + pdfString(piece.text) + ' Tj ET');
      cx += width(piece.text, piece.font, size);
    });
    if (color) ops.push('0 0 0 rg');
  };

  Doc.prototype.paragraph = function (runs, style) {
    var lines = wrap(runs, CONTENT_W, style.font, style.bold || style.font, style.size);
    this.y -= style.before || 0;
    for (var i = 0; i < lines.length; i++) {
      this.ensure(style.leading);
      this.y -= style.leading;
      var x = MARGIN;
      if (style.align === 'center') x = MARGIN + (CONTENT_W - lineWidth(lines[i], style.size)) / 2;
      this.text(lines[i], x, this.y + style.leading * 0.25, style.size, style.color);
    }
    this.y -= style.after || 0;
  };

  Doc.prototype.table = function (block) {
    var self = this, widths = block.widths.map(function (w) { return w * 72; });
    var totalW = widths.reduce(function (a, b) { return a + b; }, 0), x0 = MARGIN + (CONTENT_W - totalW) / 2;
    var hl = block.highlight || [];
    var laid = block.rows.map(function (row, ri) {
      var bold = hl.indexOf(ri) >= 0;
      var cells = row.map(function (text, ci) {
        return wrap([[String(text), bold]], widths[ci] - 2 * CELL.padX, CELL.font, CELL.bold, CELL.size);
      });
      var lines = Math.max.apply(null, cells.map(function (c) { return c.length; }));
      return { cells: cells, h: lines * CELL.leading + 2 * CELL.padY, bg: ri === 0 ? HEADER_BG : bold ? HIGHLIGHT_BG : null };
    });
    this.y -= 6;
    var drawRow = function (r) {
      var top = self.y, ops = self.ops, cx = x0;
      if (r.bg) ops.push(rgb(r.bg) + ' rg ' + num(x0) + ' ' + num(top - r.h) + ' ' + num(totalW) + ' ' + num(r.h) + ' re f 0 0 0 rg');
      r.cells.forEach(function (lines, ci) {
        lines.forEach(function (line, li) {
          self.text(line, cx + CELL.padX, top - CELL.padY - (li + 1) * CELL.leading + CELL.leading * 0.22, CELL.size);
        });
        cx += widths[ci];
      });
      ops.push(rgb(GRID) + ' RG 0.4 w');
      ops.push(num(x0) + ' ' + num(top) + ' m ' + num(x0 + totalW) + ' ' + num(top) + ' l S');
      ops.push(num(x0) + ' ' + num(top - r.h) + ' m ' + num(x0 + totalW) + ' ' + num(top - r.h) + ' l S');
      var vx = x0;
      ops.push(num(vx) + ' ' + num(top) + ' m ' + num(vx) + ' ' + num(top - r.h) + ' l S');
      widths.forEach(function (w) {
        vx += w;
        ops.push(num(vx) + ' ' + num(top) + ' m ' + num(vx) + ' ' + num(top - r.h) + ' l S');
      });
      ops.push('0 0 0 RG');
      self.y -= r.h;
    };
    laid.forEach(function (r, i) {
      if (self.ensure(r.h) && i > 0) drawRow(laid[0]);  // repeat the header row on a new page
      drawRow(r);
    });
  };

  Doc.prototype.render = function (blocks) {
    var self = this;
    blocks.forEach(function (b) {
      if (b.t === 'p') self.paragraph(b.runs, STYLES.p);
      else if (STYLES[b.t]) self.paragraph([[b.text, false]], STYLES[b.t]);
      else if (b.t === 'space') self.y -= b.h;
      else if (b.t === 'table') self.table(b);
      else throw new Error('unknown block type ' + b.t);
    });
    return this;
  };

  Doc.prototype.bytes = function (info) {
    var objs = [];  // object bodies, numbered from 1
    function add(body) { objs.push(body); return objs.length; }
    var catalog = add(null), pagesObj = add(null), fontIds = {};
    Object.keys(FONTS).forEach(function (name) {
      fontIds[FONTS[name]] = add('<< /Type /Font /Subtype /Type1 /BaseFont /' + name + ' /Encoding /WinAnsiEncoding >>');
    });
    var fontDict = '<< ' + Object.keys(fontIds).map(function (k) { return '/' + k + ' ' + fontIds[k] + ' 0 R'; }).join(' ') + ' >>';
    var kids = this.pages.map(function (ops) {
      var stream = ops.join('\n');
      var content = add('<< /Length ' + stream.length + ' >>\nstream\n' + stream + '\nendstream');
      return add('<< /Type /Page /Parent ' + pagesObj + ' 0 R /MediaBox [0 0 ' + PAGE_W + ' ' + PAGE_H + '] /Resources << /Font ' +
                 fontDict + ' >> /Contents ' + content + ' 0 R >>');
    });
    objs[catalog - 1] = '<< /Type /Catalog /Pages ' + pagesObj + ' 0 R >>';
    objs[pagesObj - 1] = '<< /Type /Pages /Kids [' + kids.map(function (k) { return k + ' 0 R'; }).join(' ') + '] /Count ' + kids.length + ' >>';
    var infoObj = add('<< /Title ' + pdfString(encode(info.title || '')) + ' /Author ' + pdfString(encode(info.author || '')) +
                      ' /Producer (Texas Property Tax Protest Helper) >>');
    var out = '%PDF-1.4\n%\xE2\xE3\xCF\xD3\n', offsets = [];
    objs.forEach(function (body, i) {
      offsets.push(out.length);
      out += (i + 1) + ' 0 obj\n' + body + '\nendobj\n';
    });
    var xref = out.length;
    out += 'xref\n0 ' + (objs.length + 1) + '\n0000000000 65535 f \n';
    offsets.forEach(function (o) { out += String(o).padStart(10, '0') + ' 00000 n \n'; });
    out += 'trailer\n<< /Size ' + (objs.length + 1) + ' /Root ' + catalog + ' 0 R /Info ' + infoObj + ' 0 R >>\nstartxref\n' + xref + '\n%%EOF\n';
    var bytes = new Uint8Array(out.length);
    for (var i = 0; i < out.length; i++) bytes[i] = out.charCodeAt(i) & 0xFF;
    return bytes;
  };

  // letter: {blocks, address, owner_name} from engine.letterBlocks(). Returns PDF bytes.
  function renderLetter(letter) {
    return new Doc().render(letter.blocks).bytes({ title: 'Property Tax Protest - ' + letter.address, author: letter.owner_name });
  }

  var api = { renderLetter: renderLetter, encode: encode, width: width, wrap: wrap };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.LetterPdf = api;
})(this);
