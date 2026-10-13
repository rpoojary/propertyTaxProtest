# Roadmap — Texas Property Tax Protest Helper

## Product decisions (agreed)
- **Free public tool**, ad-supported later. Texas only.
- **Counties (v1):** Dallas, Denton, Collin, Tarrant.
- **No MLS / sale-price access.** The core argument is **unequal appraisal**
  (Texas Tax Code §42.26(a)(3)): subject's appraised value vs. the median
  appraised value of a reasonable number of comparable properties, appropriately adjusted.
  Market-value evidence is optional and owner-supplied (own purchase price,
  own appraisal, repair estimates, photos).
- Never call appraised values "sale prices". Every claim in the generated
  letter must be computed from data (no hardcoded narrative).
- Don't show owner names on public pages. Self-help tool, not an agent
  (owner files their own protest). Disclaimers: not legal/appraisal advice.
- No scraping Zillow/Redfin listings.

## Architecture direction
- Per-county **adapters** → **canonical schema** → read-only SQLite (one DB,
  or one per county) → Flask/FastAPI API → UI + protest document.
- Canonical tables (draft): `property`, `valuation` (per year), `improvement`,
  `land`, `exemption`, `sale` (where available), `county_meta`.
- Lat/lon from county GIS parcel files → radius-based comps.
- Hosting: Fly.io/Render + Cloudflare caching (seasonal April–May spikes).
  Postgres only if user accounts are added.
- SEO: one page per property (`/tx/<county>/<address-slug>`) + county guides.

## Phases
### Phase 0 — Get the data — DONE
Download each county's bulk export, inspect layouts, document fields in
`docs/data-sources.md`. Raw files go in `data/` (gitignored, never committed).

Status (2026-10-12): all four counties downloaded and documented in
`docs/data-sources.md`; fetch with `python scripts/fetch_data.py`.

| County | Source (verified) | Notes |
|---|---|---|
| Dallas | olp.dallascad.org/DataProducts.aspx; files via `www.dallascad.org/ViewPDFs.aspx` | Certified CSV tables + ARB outcomes + `PARCEL_GEOM.zip`. |
| Collin | link.collincad.org public shares (linked from collincad.org) | Nightly CSVs; `CCAD-Appraisal-Data.csv` has beds/baths. |
| Tarrant | www.tad.org/resources/data-downloads | Pipe-delimited roll, comp attributes (quality/condition/equity value), parcels. No beds/baths. |
| Denton | denton.prodigycad.com/data-downloads → files on dentoncad.net | Nightly CSV + weekly geodatabase; beds/baths only in the full fixed-width certified export. |

