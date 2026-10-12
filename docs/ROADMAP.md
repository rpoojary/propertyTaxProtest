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
### Phase 0 — Get the data (CURRENT)
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

### Phase 1 — Foundation (~1 day)
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

Open questions: keep `TOTAL_EXEMPTION.CSV` in git or move to `data/`?
OK to rename `webapp/` → `app/` (breaks GoDaddy path)?

### Phase 2 — Canonical schema + Dallas & Collin adapters (golden-file tests)
### Phase 3 — Denton & Tarrant adapters + GIS lat/lon
### Phase 4 — Equity comp engine (§42.26(a)(3) adjusted median, adjustment grid) + server-side PDF, prefilled Comptroller Form 50-132, §41.461 evidence-request reminder
### Phase 5 — Public launch: property pages, county guides, Cloudflare, analytics, ads

## Known issues in current code
See Phase 1 list. Also: Collin importer sets beds/baths to 0 (breaks zip comps).
