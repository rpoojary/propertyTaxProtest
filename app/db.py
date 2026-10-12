"""Read-only access to a county app DB built by pipeline/build_db.py."""
import sqlite3
from urllib.parse import quote

SCHEMA = """
CREATE TABLE property (
    account       TEXT PRIMARY KEY,
    street_num    TEXT,
    street_name   TEXT,
    city          TEXT,
    zip           TEXT,
    state_cd      TEXT,     -- Texas PTAD state category code, e.g. A1 / A11
    nbhd          TEXT,
    deed_date     TEXT,     -- ISO YYYY-MM-DD; transfer date, not a sale price
    appraised_val REAL,
    improvement_val REAL,
    land_val      REAL,
    beds          INTEGER,
    full_baths    INTEGER,
    half_baths    INTEGER,
    living_sqft   REAL,
    year_built    INTEGER,
    lot_sqft      REAL,
    homestead     INTEGER
);
CREATE TABLE county_meta (key TEXT PRIMARY KEY, value TEXT);
"""

INDEXES = """
CREATE INDEX idx_prop_street ON property(street_num, street_name);
CREATE INDEX idx_prop_zip ON property(zip);
CREATE INDEX idx_prop_nbhd ON property(nbhd);
"""

COLUMNS = ("account", "street_num", "street_name", "city", "zip", "state_cd", "nbhd",
           "deed_date", "appraised_val", "improvement_val", "land_val", "beds",
           "full_baths", "half_baths", "living_sqft", "year_built", "lot_sqft", "homestead")


def connect_ro(path):
    """Open an existing SQLite file read-only (fails if it does not exist)."""
    db = sqlite3.connect(f"file:{quote(path)}?mode=ro", uri=True, check_same_thread=False)
    db.row_factory = sqlite3.Row
    return db
