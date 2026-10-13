// In-browser protest engine for the static site.
//
// Mirrors app/comps.py (comparison sets), app/equity.py (adjusted equity
// analysis) and app/letter.py (letter blocks) on the JSON written by
// pipeline/export_static.py. tests/test_static_parity.py runs this file in
// Node and requires identical results to the Python code, so keep the two in
// step: same filters, same arithmetic order, Python's rounding (round half to
// even) and Python's number formatting.
(function (root) {
  'use strict';

  // ---- Python-compatible numbers -------------------------------------------------

  // Python round(x, nd) / f"{x:.{nd}f}": round half to even on the exact decimal value of
  // the double. toPrecision(100) prints that exact value for the magnitudes used here.
  function roundDecimal(x, nd) {
    var exact = Math.abs(x).toPrecision(100);
    if (exact.indexOf('e') >= 0) return (x < 0 ? '-' : '') + Math.abs(x).toFixed(nd);
    var parts = exact.split('.'), whole = parts[0], frac = (parts[1] || '').padEnd(nd + 1, '0');
    var kept = frac.slice(0, nd), next = frac.charAt(nd), rest = frac.slice(nd + 1);
    var digits = BigInt(whole + kept);
    var lastOdd = Number(digits % 2n) === 1;
    if (next > '5' || (next === '5' && (/[1-9]/.test(rest) || lastOdd))) digits += 1n;
    var s = digits.toString().padStart(nd + 1, '0');
    var out = nd ? s.slice(0, s.length - nd) + '.' + s.slice(s.length - nd) : s;
    return (x < 0 && /[1-9]/.test(out) ? '-' : '') + out;
  }

  function pyRound(x, nd) {
    var r = Number(roundDecimal(x, nd || 0));
    return r === 0 ? 0 : r;  // no negative zero
  }

  function commas(n) {
    var s = String(Math.abs(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return n < 0 ? '-' + s : s;
  }

  var fmt = {
    money: function (v) { return '$' + commas(pyRound(v)); },          // f"${v:,.0f}"
    int: function (v) { return commas(pyRound(v)); },                  // f"{v:,.0f}" / f"{v:,}"
    signed: function (v) { return (v >= 0 ? '+' : '-') + commas(Math.abs(v)); },  // f"{v:+,}"
    fixed: function (v, nd) { return roundDecimal(v, nd); },            // f"{v:.Nf}"
    g: function (v) { return String(v); }                              // f"{v:g}" for 0.5, 1.0, 2.0
  };

  // ---- shared helpers (app/stats.py) ---------------------------------------------

  function median(values) {
    var v = values.slice().sort(function (a, b) { return a - b; }), n = v.length;
    if (!n) return null;
    var mid = Math.floor(n / 2);
    return n % 2 ? v[mid] : (v[mid - 1] + v[mid]) / 2;
  }

  function summarize(values) {
    var vals = values.filter(function (v) { return v != null; });
    if (!vals.length) return { count: 0 };
    var sum = 0;
    vals.forEach(function (v) { sum += v; });
    return { count: vals.length, median: median(vals), average: sum / vals.length,
             low: Math.min.apply(null, vals), high: Math.max.apply(null, vals) };
  }

  function between(v, lo, hi) { return v != null && v >= lo && v <= hi; }
  function category(p) { return (p.state_cd || '').slice(0, 1); }
  function address(p) { return p.street_num == null || p.street_name == null ? null : p.street_num + ' ' + p.street_name; }
  function byValueThenAccount(a, b) {
    return a.appraised_val - b.appraised_val || (a.account < b.account ? -1 : a.account > b.account ? 1 : 0);
  }

  // ---- data access ---------------------------------------------------------------

  // fetchJSON(path) -> Promise of parsed JSON; paths are relative to the data root.
  function County(id, fetchJSON) {
    this.id = id;
    this.fetchJSON = fetchJSON;
    this.areaCache = {};
  }

  County.prototype.init = function () {
    var self = this;
    return this.fetchJSON(this.id + '/meta.json').then(function (meta) { self.meta = meta; return self; });
  };

  County.prototype.area = function (areaId) {
    var self = this;
    if (!this.areaCache[areaId]) {
      this.areaCache[areaId] = this.fetchJSON(this.id + '/areas/' + areaId + '.json').then(function (rows) {
        var F = self.meta.fields, cities = self.meta.cities;
        return rows.map(function (r) {
          var o = {};
          for (var i = 0; i < F.length; i++) o[F[i]] = r[i];
          o.city = cities[o.city];
          o.homestead = !!o.homestead;
          o.area = areaId;
          return o;
        });
      });
    }
    return this.areaCache[areaId];
  };

  County.prototype.areas = function (ids) {
    var self = this;
    return Promise.all(ids.map(function (a) { return self.area(a); })).then(function (lists) {
      return [].concat.apply([], lists);
    });
  };

  County.prototype.property = function (account, areaId) {
    return this.area(areaId).then(function (rows) {
      return rows.find(function (r) { return r.account === account; }) || null;
    });
  };

  // Areas whose bounding box overlaps [lat0, lon0, lat1, lon1].
  County.prototype.areasInBox = function (lat0, lon0, lat1, lon1) {
    var idx = this.meta.areas;
    return Object.keys(idx).filter(function (a) {
      var b = idx[a].bbox;
      return b && b[0] <= lat1 && b[2] >= lat0 && b[1] <= lon1 && b[3] >= lon0;
    }).sort();
  };

  County.prototype.nbhdAreas = function (nbhd) { return (this.meta.nbhd_areas[nbhd] || []).slice(); };

  // ---- search (word-prefix shards; see pipeline/export_static.py) ----------------

  County.prototype.searchKey = function (word) {
    var w = word.toUpperCase().replace(/[^A-Z0-9]/g, '');
    if (w.length < 2 || this.meta.skip_words.indexOf(w) >= 0 || /^\d+$/.test(w)) return null;
    return w.slice(0, 2);
  };

  County.prototype.search = function (q, limit) {
    var self = this, SF = this.meta.search_fields, cities = this.meta.cities;
    q = (q || '').trim().toUpperCase().replace(/\s+/g, ' ');
    limit = limit || 20;
    if (q.length < 3) return Promise.resolve([]);
    var parts = q.split(' '), num = /^\d+[A-Z]?$/.test(parts[0]) && parts.length > 1 ? parts[0] : null;
    var rest = num ? parts.slice(1).join(' ') : q;
    var key = null, words = rest.split(' ');
    for (var i = 0; i < words.length && !key; i++) key = self.searchKey(words[i]);
    var looksLikeAccount = /\d/.test(q) && q.indexOf(' ') < 0;
    var path = looksLikeAccount
      ? this.id + '/accounts/' + (q.replace(/[^A-Z0-9]/g, '').replace(/^0+/, '') || '0').slice(0, 3) + '.json'
      : key ? this.id + '/search/' + key + '.json' : null;
    if (!path) return Promise.resolve([]);
    return this.fetchJSON(path).catch(function () { return []; }).then(function (entries) {
      var hits = entries.map(function (e) {
        var o = {};
        for (var j = 0; j < SF.length; j++) o[SF[j]] = e[j];
        o.city = cities[o.city];
        return o;
      }).filter(function (o) {
        if (looksLikeAccount) return o.account.toUpperCase().indexOf(q) === 0;
        if (num) return o.street_num === num && o.street_name.indexOf(rest) >= 0;
        return o.street_name.indexOf(rest) >= 0;
      });
      hits.sort(function (a, b) {
        return a.street_name < b.street_name ? -1 : a.street_name > b.street_name ? 1
          : (a.street_num < b.street_num ? -1 : a.street_num > b.street_num ? 1 : 0);
      });
      return hits.slice(0, limit);
    });
  };

  // ---- comparison sets (app/comps.py find_comps) ---------------------------------

  var SQFT_BAND = 0.15, MAX_ROWS = 200;

  function result(criteria, rows, includeRows) {
    rows.sort(byValueThenAccount);
    var out = { criteria: criteria, stats: summarize(rows.map(function (r) { return r.appraised_val; })) };
    if (includeRows) {
      out.comps = rows.slice(0, MAX_ROWS).map(compRow);
      out.truncated = rows.length > MAX_ROWS;
    }
    return out;
  }

  function compRow(r) {
    return { account: r.account, address: address(r), deed_date: r.deed_date, appraised_val: r.appraised_val,
             beds: r.beds, full_baths: r.full_baths, half_baths: r.half_baths, living_sqft: r.living_sqft,
             lot_sqft: r.lot_sqft, year_built: r.year_built };
  }

  County.prototype.findComps = function (s, taxYear) {
    var self = this, since = (taxYear - 1) + '-01-01', cat = category(s);
    var base = function (p) {
      return p.account !== s.account && p.appraised_val > 0 && (!cat || category(p) === cat);
    };
    var sqft = s.living_sqft || 0, low = sqft * (1 - SQFT_BAND), high = sqft * (1 + SQFT_BAND);
    var beds = s.beds, full = s.full_baths, half = s.half_baths;
    var hasRooms = beds != null && full != null;
    var nbhd = s.nbhd, useNbhd = nbhd && nbhd.toUpperCase() !== 'UNASSIGNED';
    var loads = [s.zip ? self.area(s.zip) : Promise.resolve([]),
                 useNbhd ? self.areas(self.nbhdAreas(nbhd)) : Promise.resolve([])];
    return Promise.all(loads).then(function (loaded) {
      var zipRows = s.zip ? loaded[0].filter(function (p) { return p.zip === s.zip; }) : [];
      var nbhdRows = loaded[1];

      var nb = useNbhd ? nbhdRows.filter(function (p) {
        return base(p) && p.nbhd === nbhd && p.deed_date != null && p.deed_date >= since;
      }) : [];
      var neighborhood = result({ nbhd: nbhd, deed_since: since, state_category: cat }, nb, true);

      var crit = { zip: s.zip, deed_since: since, state_category: cat };
      if (sqft) { crit.sqft_low = pyRound(low); crit.sqft_high = pyRound(high); }
      if (hasRooms) { crit.beds = beds; crit.min_full_baths = full; }
      var zr = (sqft || hasRooms) ? zipRows.filter(function (p) {
        return base(p) && p.deed_date != null && p.deed_date >= since && (!sqft || between(p.living_sqft, low, high)) &&
          (!hasRooms || (p.beds === beds && p.full_baths != null && p.full_baths >= full));
      }) : [];
      var zipSet = result(crit, zr, true);

      crit = { zip: s.zip, state_category: cat };
      if (sqft) { crit.sqft_low = pyRound(low); crit.sqft_high = pyRound(high); }
      if (hasRooms) { crit.beds = beds; crit.full_baths = full; crit.half_baths = half || 0; }
      var ar = (sqft || hasRooms) ? zipRows.filter(function (p) {
        return base(p) && (!sqft || between(p.living_sqft, low, high)) &&
          (!hasRooms || (p.beds === beds && p.full_baths === full && (p.half_baths || 0) === (half || 0)));
      }) : [];
      var allSimilar = result(crit, ar, false);
      return { neighborhood: neighborhood, zip: zipSet, all_similar: allSimilar };
    });
  };

  // ---- equity analysis (app/equity.py analyze) -----------------------------------

  var MILES_PER_DEG_LAT = 69.0;

  function radians(d) { return d * (Math.PI / 180); }  // as Python math.radians

  function distanceMi(lat1, lon1, lat2, lon2) {
    var p1 = radians(lat1), p2 = radians(lat2), dp = p2 - p1, dl = radians(lon2 - lon1);
    var a = Math.pow(Math.sin(dp / 2), 2) + Math.cos(p1) * Math.cos(p2) * Math.pow(Math.sin(dl / 2), 2);
    return 3958.8 * 2 * Math.asin(Math.sqrt(a));
  }

  function effYear(p, useEff) { return useEff ? p.eff_year_built : p.year_built; }

  function adjust(s, c, useEff, params) {
    var impr = c.improvement_val, sqft = c.living_sqft, rate = impr / sqft;
    var size = (s.living_sqft - sqft) * rate;
    var age = impr * params.age_rate * (effYear(s, useEff) - effYear(c, useEff));
    var land = (s.land_val || 0) - (c.land_val || 0);
    var adjusted = c.appraised_val + size + age + land;
    return { improvement_rate: pyRound(rate, 2), size_adj: pyRound(size), age_adj: pyRound(age),
             land_adj: pyRound(land), adjusted_val: pyRound(adjusted) };
  }

  function candidateFilter(s, params) {
    var useEff = s._use_effective, year = effYear(s, useEff), sqft = s.living_sqft, cat = category(s);
    var lo = sqft * (1 - params.sqft_band), hi = sqft * (1 + params.sqft_band);
    return function (p) {
      return p.account !== s.account && p.appraised_val > 0 && p.improvement_val > 0 &&
        between(p.living_sqft, lo, hi) && between(effYear(p, useEff), year - params.year_band, year + params.year_band) &&
        category(p) === cat && (!s.quality || p.quality === s.quality) && (!s.condition || p.condition === s.condition);
    };
  }

  function candidate(p) {
    return { account: p.account, address: address(p), nbhd: p.nbhd, zip: p.zip, deed_date: p.deed_date,
             appraised_val: p.appraised_val, improvement_val: p.improvement_val, land_val: p.land_val, beds: p.beds,
             full_baths: p.full_baths, half_baths: p.half_baths, living_sqft: p.living_sqft, year_built: p.year_built,
             eff_year_built: p.eff_year_built, quality: p.quality, condition: p.condition, lot_sqft: p.lot_sqft,
             lat: p.lat, lon: p.lon };
  }

  County.prototype.findEquityComps = function (s, params) {
    var self = this, keep = candidateFilter(s, params);
    var hasLoc = s.lat != null && s.lon != null;
    var radii = params.radius_steps_mi;

    function radiusStep(i, rows, how) {
      if (!hasLoc || i >= radii.length) return Promise.resolve([rows, how]);
      var r = radii[i], dlat = r / MILES_PER_DEG_LAT, dlon = r / (MILES_PER_DEG_LAT * Math.cos(radians(s.lat)));
      var lat0 = s.lat - dlat, lat1 = s.lat + dlat, lon0 = s.lon - dlon, lon1 = s.lon + dlon;
      return self.areas(self.areasInBox(lat0, lon0, lat1, lon1)).then(function (all) {
        var found = all.filter(function (p) {
          return keep(p) && between(p.lat, lat0, lat1) && between(p.lon, lon0, lon1);
        }).map(function (p) {
          var c = candidate(p);
          c.distance_mi = pyRound(distanceMi(s.lat, s.lon, c.lat, c.lon), 2);
          return c;
        });
        var within = found.filter(function (c) { return c.distance_mi <= r; });
        var h = { method: 'radius', radius_mi: r };
        if (within.length >= params.min_comps) return [within, h, true];
        return radiusStep(i + 1, within, h);
      });
    }

    return radiusStep(0, [], { method: 'none' }).then(function (res) {
      if (res[2]) return [res[0], res[1]];
      var rows = res[0], how = res[1];
      if (!s.nbhd) return [rows, how];
      return self.areas(self.nbhdAreas(s.nbhd)).then(function (all) {
        var found = all.filter(function (p) { return keep(p) && p.nbhd === s.nbhd; }).map(candidate);
        if (found.length > rows.length) {
          found.forEach(function (c) {
            c.distance_mi = s.lat != null && c.lat != null ? pyRound(distanceMi(s.lat, s.lon, c.lat, c.lon), 2) : null;
          });
          return [found, { method: 'neighborhood', nbhd: s.nbhd }];
        }
        return [rows, how];
      });
    });
  };

  function rank(s, rows, useEff) {
    var year = effYear(s, useEff);
    function score(r) {
      var d = r.distance_mi || 0;
      var other = s.nbhd && r.nbhd !== s.nbhd ? 1 : 0;
      return other + d + Math.abs(r.living_sqft - s.living_sqft) / s.living_sqft * 2 + Math.abs(effYear(r, useEff) - year) / 10;
    }
    return rows.map(function (r) { return [score(r), r]; }).sort(function (a, b) {
      return a[0] - b[0] || (a[1].account < b[1].account ? -1 : a[1].account > b[1].account ? 1 : 0);
    }).map(function (x) { return x[1]; });
  }

  County.prototype.equity = function (subject) {
    var params = this.meta.params, s = Object.assign({}, subject);
    var missing = ['living_sqft', 'improvement_val', 'appraised_val'].filter(function (k) { return !s[k]; });
    if (!s.year_built && !s.eff_year_built) missing.push('year_built');
    if (missing.length) return Promise.resolve({ available: false, reason: 'subject is missing ' + missing.join(', '), params: params });
    s._use_effective = !!s.eff_year_built;
    var useEff = s._use_effective;
    return this.findEquityComps(s, params).then(function (res) {
      var rows = res[0], how = res[1];
      if (useEff) rows = rows.filter(function (r) { return r.eff_year_built; });
      var comps = rank(s, rows, useEff).slice(0, params.max_comps);
      comps.forEach(function (c) { Object.assign(c, adjust(s, c, useEff, params)); });
      var out = {
        available: comps.length >= params.min_comps, params: params, search: how,
        criteria: {
          state_category: category(s), quality: s.quality == null ? null : s.quality,
          condition: s.condition == null ? null : s.condition,
          sqft_low: pyRound(s.living_sqft * (1 - params.sqft_band)), sqft_high: pyRound(s.living_sqft * (1 + params.sqft_band)),
          year_basis: useEff ? 'effective year built' : 'year built',
          year_low: effYear(s, useEff) - params.year_band, year_high: effYear(s, useEff) + params.year_band
        },
        candidates_found: rows.length, comps: comps
      };
      if (!out.available) {
        out.reason = 'only ' + comps.length + ' comparable homes found (need ' + params.min_comps + ')';
        return out;
      }
      var med = median(comps.map(function (c) { return c.adjusted_val; }));
      out.count = comps.length;
      out.median_adjusted = pyRound(med);
      out.unadjusted_median = pyRound(median(comps.map(function (c) { return c.appraised_val; })));
      out.subject_value = s.appraised_val;
      out.supports_reduction = s.appraised_val > med;
      out.difference = pyRound(s.appraised_val - med);
      return out;
    });
  };

  // ---- letter (app/letter.py) ----------------------------------------------------

  var SET_TITLES = [
    ['neighborhood', 'Recently transferred homes in my neighborhood'],
    ['zip', 'Similar recently transferred homes in my ZIP code'],
    ['all_similar', 'All similar homes in my ZIP code']
  ];

  function cleanOwnerInput(body) {
    body = body || {};
    var name = String(body.owner_name || '').trim().slice(0, 120) || 'Property Owner';
    var conditions = (body.conditions || []).map(function (c) { return String(c).trim().slice(0, 300); })
      .filter(function (c) { return c; }).slice(0, 20);
    var repairs = [];
    (body.repairs || []).slice(0, 20).forEach(function (r) {
      if (!r || typeof r !== 'object') return;
      var cost = Number(r.cost || 0);
      if (isFinite(cost) && cost > 0 && cost < 10000000) {
        repairs.push({ desc: String(r.desc || '').trim().slice(0, 200) || 'Repair', cost: pyRound(cost) });
      }
    });
    return { name: name, conditions: conditions, repairs: repairs };
  }

  function NoReduction(message) { this.name = 'NoReduction'; this.message = message; }
  NoReduction.prototype = Object.create(Error.prototype);

  function opinionOfValue(subject, equity, sets, repairTotal) {
    var base, basis;
    if (equity.available && equity.supports_reduction) {
      base = equity.median_adjusted; basis = 'equity';
    } else {
      var medians = SET_TITLES.map(function (t) { return sets[t[0]].stats; })
        .filter(function (st) { return st.count; }).map(function (st) { return st.median; });
      if (!medians.length) throw new NoReduction('no comparable properties were found');
      var sum = 0;
      medians.forEach(function (m) { sum += m; });
      base = pyRound(sum / medians.length / 1000) * 1000; basis = 'set_medians';
    }
    var requested = base - repairTotal;
    if (requested >= subject.appraised_val) throw new NoReduction('the comparable appraised values do not support a lower value');
    return { base: base, basis: basis, requested: requested, reduction: subject.appraised_val - requested };
  }

  function describe(c) {
    var parts = [];
    if (c.nbhd) parts.push('neighborhood code ' + c.nbhd);
    if (c.zip) parts.push('ZIP ' + c.zip);
    if (c.beds != null) parts.push(c.beds + ' bedrooms');
    if (c.min_full_baths != null) parts.push('at least ' + c.min_full_baths + ' full baths');
    if (c.full_baths != null) parts.push(c.full_baths + ' full / ' + c.half_baths + ' half baths');
    if (c.sqft_low != null) parts.push(fmt.int(c.sqft_low) + '–' + fmt.int(c.sqft_high) + ' sq ft living area');
    if (c.deed_since) parts.push('deed recorded on or after ' + c.deed_since);
    return parts.join(', ');
  }

  function p() {
    return { t: 'p', runs: Array.prototype.map.call(arguments, function (r) { return typeof r === 'string' ? [r, false] : r; }) };
  }

  // todayText: e.g. 'October 13, 2026' (Python: strftime('%B %d, %Y') without the leading zero).
  function letterBlocks(cfg, s, eq, sets, owner, todayText) {
    var money = fmt.money, val = s.appraised_val;
    var repairTotal = 0;
    owner.repairs.forEach(function (r) { repairTotal += r.cost; });
    var op = opinionOfValue(s, eq, sets, repairTotal);
    var street = (s.street_num + ' ' + s.street_name).trim();
    var addr = [street, s.city, ('TX ' + (s.zip || '')).trim()].filter(function (x) { return x; }).join(', ');

    var grounds = [];
    if (eq.available && eq.supports_reduction) {
      grounds.push('Unequal appraisal (Texas Tax Code §41.41(a)(2), §42.26(a)(3)): my appraised value of ' + money(val) +
        ' exceeds the median appraised value of ' + eq.count + ' comparable properties, appropriately adjusted, which is ' +
        money(eq.median_adjusted) + '.');
    }
    var above = SET_TITLES.filter(function (t) { var st = sets[t[0]].stats; return st.count && val > st.median; });
    if (above.length && !grounds.length) {
      grounds.push('Unequal appraisal (Texas Tax Code §41.41(a)(2)): my appraised value is higher than the median appraised value of ' +
        above.map(function (t) { var st = sets[t[0]].stats; return st.count + ' ' + t[1].toLowerCase() + ' (' + money(st.median) + ')'; }).join('; ') + '.');
    }
    if (owner.conditions.length) grounds.push('Property-specific conditions, described below.');
    if (repairTotal) grounds.push('Repair costs totaling ' + money(repairTotal) + ', based on the estimates listed below.');

    var blocks = [
      { t: 'title', text: 'Property Tax Protest' },
      { t: 'small', text: cfg.tax_year + ' Appraisal Year · ' + cfg.cad_name + '\n' + todayText },
      { t: 'space', h: 8 },
      p(['To:', true], ' Appraisal Review Board, ' + cfg.cad_name + ', ' + cfg.cad_address),
      p(['From:', true], ' ' + owner.name + '\n', ['Re:', true], ' Account ' + s.account + ', ' + addr),
      { t: 'space', h: 6 },
      p('Dear Members of the Appraisal Review Board,'),
      p('I am protesting the ' + cfg.tax_year + ' appraised value of ', [money(val), true],
        ' for my property at ' + addr + ' and request that it be reduced to ', [money(op.requested), true],
        ', a reduction of ' + money(op.reduction) + ' (' + fmt.fixed(op.reduction / val * 100, 1) + '%).'),
      p('This protest is based on the following grounds:')
    ];
    grounds.forEach(function (g, i) { blocks.push(p((i + 1) + '. ' + g)); });

    var yr = s.year_built || '—';
    var eff = s.eff_year_built ? ' (effective ' + s.eff_year_built + ')' : '';
    var rooms = s.beds != null ? s.beds + ' bedrooms, ' : '';
    var baths = s.full_baths != null ? s.full_baths + ' full / ' + (s.half_baths || 0) + ' half baths, ' : '';
    blocks.push({ t: 'h2', text: 'Subject property' },
      p('Account ' + s.account + '. ' + rooms + baths +
        (s.living_sqft ? fmt.int(s.living_sqft) + ' sq ft living area' : 'living area not recorded') + ', built ' + yr + eff +
        (s.quality ? ', quality ' + s.quality : '') + (s.lot_sqft ? ', lot ' + fmt.int(s.lot_sqft) + ' sq ft' : '') +
        '. Appraised at ' + money(val) + ': improvements ' + money(s.improvement_val || 0) + ', land ' + money(s.land_val || 0) + '.'),
      { t: 'small', text: 'All values are appraised values from the ' + cfg.cad_name + ' ' + cfg.tax_year + ' appraisal roll, not sale prices.' });

    var n = 1;
    if (eq.available) {
      var cr = eq.criteria, prm = eq.params, radius = eq.search.radius_mi;
      var where = eq.search.method === 'radius'
        ? 'within ' + fmt.g(radius) + ' ' + (radius === 1 ? 'mile' : 'miles') + ' of my property'
        : 'in neighborhood ' + eq.search.nbhd;
      var grades = [cr.quality ? 'quality grade (' + cr.quality + ')' : '', cr.condition ? 'condition rating (' + cr.condition + ')' : '']
        .filter(function (g) { return g; }).join(' and ');
      var yearKey = cr.year_basis.indexOf('effective') === 0 ? 'eff_year_built' : 'year_built';
      var rows = [['Address', 'Miles', 'Sq ft', 'Year', 'Appraised', 'Size adj.', 'Age adj.', 'Land adj.', 'Adjusted'],
                  [street + ' (subject)', '', fmt.int(s.living_sqft), String(s[yearKey] || ''), money(val), '', '', '', '']];
      eq.comps.forEach(function (r) {
        rows.push([r.address, r.distance_mi == null ? '' : fmt.fixed(r.distance_mi, 2), fmt.int(r.living_sqft),
                   String(r[yearKey] || ''), money(r.appraised_val), fmt.signed(r.size_adj), fmt.signed(r.age_adj),
                   fmt.signed(r.land_adj), money(r.adjusted_val)]);
      });
      rows.push(['Median adjusted value', '', '', '', '', '', '', '', money(eq.median_adjusted)]);
      var verdict = eq.supports_reduction ? 'My appraised value is ' + money(eq.difference) + ' more than this median.'
        : 'My appraised value is not above this median.';
      blocks.push({ t: 'h2', text: 'Evidence ' + n + ': Comparable properties, appropriately adjusted' },
        p('I selected the ' + eq.count + ' most similar properties ' + where + ' in the same property category' +
          (grades ? ' and the same ' + grades : '') + ', with ' + fmt.int(cr.sqft_low) + '–' + fmt.int(cr.sqft_high) +
          ' sq ft of living area and ' + cr.year_basis + ' between ' + cr.year_low + ' and ' + cr.year_high +
          ". Each comparable's appraised value is adjusted to my property: living area at the comparable's own improvement " +
          'value per square foot; age at ' + fmt.fixed(prm.age_rate * 100, 1) + '% of its improvement value per year of ' +
          'difference; land by the difference in appraised land value.'),
        { t: 'table', rows: rows, widths: [1.55, 0.45, 0.5, 0.4, 0.75, 0.7, 0.65, 0.7, 0.75], highlight: [1, rows.length - 1] },
        p('The median of the ' + eq.count + ' adjusted values is ', [money(eq.median_adjusted), true],
          ' (unadjusted median ' + money(eq.unadjusted_median) + '). ' + verdict));
      n += 1;
    }

    SET_TITLES.forEach(function (t) {
      var st = sets[t[0]].stats;
      if (!st.count) return;
      blocks.push({ t: 'h2', text: 'Evidence ' + n + ': ' + t[1] + ' (appraised value)' },
        p(st.count + ' properties on the ' + cfg.cad_abbrev + ' ' + cfg.tax_year + ' roll match ' + describe(sets[t[0]].criteria) +
          '. Median appraised value ', [money(st.median), true], '; range ' + money(st.low) + ' to ' + money(st.high) + '.'));
      n += 1;
    });

    if (owner.conditions.length) {
      blocks.push({ t: 'h2', text: 'Property-specific conditions' });
      owner.conditions.forEach(function (x) { blocks.push(p('• ' + x)); });
    }
    if (owner.repairs.length) {
      var rrows = [['Description', 'Estimated cost']].concat(owner.repairs.map(function (r) { return [r.desc, money(r.cost)]; }));
      rrows.push(['Total', money(repairTotal)]);
      blocks.push({ t: 'h2', text: 'Repair costs' }, { t: 'table', rows: rrows, widths: [4.5, 1.5], highlight: [rrows.length - 1] },
        { t: 'small', text: 'Copies of the estimates are attached.' });
    }

    var baseLabel = op.basis === 'equity' ? 'Median adjusted value of comparable properties (Evidence 1)'
      : 'Average of the comparison-set median appraised values, rounded to $1,000';
    var vrows = [['Basis', 'Value'], [baseLabel, money(op.base)]];
    if (repairTotal) vrows.push(['Less: repair costs', '-' + money(repairTotal)]);
    vrows.push(['Requested appraised value', money(op.requested)]);
    blocks.push({ t: 'h2', text: 'Requested value' },
      { t: 'table', rows: vrows, widths: [4.5, 1.5], highlight: [vrows.length - 1] },
      { t: 'space', h: 6 },
      p('Based on the evidence above, I respectfully request that the Appraisal Review Board reduce the appraised value of my ' +
        'property from ' + money(val) + ' to ' + money(op.requested) + '. Thank you for your time and consideration.'),
      { t: 'space', h: 18 }, p('Respectfully submitted,'), { t: 'space', h: 26 },
      p('______________________________\n' + owner.name + '\n' + addr), { t: 'space', h: 14 },
      { t: 'small', text: 'Data source: ' + cfg.cad_name + ', ' + cfg.tax_year + ' appraisal roll. Prepared with a free ' +
        'self-help tool; not legal or appraisal advice.' });
    return { opinion: op, address: addr, owner_name: owner.name, blocks: blocks };
  }

  function todayText(d) {
    d = d || new Date();
    var months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
                  'November', 'December'];
    return months[d.getMonth()] + ' ' + d.getDate() + ', ' + d.getFullYear();
  }

  var api = { County: County, pyRound: pyRound, roundDecimal: roundDecimal, fmt: fmt, median: median, summarize: summarize, distanceMi: distanceMi,
              adjust: adjust, describe: describe, cleanOwnerInput: cleanOwnerInput, opinionOfValue: opinionOfValue,
              letterBlocks: letterBlocks, todayText: todayText, NoReduction: NoReduction };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.ProtestEngine = api;
})(this);
