"""Shared fixtures: each county's synthetic raw export, built into a DB once per session."""
import os
import sqlite3
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.config import normalize  # noqa: E402
from pipeline.build_db import build  # noqa: E402

FIXTURES = os.path.join(ROOT, "tests", "fixtures")


def county_cfg(db, **extra):
    cfg = {
        "name": "Test County", "cad_name": "Test Central Appraisal District", "cad_abbrev": "TCAD",
        "cad_address": "1 Main St, Testville, TX 75000", "protest_url": "https://example.test/",
        "tax_year": 2026, "date_format": "%m/%d/%Y", "adapter": "dallas",
        "source": os.path.join(FIXTURES, "dallas"), "db": db,
    }
    cfg.update(extra)
    return cfg


def build_fixture(cid, cfg):
    build(normalize(cid, cfg), log=lambda *a: None)
    return cfg["db"]


def read_rows(db_path, table="property_summary", key="account"):
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    rows = {r[key]: dict(r) for r in db.execute(f"SELECT * FROM {table}")}
    db.close()
    return rows


@pytest.fixture(scope="session")
def dallas_db(tmp_path_factory):
    from pipeline.geo import LCC
    from tests.shapefile_util import PRJ_2276, square, write_zip

    tmp = tmp_path_factory.mktemp("dallas")
    x, y = LCC.from_prj(PRJ_2276).forward(32.89, -96.94)
    parcels = write_zip(tmp / "PARCEL_GEOM.zip", "Acct", [("S0001", [square(x, y, 40)]), ("NOPE", [square(x, y, 9)])])
    return build_fixture("dallas", county_cfg(str(tmp / "dallas.db"), parcels=str(parcels), parcels_key="Acct"))


