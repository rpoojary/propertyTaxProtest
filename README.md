# Texas Property Tax Protest Helper

A free self-help tool for Texas homeowners. Look up your property, compare its
**appraised value** with similar properties on the appraisal district's roll,
and download a protest letter you file yourself. The core argument is
**unequal appraisal** (Texas Tax Code §41.41(a)(2), §42.26(a)(3)). Texas does
not publish sale prices, so all comparisons use appraised values.

Not legal or appraisal advice. Product decisions and the phase plan are in
[`docs/ROADMAP.md`](docs/ROADMAP.md); county data sources are in
[`docs/data-sources.md`](docs/data-sources.md).

Counties: Dallas, Collin, Tarrant and Denton. Tarrant does not publish
bedroom/bath counts, so its comparisons match on size only.

## Layout

```
app/                 Flask app: main.py (factory + dev server), wsgi.py,
                     routes/api.py, comps.py (queries), stats.py, static/,
                     db.py (DB schema: canonical tables + property_summary)
counties/config.yaml per-county settings (CAD name/address, tax year, paths)
counties/<county>/   adapter.py: raw export -> app DB
pipeline/build_db.py build a county's app DB
pipeline/geo.py      parcel shapefile centroids -> lat/lon (no GDAL needed)
scripts/fetch_data.py      download raw county exports into data/
scripts/query_comps.py     print a property's comparables from the command line
tests/               pytest suite; fixtures/ holds synthetic county exports,
                     golden/ the expected adapter output (golden files)
data/                raw downloads and built DBs (gitignored, never committed)
```

## Setup

Python 3.11+.

```bash
pip install -r requirements-dev.txt
python scripts/fetch_data.py                   # ~3.5 GB of raw exports, all counties
for c in dallas collin tarrant denton; do python pipeline/build_db.py $c; done
```

## Run

```bash
python -m app.main                  # http://127.0.0.1:5000
FLASK_DEBUG=1 python -m app.main    # debug mode (local only)
HOST=0.0.0.0 PORT=8000 python -m app.main
gunicorn app.wsgi:app               # production
```

The app only lists counties whose DB exists, opens DBs read-only, and never
stores or returns owner names.

## Command line

```bash
python scripts/query_comps.py dallas 325402100A0260000
python scripts/query_comps.py dallas 325402100A0260000 --set zip
```

## Tests and lint

```bash
pytest -q
ruff check .
```

CI runs both on every push (`.github/workflows/ci.yml`).

`tests/test_golden.py` compares each adapter's complete output on its fixture
with `tests/golden/<county>.json`. After an intended adapter change,
regenerate and review the diff:

```bash
UPDATE_GOLDEN=1 pytest tests/test_golden.py && git diff tests/golden
```

## Database

Each county DB (`data/<county>/app.db`) has the same canonical tables:
`property`, `valuation` (one row per tax year), `improvement` (main dwelling
and other structures), `land`, `exemption`, `deed` (transfer dates; Texas
publishes no sale prices) and `county_meta`. The web app reads
`property_summary`, one row per property derived from those tables in
`app/db.py`.

## How the protest value is computed

The main evidence is an unequal-appraisal analysis (`app/equity.py`,
Texas Tax Code §42.26(a)(3)): up to 15 nearby comparable homes (same
category and, where published, quality grade and condition; similar size
and age), each adjusted to the subject for living area, age and land value.
The median adjusted value is the indicated value; the suggested opinion of
value is that median minus any repair costs the owner enters. The PDF letter
(`app/letter.py`, `POST /api/<county>/letter/<account>`) shows the full
adjustment grid and is refused when the data does not support a reduction.

## Supporting comparison sets

For the selected property, the app builds three sets from the same state
property category (e.g. residential):

1. **Neighborhood:** same neighborhood code, deed recorded since Jan 1 of
   the year before the tax year.
2. **ZIP, similar:** same ZIP, same bedrooms, at least as many full baths,
   living area within ±15%, deed recorded since the same date.
3. **ZIP, all similar:** same ZIP, bedrooms, full and half baths, and size
   band, regardless of deed date.

These are shown on the page and listed in the letter as supporting evidence.
When the adjusted analysis is unavailable (fewer than 5 comparables), the
average of these medians is used instead.
