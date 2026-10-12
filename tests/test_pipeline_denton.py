import sqlite3

import pytest

from app.config import normalize
from pipeline.build_db import build
from tests.conftest import county_cfg

CSV_HEADER = ("pYear,pid,stateCodes,situsStreetNumb,situsStreetPrefix,situsStreetName,situsStreetSuff,situsCity,"
              "situsZip,exemptions,deedDt,ownerAppraisedValue,improvementValue,landHSValue,landNHSValue,"
              "imprvMainArea,imprvActualYearBuilt,land_sqft,landTotalSqft")
HOME = ("2026,247593,A1,3004,,SOUTHMOOR,TRL,FLOWER MOUND,75022-1055,HS,2018-11-20 0:00:00,"
        "820000,700000,120000,0,3376,2004,12079.188,12080")
CSV_ROWS = [
    HOME,
    HOME,  # second owner row repeats the full value
    '2026,8,"C1,F1",100,N,ELM,ST,DENTON,76201,"OTHER,EX-XV",,50,0,0,50,0,0,,1302',
]


def info_line(pid, hood):
    line = [" "] * 9923
    line[0:12] = str(pid).zfill(12)
    line[1685:1695] = hood.ljust(10)
    return "".join(line) + "\n"


def attr_line(pid, desc, code):
    return f"{str(pid).zfill(12)}2026{'1'.zfill(12)}{'1'.zfill(12)}{'1'.zfill(12)}{desc:<25}{code:<10}\n"


@pytest.fixture(scope="module")
def rows(tmp_path_factory):
    d = tmp_path_factory.mktemp("denton")
    (d / "nightly.csv").write_text("\n".join([CSV_HEADER] + CSV_ROWS) + "\n")
    det = d / "export"
    det.mkdir()
    (det / "2026-07-24_2026_APPRAISAL_INFO.TXT").write_text(info_line(247593, "DC07218") + info_line(8, ""))
    (det / "2026-07-24_2026_APPRAISAL_IMPROVEMENT_DETAIL_ATTR.TXT").write_text(
        attr_line(247593, "Foundation", "SLAB") + attr_line(247593, "Bedrooms", "4") +
        attr_line(247593, "Plumbing", "2.5") + attr_line(247593, "Plumbing", "1") +
        attr_line(8, "Plumbing", "Allowance"))
    cfg = county_cfg(str(d / "d.db"), adapter="denton", date_format="%Y-%m-%d", source=str(d / "nightly.csv"),
                     details=str(det))
    build(normalize("denton", cfg), log=lambda *a: None)
    db = sqlite3.connect(d / "d.db")
    db.row_factory = sqlite3.Row
    return {r["account"]: dict(r) for r in db.execute("SELECT * FROM property")}


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
