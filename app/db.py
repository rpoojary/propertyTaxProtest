"""County DB schema and read-only access.

pipeline/build_db.py writes one SQLite file per county:

  canonical tables  property, valuation, improvement, land, exemption, deed,
                    county_meta. Same columns for every county; adapters
                    fill them from each county's raw export.
  property_summary  one row per property, derived from the canonical tables
                    by SUMMARY_SQL. The web app reads only this table.

Values are appraisal-district values. `deed` records ownership transfers;
Texas does not publish sale prices, so there is no price column.
"""
import sqlite3
from urllib.parse import quote

SCHEMA = """
CREATE TABLE property (
    account       TEXT PRIMARY KEY,
    parcel_id     TEXT,     -- key into the county parcel map
    street_num    TEXT,
    street_name   TEXT,
    unit          TEXT,
    city          TEXT,
    zip           TEXT,
    state_cd      TEXT,     -- Texas PTAD state category code, e.g. A1 / A11
    nbhd          TEXT,     -- neighborhood / market area code
    legal_desc    TEXT,
    lat           REAL,     -- parcel centroid, WGS84
    lon           REAL
);
CREATE TABLE valuation (
    account         TEXT NOT NULL,
    tax_year        INTEGER NOT NULL,
    land_val        REAL,
    improvement_val REAL,
    market_val      REAL,   -- land + improvements
    appraised_val   REAL,   -- market less agricultural-use reduction
    assessed_val    REAL,   -- appraised less the homestead cap, where published
    PRIMARY KEY (account, tax_year)
);
CREATE TABLE improvement (
    account       TEXT NOT NULL,
    kind          TEXT NOT NULL,   -- 'main' (living area) or 'other' (garage, pool, shed...)
    seq           INTEGER NOT NULL,  -- distinguishes rows of the same kind
    description   TEXT,
    year_built    INTEGER,
    eff_year_built INTEGER,
    living_sqft   REAL,            -- main only
    area_sqft     REAL,            -- other only
    beds          INTEGER,
    full_baths    INTEGER,
    half_baths    INTEGER,
    stories       TEXT,
    quality       TEXT,            -- county class / quality grade, as published
    condition     TEXT,            -- as published (e.g. Dallas CDU rating)
    pool          INTEGER,
    value         REAL,
    PRIMARY KEY (account, kind, seq)
);
CREATE TABLE land (
    account       TEXT NOT NULL,
    seq           INTEGER NOT NULL,  -- 1 = primary land segment
    size_sqft     REAL,
    value         REAL,
    PRIMARY KEY (account, seq)
);
CREATE TABLE exemption (
    account       TEXT NOT NULL,
    tax_year      INTEGER NOT NULL,
    code          TEXT NOT NULL,     -- 'HS' homestead, 'OV65', 'DP', 'DV', or the county's own code
    description   TEXT,
    PRIMARY KEY (account, tax_year, code)
);
CREATE TABLE deed (
    account       TEXT NOT NULL,
    transfer_date TEXT NOT NULL,     -- ISO YYYY-MM-DD
    deed_type     TEXT,
    instrument    TEXT,
    PRIMARY KEY (account, transfer_date)
);
CREATE TABLE county_meta (key TEXT PRIMARY KEY, value TEXT);
"""

CANONICAL_TABLES = ("property", "valuation", "improvement", "land", "exemption", "deed")

SUMMARY_SQL = """
CREATE TABLE property_summary AS
WITH main AS (
    SELECT account, beds, full_baths, half_baths, living_sqft, year_built,
           row_number() OVER (PARTITION BY account ORDER BY coalesce(living_sqft, 0) DESC, seq) AS rn
    FROM improvement WHERE kind = 'main'
)
SELECT p.account, p.street_num, p.street_name, p.city, p.zip, p.state_cd, p.nbhd,
       (SELECT max(transfer_date) FROM deed d WHERE d.account = p.account) AS deed_date,
       v.appraised_val, v.improvement_val, v.land_val, v.market_val,
       prev.market_val AS prior_market_val,
       m.beds, m.full_baths, m.half_baths, m.living_sqft, m.year_built,
       l.size_sqft AS lot_sqft,
       EXISTS (SELECT 1 FROM exemption e WHERE e.account = p.account AND e.code = 'HS') AS homestead,
       p.parcel_id, p.lat, p.lon
FROM property p
JOIN valuation v ON v.account = p.account AND v.tax_year = :tax_year
LEFT JOIN valuation prev ON prev.account = p.account AND prev.tax_year = :tax_year - 1
LEFT JOIN main m ON m.account = p.account AND m.rn = 1
LEFT JOIN land l ON l.account = p.account AND l.seq = 1;
"""

INDEXES = """
CREATE INDEX idx_valuation_year ON valuation(tax_year);
CREATE UNIQUE INDEX idx_sum_account ON property_summary(account);
CREATE INDEX idx_sum_street ON property_summary(street_num, street_name);
CREATE INDEX idx_sum_zip ON property_summary(zip);
CREATE INDEX idx_sum_nbhd ON property_summary(nbhd);
"""

PARCEL_INDEX = "CREATE INDEX IF NOT EXISTS idx_property_parcel ON property(parcel_id)"


def columns(table):
    """Column names of a canonical table, in schema order."""
    db = sqlite3.connect(":memory:")
    db.executescript(SCHEMA)
    return tuple(r[1] for r in db.execute(f"PRAGMA table_info({table})"))


def connect_ro(path):
    """Open an existing SQLite file read-only (fails if it does not exist)."""
    db = sqlite3.connect(f"file:{quote(path)}?mode=ro", uri=True, check_same_thread=False)
    db.row_factory = sqlite3.Row
    return db
