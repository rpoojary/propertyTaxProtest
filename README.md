# Texas Property Tax Protest Helper

A free self-help tool for Texas homeowners. Look up your property, compare its
**appraised value** with similar properties on the appraisal district's roll,
and download a protest letter you file yourself. The core argument is
**unequal appraisal** (Texas Tax Code §41.41(a)(2), §42.26(a)(3)). Texas does
not publish sale prices, so all comparisons use appraised values.

Not legal or appraisal advice. Product decisions and the phase plan are in
[`docs/ROADMAP.md`](docs/ROADMAP.md); county data sources are in
[`docs/data-sources.md`](docs/data-sources.md).

Counties: Dallas and Collin work end to end. Tarrant and Denton data is
downloaded but has no app DB adapter yet.

## Layout

```
app/                 Flask app: main.py (factory + dev server), wsgi.py,
                     routes/api.py, comps.py (queries), stats.py, db.py, static/
counties/config.yaml per-county settings (CAD name/address, tax year, paths)
counties/<county>/   adapter.py: raw export -> app DB
pipeline/build_db.py build a county's app DB
scripts/fetch_data.py      download raw county exports into data/
scripts/query_comps.py     print a property's comparables from the command line
tests/               pytest suite; fixtures/ holds synthetic Dallas-format CSVs
data/                raw downloads and built DBs (gitignored, never committed)
```

## Setup

Python 3.11+.

```bash
pip install -r requirements-dev.txt
python scripts/fetch_data.py dallas collin     # ~1.7 GB of raw exports
python pipeline/build_db.py dallas             # -> data/dallas/app.db
python pipeline/build_db.py collin             # -> data/collin/app.db
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

## How comparisons work (current, before Phase 4)

For the selected property, the app builds three sets from the same state
property category (e.g. residential):

1. **Neighborhood:** same neighborhood code, deed recorded since Jan 1 of
   the year before the tax year.
2. **ZIP, similar:** same ZIP, same bedrooms, at least as many full baths,
   living area within ±15%, deed recorded since the same date.
3. **ZIP, all similar:** same ZIP, bedrooms, full and half baths, and size
   band, regardless of deed date.

The suggested value is the average of the sets' median appraised values
(rounded to $1,000), minus any repair costs the owner enters. The letter
states each set's exact criteria, count, median and range. Phase 4 replaces
this with an adjusted-median equity analysis.
