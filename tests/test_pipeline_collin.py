import pytest

from tests.conftest import read_rows


@pytest.fixture(scope="module")
def rows(collin_db):
    return read_rows(collin_db)


def test_home_with_details(rows):
    r = rows["1001"]
    assert (r["street_num"], r["street_name"], r["zip"]) == ("10", "SAMPLE LN", "75074")
    assert (r["beds"], r["full_baths"], r["half_baths"]) == (4, 2, 1)
    assert r["appraised_val"] == 420000 and r["prior_market_val"] == 395000
    assert r["homestead"] == 1
    assert r["lot_sqft"] == 7200
    assert r["deed_date"] == "2020-05-01"


def test_lot_and_missing_details(rows):
    r = rows["1002"]
    assert r["beds"] is None and r["full_baths"] is None
    assert r["lot_sqft"] == 8712  # from the details file
    assert r["homestead"] == 0
    assert r["prior_market_val"] is None


def test_zero_means_not_recorded(rows):
    r = rows["1003"]
    assert r["beds"] is None and r["full_baths"] is None
    assert r["street_name"] == "N SAMPLE LN"
    assert r["deed_date"] is None


def test_exemption_codes(collin_db):
    import sqlite3

    sql = "SELECT code FROM exemption WHERE account='1001' ORDER BY code"
    codes = sqlite3.connect(collin_db).execute(sql).fetchall()
    assert [c[0] for c in codes] == ["HS", "OV65"]


@pytest.mark.parametrize("acct", ["1001", "1002", "1003"])
def test_every_account_has_one_main_improvement(collin_db, acct):
    assert read_rows(collin_db, "improvement")[acct]["kind"] == "main"
