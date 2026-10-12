import sqlite3

import pytest

from app.config import normalize
from pipeline.build_db import build
from tests.conftest import county_cfg

HEADER = ("RP|Appraisal_Year|Account_Num|Owner_Name|Owner_Address|Owner_CityState|Owner_Zip|Situs_Address|"
          "Property_Class|Deed_Date|Land_Value|Improvement_Value|Total_Value|Living_Area|Year_Built|Land_Acres|"
          "Land_SqFt|Appraised_Value|GIS_Link")
ROWS = [
    # owner-occupied: ZIP and city come from the owner address
    "R|2026|1309|OWNER A|704 E WEATHERFORD ST|FORT WORTH ,  TX|76102-1350|704 E WEATHERFORD ST|A|2016-08-22|"
    "110000|446381|556381|2550.00|1910|0.1148|5000.00|500000|14437-29-32",
    # landlord-owned: ZIP and city stay empty
    "R|2026|6483|OWNER B|1 ELSEWHERE RD|DALLAS ,  TX|75201|922 E  PEACH ST|A|1900-12-31|"
    "11840|89274|101114|939.00|1910|0.0340||101114|14437-124-1B",
]


@pytest.fixture(scope="module")
def rows(tmp_path_factory):
    openpyxl = pytest.importorskip("openpyxl")
    d = tmp_path_factory.mktemp("tarrant")
    (d / "roll.txt").write_text("\n".join([HEADER] + ROWS) + "\n")
    (d / "ex.txt").write_text("TaxYear|Account_Num|GIS_Link|Exemption|ExemptionPct\n"
                              "2025|00001309|14437-29-32|HOMESTEAD GENERAL 11.13(b)|100\n"
                              "2025|00006483|14437-124-1B|Tax Code 11.26 Adjustments|100\n")
    wb = openpyxl.Workbook()
    wb.active.append(["Tax Year", "PIN", "Market Area", "Situs Address"])
    wb.active.append([2026, "00001309", "4T050C", "704 E WEATHERFORD ST"])
    wb.save(d / "comp.xlsx")
    cfg = county_cfg(str(d / "t.db"), adapter="tarrant", date_format="%Y-%m-%d", source=str(d / "roll.txt"),
                     market_areas=str(d / "comp.xlsx"), exemptions=str(d / "ex.txt"))
    build(normalize("tarrant", cfg), log=lambda *a: None)
    db = sqlite3.connect(d / "t.db")
    db.row_factory = sqlite3.Row
    return {r["account"]: dict(r) for r in db.execute("SELECT * FROM property")}


def test_owner_occupied(rows):
    r = rows["1309"]
    assert (r["street_num"], r["street_name"]) == ("704", "E WEATHERFORD ST")
    assert (r["city"], r["zip"]) == ("FORT WORTH", "76102")
    assert r["nbhd"] == "4T050C"
    assert r["appraised_val"] == 556381  # Total_Value, not the capped Appraised_Value
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
    assert r["lot_sqft"] == pytest.approx(0.0340 * 43560)
