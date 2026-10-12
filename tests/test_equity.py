import sqlite3

import pytest

from app import equity
from app.db import SCHEMA, SUMMARY_SQL

BASE_LAT, BASE_LON = 32.89, -96.94
MI = 1 / 69.0  # degrees of latitude per mile


def home(account, *, dlat_mi=0.0, sqft=2000, year=2010, eff=None, val=400000, impr=300000, land=100000,
         quality="R04", nbhd="N1", state="A1", lat=True):
    return {"account": account, "street_num": "1", "street_name": f"{account} ST", "city": "TESTVILLE",
            "zip": "75000", "state_cd": state, "nbhd": nbhd, "deed_date": None, "appraised_val": val,
            "improvement_val": impr, "land_val": land, "market_val": val, "prior_market_val": None,
            "beds": 3, "full_baths": 2, "half_baths": 0, "living_sqft": sqft, "year_built": year,
            "eff_year_built": eff, "quality": quality, "condition": None, "lot_sqft": 7000, "homestead": 0,
            "parcel_id": account, "lat": BASE_LAT + dlat_mi * MI if lat else None, "lon": BASE_LON if lat else None}


def make_db(homes):
    db = sqlite3.connect(":memory:")
    db.executescript(SCHEMA)
    db.execute(SUMMARY_SQL, {"tax_year": 2026})  # creates property_summary with the real columns
    cols = [r[1] for r in db.execute("PRAGMA table_info(property_summary)")]
    db.executemany(f"INSERT INTO property_summary VALUES ({','.join('?' * len(cols))})",
                   [tuple(h.get(c) for c in cols) for h in homes])
    db.row_factory = sqlite3.Row
    return db


def subject_of(db, account="SUBJ"):
    return dict(db.execute("SELECT * FROM property_summary WHERE account = ?", [account]).fetchone())


def test_adjustment_grid_math():
    s = home("SUBJ", sqft=2000, year=2010, land=100000)
    c = home("C1", sqft=2200, year=2000, val=440000, impr=330000, land=110000)
    row = equity.adjust(s, c, use_effective=False)
    assert row["improvement_rate"] == 150.0              # 330,000 / 2,200
    assert row["size_adj"] == -30000                     # (2000 - 2200) * 150
    assert row["age_adj"] == 16500                       # 330,000 * 0.5% * (2010 - 2000)
    assert row["land_adj"] == -10000                     # 100,000 - 110,000
    assert row["adjusted_val"] == 440000 - 30000 + 16500 - 10000


def test_median_and_reduction():
    homes = [home("SUBJ", val=450000)] + [home(f"C{i}", dlat_mi=0.1, val=v) for i, v in
                                         enumerate([380000, 390000, 400000, 410000, 420000, 430000])]
    db = make_db(homes)
    out = equity.analyze(db, subject_of(db))
    assert out["available"] and out["count"] == 6
    # identical size/age/land, so adjusted == appraised; even count -> mean of the middle two
    assert out["median_adjusted"] == 405000
    assert out["supports_reduction"] and out["difference"] == 45000
    assert out["search"] == {"method": "radius", "radius_mi": 0.5}


def test_selection_filters_and_radius_expansion():
    homes = [home("SUBJ")]
    homes += [home(f"NEAR{i}", dlat_mi=0.2) for i in range(3)]          # within 0.5 mi
    homes += [home(f"MID{i}", dlat_mi=0.8) for i in range(3)]           # needs 1 mi
    homes += [home("BIG", dlat_mi=0.1, sqft=2600),                      # outside ±20% size
              home("OLD", dlat_mi=0.1, year=1990),                      # outside ±10 years
              home("LUX", dlat_mi=0.1, quality="R07"),                  # different quality grade
              home("SHOP", dlat_mi=0.1, state="F1"),                    # commercial
              home("FAR", dlat_mi=5)]                                   # beyond 3 mi
    db = make_db(homes)
    out = equity.analyze(db, subject_of(db))
    assert out["search"]["radius_mi"] == 1.0
    assert sorted(c["account"] for c in out["comps"]) == ["MID0", "MID1", "MID2", "NEAR0", "NEAR1", "NEAR2"]
    assert [c["account"] for c in out["comps"]][:3] == ["NEAR0", "NEAR1", "NEAR2"]  # nearest ranked first


def test_max_comps_cap():
    db = make_db([home("SUBJ")] + [home(f"C{i:02}", dlat_mi=0.01 * i) for i in range(25)])
    out = equity.analyze(db, subject_of(db))
    assert out["count"] == equity.PARAMS["max_comps"]
    assert out["comps"][0]["account"] == "C00"


def test_effective_year_used_when_available():
    db = make_db([home("SUBJ", year=1970, eff=2005)] +
                 [home(f"C{i}", dlat_mi=0.1, year=1960, eff=2000) for i in range(5)] +
                 [home("NOEFF", dlat_mi=0.1, year=1970)])
    out = equity.analyze(db, subject_of(db))
    assert out["criteria"]["year_basis"] == "effective year built"
    assert "NOEFF" not in [c["account"] for c in out["comps"]]
    assert out["comps"][0]["age_adj"] == round(300000 * 0.005 * 5)


def test_neighborhood_fallback_without_location():
    db = make_db([home("SUBJ", lat=False)] + [home(f"C{i}", lat=False) for i in range(5)] +
                 [home("OTHER", lat=False, nbhd="N2")])
    out = equity.analyze(db, subject_of(db))
    assert out["search"] == {"method": "neighborhood", "nbhd": "N1"}
    assert out["count"] == 5 and all(c["distance_mi"] is None for c in out["comps"])


def test_too_few_comps():
    db = make_db([home("SUBJ")] + [home(f"C{i}", dlat_mi=0.1) for i in range(3)])
    out = equity.analyze(db, subject_of(db))
    assert out["available"] is False and "only 3" in out["reason"]


@pytest.mark.parametrize("field", ["living_sqft", "improvement_val"])
def test_missing_subject_data(field):
    s = home("SUBJ")
    s[field] = None
    out = equity.analyze(make_db([s]), s)
    assert out["available"] is False and field in out["reason"]


def test_distance():
    assert equity.distance_mi(32.89, -96.94, 32.89 + 1 / 69.0, -96.94) == pytest.approx(1.0, rel=0.01)
