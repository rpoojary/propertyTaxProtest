import pytest

from tests.conftest import read_rows


@pytest.fixture(scope="module")
def rows(tarrant_db):
    return read_rows(tarrant_db)


def test_owner_occupied(rows):
    r = rows["1309"]
    assert (r["street_num"], r["street_name"]) == ("704", "E WEATHERFORD ST")
    assert (r["city"], r["zip"]) == ("FORT WORTH", "76102")
    assert r["nbhd"] == "4T050C"
    assert r["appraised_val"] == 556381  # Total_Value, not the capped Appraised_Value
    assert r["prior_market_val"] == 500000
    assert r["homestead"] == 1
    assert r["parcel_id"] == "14437-29-32"
    assert r["beds"] is None and r["full_baths"] is None


def test_not_owner_occupied(rows):
    r = rows["6483"]
    assert r["street_name"] == "E PEACH ST"
    assert r["zip"] is None and r["city"] is None
    assert r["nbhd"] is None
    assert r["deed_date"] is None  # 1900 placeholder
    assert r["homestead"] == 0
    assert r["prior_market_val"] is None
    assert r["lot_sqft"] == pytest.approx(0.0340 * 43560)


def test_canonical_detail(tarrant_db):
    main = read_rows(tarrant_db, "improvement")["1309"]
    assert (main["quality"], main["condition"], main["eff_year_built"], main["pool"]) == ("Good", "Average", 1995, 1)
    vals = read_rows(tarrant_db, "valuation", key="tax_year")
    assert vals[2025]["assessed_val"] == 480000
