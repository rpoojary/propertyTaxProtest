import sqlite3

import pytest

from tests.conftest import read_rows


@pytest.fixture
def rows(dallas_db):
    return read_rows(dallas_db)


def test_all_accounts_loaded(rows):
    assert set(rows) == {"S0001", "C0001", "C0002", "C0003", "C0004", "C0005", "C0006", "C0007", "C0008"}


def test_subject_fields(rows):
    s = rows["S0001"]
    assert s["zip"] == "75000"
    assert s["deed_date"] == "2014-05-01"
    assert s["appraised_val"] == 400000
    assert (s["beds"], s["full_baths"], s["half_baths"]) == (3, 2, 0)
    assert s["lot_sqft"] == 6000  # section 1 only
    assert s["state_cd"] == "A11"
    assert s["homestead"] == 1


def test_land_units(rows):
    assert rows["C0006"]["lot_sqft"] == pytest.approx(0.5 * 43560)
    assert rows["C0001"]["lot_sqft"] == 7000
    assert rows["C0002"]["lot_sqft"] is None


def test_largest_dwelling_kept(rows):
    assert rows["C0002"]["living_sqft"] == 2100
    assert rows["C0002"]["half_baths"] == 1


def test_placeholders_and_blanks(rows):
    assert rows["C0001"]["homestead"] == 0  # 01/01/1900 placeholder date
    assert rows["C0008"]["deed_date"] is None
    assert rows["C0008"]["appraised_val"] is None
    assert rows["C0008"]["improvement_val"] == 1000
    assert rows["C0005"]["beds"] is None


def test_owner_names_not_stored(dallas_db):
    db = sqlite3.connect(dallas_db)
    cols = [r[1] for r in db.execute("PRAGMA table_info(property)")]
    assert not any("owner" in c.lower() for c in cols)
    dump = "\n".join(db.iterdump())
    assert "OWNER" not in dump


def test_meta(dallas_db):
    db = sqlite3.connect(dallas_db)
    meta = dict(db.execute("SELECT key, value FROM county_meta"))
    assert meta["tax_year"] == "2026"
    assert meta["rows"] == "9"


def test_locations(rows, dallas_db):
    assert rows["S0001"]["lat"] == pytest.approx(32.89, abs=1e-5)
    assert rows["C0001"]["lat"] is None
    meta = dict(sqlite3.connect(dallas_db).execute("SELECT key, value FROM county_meta"))
    assert meta["located"] == "1"


def test_canonical_detail(dallas_db):
    impr = sqlite3.connect(dallas_db).execute(
        "SELECT kind, description, condition, year_built, eff_year_built, pool FROM improvement"
        " WHERE account='S0001' ORDER BY kind, seq"
    ).fetchall()
    assert impr == [("main", "14", "GOOD", 2010, 2012, 1), ("other", "DETACHED GARAGE", None, 2010, None, None),
                    ("other", "STORAGE BUILDING", None, None, None, None)]  # 1000 = placeholder year
    rows = read_rows(dallas_db)
    assert rows["S0001"]["prior_market_val"] == 380000
    sql = "SELECT code FROM exemption WHERE account='S0001' ORDER BY code"
    codes = sqlite3.connect(dallas_db).execute(sql).fetchall()
    assert [c[0] for c in codes] == ["HS", "OV65"]