Cloud sessions need these domains allowed in the environment's network
settings: `dallascad.org`, `*.dallascad.org`, `tad.org`, `*.tad.org`,
`collincad.org`, `*.collincad.org`, `dentoncad.com`, `*.dentoncad.com`,
`dentoncad.net`, `*.dentoncad.net`, `*.prodigycad.com`, `*.trueprodigyapi.com`,
`cdn.builder.io` (only to render Denton's index page).

### Phase 1 — Foundation (~1 day) — DONE 2026-10-12
All items below landed; see README for the new layout. Decisions: `TOTAL_EXEMPTION.CSV`
removed from git (it ships inside the Dallas zip); GoDaddy files deleted (it was
an experiment); app DB is one denormalized `property` table (Phase 2 replaces it
with the canonical schema); the test fixture is synthetic CSVs run through the
real adapter, not a committed `.db`.

1. Restructure repo: `app/` (main.py, db.py, routes/, static/, wsgi.py),
   `counties/` (config.yaml + per-county adapter dirs), `pipeline/build_db.py`,
   `scripts/query_comps.py` (takes args), `data/` (gitignored), `tests/`.
   Delete `County/Dallas/dcad.db-shm`.
2. Fixes: `debug=True` on 0.0.0.0 → env-gated, localhost default; remove
   fabricated "highest $/sqft, smallest lot" narrative in protest.js;
   HTML-escape all user/DB values; relabel "comparable sales" as
   "recently sold properties (appraised value)"; true median; safe numeric
   parsing; fix `query_comps.py` AREA_UOM_DESC; read-only DB connections.
3. `counties/config.yaml`: name, CAD name/abbrev, ARB address, protest URL,
   tax_year, date_format, db path. `/api/counties` endpoint, county picker,
   letter uses config. Sold-year filter derived from tax_year.
4. Tests: tiny fixture DB in git, pytest for endpoints/stats/parsing, ruff,
   GitHub Actions CI, `.gitignore`.
5. Rewrite README; mark DEPLOY_GODADDY.md stale.


### Phase 2 — Canonical schema + adapters (golden-file tests) — DONE 2026-10-12
Each county DB now holds canonical tables (`property`, `valuation` per year,
`improvement`, `land`, `exemption`, `deed`, `county_meta`; schema in
`app/db.py`) filled by all four adapters, plus a derived `property_summary`
table the app reads. `sale` became `deed`: no county publishes prices, so the
table records transfer dates only. Golden-file tests (`tests/golden/`) pin
every adapter's full output on its fixture. Rebuilding the real DBs gave the
same summary values as before for all 2.37M properties, except 33,827 Dallas
homes whose placeholder year built (0/1/1000) is now stored as unknown.
New data now available for Phase 4: prior-year values (Dallas, Collin,
Tarrant), quality/condition/effective year (all but Collin condition), extra
structures (Dallas), all exemption codes, deed types/instruments.
### Phase 3 — Denton & Tarrant adapters + GIS lat/lon — DONE 2026-10-12
All four counties build an app DB. Every property gets a parcel-centroid
lat/lon (pure-Python shapefile reader + Lambert Conformal Conic inverse, no
GDAL). Coverage of residential properties: Dallas 93%, Collin 97%, Tarrant
100%, Denton 98% (Denton uses its 2023 parcel shapefile; the current parcels
only ship as a file geodatabase). Lat/lon is stored and shown as a map link;
radius-based comps are left for Phase 4. Tarrant has no beds/baths and only
owner-occupied homes get a ZIP (72%); its market area stands in for the
neighborhood code.
### Phase 4 — Equity comp engine + PDF letter — DONE 2026-10-12 (except Form 50-132)
- `app/equity.py`: comparables by distance from the parcel centroid (0.5 →
  1 → 2 → 3 mi, neighborhood fallback), same property category and, where
  published, quality grade and condition; living area ±20%, (effective) year
  built ±10. Up to 15, ranked by same neighborhood, distance, size, age.
  Adjustment grid: size at the comparable's improvement $/sq ft, age at 0.5%
  of improvement value per year, land by land-value difference. Median of
  adjusted values = §42.26(a)(3) indicated value.
- On a random 300 homes per county: 97–99% get an analysis; about half are
  above their adjusted median. Typical gap: Dallas 2.3%, Collin 1.5%,
  Denton 2.6%, Tarrant 11% (TAD values vary more within its coarse grades).
- `app/letter.py`: PDF letter built server-side from the analysis
  (`POST /api/<county>/letter/<account>`); refuses (422) when the data does
  not support a reduction. Opinion of value = adjusted median − owner repair
  costs, falling back to the comparison-set medians when no analysis.
- Page: adjusted-comparables card, PDF download, filing deadline (§41.44) and
  evidence-request (§41.461) reminders.
- Form 50-132 prefill is NOT done: every copy of the form is on hosts this
  environment cannot reach (comptroller.texas.gov). Needs that domain allowed.
### Phase 5 — Public launch (IN PROGRESS)
Done 2026-10-13:
- Serverless static site (`site/`): data exported as JSON shards
  (`pipeline/export_static.py`, ~1.88M homes in ~6k files), comparison sets,
  equity analysis and letter ported to JS (`site/js/engine.js`), PDF drawn
  in the browser (`site/js/pdf.js`). Parity: identical to Python on all four
  county fixtures (CI) and on 800 random real homes; browser PDF contains
  every word of the Python letter.
- Confidential records (§25.025) excluded from everything the app serves.
- Deploy workflow to Cloudflare Pages (needs Cloudflare secrets; see README).
Remaining: property pages (`/tx/<county>/<address-slug>`), county guides,
sitemap, analytics, ads, privacy page, Form 50-132 prefill.

## Known issues in current code
- Bedrooms/baths, pools and other structures are not adjusted in the equity
  grid; district values are driven mainly by living area, which is.
- Collin lot size is only published for ~30% of homes.
- Tarrant market areas are broader than Dallas/Collin neighborhoods, so the
  unadjusted neighborhood set can mix very different homes.
- Tarrant homes that are not owner-occupied have no ZIP, so they only get the
  neighborhood comparison set.
- Denton parcels created after Dec 2023 have no lat/lon until the geodatabase
  can be read.