@pytest.fixture(scope="session")
def collin_db(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("collin")
    src = os.path.join(FIXTURES, "collin")
    return build_fixture("collin", county_cfg(
        str(tmp / "collin.db"), adapter="collin", date_format="%Y-%m-%d",
        source=os.path.join(src, "AppraisalData-Public-2026.csv"),
        details=os.path.join(src, "CCAD-Appraisal-Data.csv")))


TARRANT_HEADER = ("RP|Appraisal_Year|Account_Num|Owner_Name|Owner_Address|Owner_CityState|Owner_Zip|Situs_Address|"
                  "Property_Class|Deed_Date|Land_Value|Improvement_Value|Total_Value|Living_Area|Year_Built|Land_Acres|"
                  "Land_SqFt|Appraised_Value|GIS_Link|Swimming_Pool_Ind|Instrument_No")
TARRANT_ROWS = [
    # owner-occupied: ZIP and city come from the owner address
    "R|2026|1309|OWNER A|704 E WEATHERFORD ST|FORT WORTH ,  TX|76102-1350|704 E WEATHERFORD ST|A|2016-08-22|"
    "110000|446381|556381|2550.00|1910|0.1148|5000.00|500000|14437-29-32|Y|D216201720",
    # landlord-owned: ZIP and city stay empty
    "R|2026|6483|OWNER B|1 ELSEWHERE RD|DALLAS ,  TX|75201|922 E  PEACH ST|A|1900-12-31|"
    "11840|89274|101114|939.00|1910|0.0340||101114|14437-124-1B|N|",
]
TARRANT_PRIOR = ("RP|Appraisal_Year|Account_Num|Land_Value|Improvement_Value|Total_Value|Appraised_Value\n"
                 "R|2025|00001309|      100000|      400000|      500000|      480000\n")


@pytest.fixture(scope="session")
def tarrant_db(tmp_path_factory):
    openpyxl = pytest.importorskip("openpyxl")
    d = tmp_path_factory.mktemp("tarrant")
    (d / "roll.txt").write_text("\n".join([TARRANT_HEADER] + TARRANT_ROWS) + "\n")
    (d / "prior.txt").write_text(TARRANT_PRIOR)
    (d / "ex.txt").write_text("TaxYear|Account_Num|GIS_Link|Exemption|ExemptionPct\n"
                              "2025|00001309|14437-29-32|HOMESTEAD GENERAL 11.13(b)|100\n"
                              "2025|00006483|14437-124-1B|Tax Code 11.26 Adjustments|100\n")
    wb = openpyxl.Workbook()
    wb.active.append(["Tax Year", "PIN", "Market Area", "Situs Address", "Quality", "Condition",
                      "Effective Year Built"])
    wb.active.append([2026, "00001309", "4T050C", "704 E WEATHERFORD ST", "Good", "Average", 1995])
    wb.save(d / "comp.xlsx")
    return build_fixture("tarrant", county_cfg(
        str(d / "t.db"), adapter="tarrant", date_format="%Y-%m-%d", source=str(d / "roll.txt"),
        prior_source=str(d / "prior.txt"), market_areas=str(d / "comp.xlsx"), exemptions=str(d / "ex.txt")))


DENTON_HEADER = ("pYear,pid,stateCodes,situsStreetNumb,situsStreetPrefix,situsStreetName,situsStreetSuff,situsCity,"
                 "situsZip,exemptions,deedDt,deedType,instrumentNum,ownerMarketValue,ownerAppraisedValue,"
                 "ownerNetAppraisedValue,improvementValue,landHSValue,landNHSValue,imprvMainArea,imprvActualYearBuilt,"
                 "imprvEffYearBuilt,imprvClasses,land_sqft,landTotalSqft,confidential")
DENTON_HOME = ("2026,247593,A1,3004,,SOUTHMOOR,TRL,FLOWER MOUND,75022-1055,HS,2018-11-20 0:00:00,GNV,2018-137347,"
               "820000,820000,800000,700000,120000,0,3376,2004,2010,\"1750S1,GB2\",12079.188,12080,0")
DENTON_ROWS = [
    DENTON_HOME,
    DENTON_HOME,  # second owner row repeats the full value
    '2026,8,"C1,F1",100,N,ELM,ST,DENTON,76201,"OTHER,EX-XV",,,,50,50,50,0,0,50,0,0,,,,1302,0',
    # confidential owner (Tax Code §25.025): kept in canonical tables, never in the app
    '2026,9,A1,3010,,SOUTHMOOR,TRL,FLOWER MOUND,75022,HS,2020-01-01,WD,X,800000,800000,800000,700000,100000,0,'
    '3300,2004,2010,GB2,12000,12000,1',
]


def denton_info_line(pid, hood):
    line = [" "] * 9923
    line[0:12] = str(pid).zfill(12)
    line[1685:1695] = hood.ljust(10)
    return "".join(line) + "\n"


def denton_attr_line(pid, desc, code):
    return f"{str(pid).zfill(12)}2026{'1'.zfill(12)}{'1'.zfill(12)}{'1'.zfill(12)}{desc:<25}{code:<10}\n"


@pytest.fixture(scope="session")
def denton_db(tmp_path_factory):
    d = tmp_path_factory.mktemp("denton")
    (d / "nightly.csv").write_text("\n".join([DENTON_HEADER] + DENTON_ROWS) + "\n")
    det = d / "export"
    det.mkdir()
    (det / "2026-07-24_2026_APPRAISAL_INFO.TXT").write_text(
        denton_info_line(247593, "DC07218") + denton_info_line(8, ""))
    (det / "2026-07-24_2026_APPRAISAL_IMPROVEMENT_DETAIL_ATTR.TXT").write_text(
        denton_attr_line(247593, "Foundation", "SLAB") + denton_attr_line(247593, "Bedrooms", "4") +
        denton_attr_line(247593, "Plumbing", "2.5") + denton_attr_line(247593, "Plumbing", "1") +
        denton_attr_line(247593, "Condition", "Good") + denton_attr_line(8, "Plumbing", "Allowance"))
    return build_fixture("denton", county_cfg(str(d / "d.db"), adapter="denton", date_format="%Y-%m-%d",
                                              source=str(d / "nightly.csv"), details=str(det)))


@pytest.fixture(scope="session")
def counties(dallas_db, tmp_path_factory):
    missing = str(tmp_path_factory.mktemp("none") / "missing.db")
    return {
        "dallas": normalize("dallas", county_cfg(dallas_db)),
        "tarrant": normalize("tarrant", county_cfg(missing, adapter=None, name="Not Built County")),
    }
