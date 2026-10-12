import pytest

from tests.conftest import read_rows


@pytest.fixture(scope="module")
def rows(denton_db):
    return read_rows(denton_db)


def test_home(rows):
    r = rows["247593"]
    assert (r["street_num"], r["street_name"], r["zip"]) == ("3004", "SOUTHMOOR TRL", "75022")
    assert r["nbhd"] == "DC07218"
    assert (r["beds"], r["full_baths"], r["half_baths"]) == (4, 2, 1)
    assert r["deed_date"] == "2018-11-20"
    assert r["homestead"] == 1
    assert r["land_val"] == 120000
    assert r["parcel_id"] == "247593"


def test_duplicate_owner_rows_collapse(rows):
    assert sorted(rows) == ["247593", "8"]


def test_other_property(rows):
    r = rows["8"]
    assert r["state_cd"] == "C1"
    assert r["nbhd"] is None
    assert r["full_baths"] is None  # 'Allowance' is not a count
    assert r["homestead"] == 0
    assert r["lot_sqft"] == 1302


def test_canonical_detail(denton_db):
    main = read_rows(denton_db, "improvement")["247593"]
    assert (main["condition"], main["eff_year_built"], main["quality"]) == ("Good", 2010, "1750S1,GB2")
