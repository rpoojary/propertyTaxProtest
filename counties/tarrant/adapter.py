"""Tarrant Appraisal District residential roll -> app DB.

Sources (see docs/data-sources.md):
  source        PropertyData(Delimited)_R.ZIP, pipe-delimited current roll
  market_areas  <year>ResidentialCompAttributeData zip (xlsx): TAD market
                area per PIN, used as the neighborhood code
  exemptions    PropertyData_Exemptions_<year>(Certified).ZIP: homestead

TAD publishes no bedroom/bath counts and no situs ZIP or city for homes.
ZIP and city are taken from the owner's mailing address only when it is the
same street address as the property (owner-occupied); otherwise they stay
empty rather than guessed.
"""
import io
import os
import re
import zipfile

from app.stats import parse_date, to_float, to_int
from pipeline.build_db import insert_properties, open_table


def norm_addr(s):
    return re.sub(r"\s+", " ", (s or "").upper()).strip()


def split_situs(addr):
    """'704 E WEATHERFORD ST' -> ('704', 'E WEATHERFORD ST')."""
    addr = norm_addr(addr)
    m = re.match(r"^(\d+[A-Z]?)\s+(.*)$", addr)
    return (m.group(1), m.group(2)) if m else ("", addr)


def pin(account):
    return account.strip().zfill(8)


def load_market_areas(path, log=print):
    import openpyxl

    if not str(path).lower().endswith(".xlsx"):  # TAD ships the workbook inside a .zip
        zf = zipfile.ZipFile(path)
        name = next(n for n in zf.namelist() if n.lower().endswith(".xlsx"))
        path = io.BytesIO(zf.read(name))
    wb = openpyxl.load_workbook(path, read_only=True)
    rows = wb.worksheets[0].iter_rows(values_only=True)
    header = [str(h).strip() if h else "" for h in next(rows)]
    i_pin, i_area = header.index("PIN"), header.index("Market Area")
    out = {str(r[i_pin]).strip().zfill(8): str(r[i_area]).strip() for r in rows if r[i_pin] and r[i_area]}
    wb.close()
    return out


def build(conn, cfg, log=print):
    fmt = cfg["date_format"]

    areas = {}
    if cfg.get("market_areas") and os.path.exists(cfg["market_areas"]):
        log("  market areas")
        areas = load_market_areas(cfg["market_areas"], log)

    homestead = set()
    if cfg.get("exemptions") and os.path.exists(cfg["exemptions"]):
        log("  exemptions")
        for r in open_table(cfg["exemptions"], delimiter="|"):
            if (r.get("Exemption") or "").strip().upper().startswith("HOMESTEAD"):
                homestead.add(pin(r["Account_Num"]))

    log("  residential roll")

    def rows():
        for r in open_table(cfg["source"], delimiter="|"):
            acct = (r.get("Account_Num") or "").strip()
            if not acct:
                continue
            num, street = split_situs(r["Situs_Address"])
            owner_occupied = street and norm_addr(r["Owner_Address"]) == norm_addr(r["Situs_Address"])
            city = zip5 = None
            if owner_occupied:
                city = (r["Owner_CityState"] or "").split(",")[0].strip() or None
                zip5 = (r["Owner_Zip"] or "").strip()[:5] or None
            acres = to_float(r["Land_Acres"])
            yield {
                "account": acct,
                "street_num": num,
                "street_name": street,
                "city": city,
                "zip": zip5,
                "state_cd": (r["Property_Class"] or "").strip(),
                "nbhd": areas.get(pin(acct)),
                "deed_date": parse_date(r["Deed_Date"], fmt),
                # Total_Value is the market value; TAD's Appraised_Value can
                # carry the homestead cap.
                "appraised_val": to_float(r["Total_Value"]),
                "improvement_val": to_float(r["Improvement_Value"]),
                "land_val": to_float(r["Land_Value"]),
                "beds": None,
                "full_baths": None,
                "half_baths": None,
                "living_sqft": to_float(r["Living_Area"]) or None,
                "year_built": to_int(r["Year_Built"]) or None,
                "lot_sqft": to_float(r["Land_SqFt"]) or (acres * 43560 if acres else None),
                "homestead": int(pin(acct) in homestead),
                "parcel_id": (r["GIS_Link"] or "").strip() or None,
            }

    return insert_properties(conn, rows())
