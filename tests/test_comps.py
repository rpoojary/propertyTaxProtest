import sqlite3

import pytest

from app.comps import find_comps, get_property, search
from app.db import connect_ro


@pytest.fixture
def db(dallas_db):
    conn = connect_ro(dallas_db)
    yield conn
    conn.close()


def accounts(rows):
    return sorted(r["account"] for r in rows)


def test_neighborhood_set(db):
    res = find_comps(db, get_property(db, "S0001"), 2026)["neighborhood"]
    # C0003 transferred before 2025, C0005 is commercial, C0007 has no value.
    assert accounts(res["comps"]) == ["C0001", "C0002", "C0006"]
    assert res["stats"]["median"] == 350000
    assert res["criteria"] == {"nbhd": "N1", "deed_since": "2025-01-01", "state_category": "A"}


def test_zip_set(db):
    res = find_comps(db, get_property(db, "S0001"), 2026)["zip"]
    assert accounts(res["comps"]) == ["C0001", "C0002", "C0004"]
    assert res["criteria"]["sqft_low"] == 1700 and res["criteria"]["sqft_high"] == 2300
    assert res["stats"]["median"] == 350000


def test_all_similar_ignores_deed_date(db):
    res = find_comps(db, get_property(db, "S0001"), 2026)["all_similar"]
    assert "comps" not in res
    assert res["stats"]["count"] == 3  # C0001, C0003, C0004 (C0002 has a half bath)
    assert res["stats"]["median"] == 320000


def test_since_follows_tax_year(db):
    res = find_comps(db, get_property(db, "S0001"), 2021)["neighborhood"]
    assert res["criteria"]["deed_since"] == "2020-01-01"
    assert "C0003" in accounts(res["comps"])


def test_search(db):
    assert [r["account"] for r in search(db, "100 test")] == ["S0001"]
    assert [r["account"] for r in search(db, "S000")] == ["S0001"]
    assert [r["account"] for r in search(db, "wild_card")] == ["C0008"]
    assert search(db, "wildxcard") == []  # "_" is literal, not a wildcard
    assert search(db, "%%%") == []
    assert search(db, "ab") == []


def test_connection_is_read_only(db):
    with pytest.raises(sqlite3.OperationalError):
        db.execute("DELETE FROM property")
