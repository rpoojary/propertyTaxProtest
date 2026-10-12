"""Collin CAD AppraisalData-Public-<year>.csv -> app DB.

Bedrooms and baths are not in AppraisalData-Public, and its lot size is
mostly blank; they come from the optional `details` file
(CCAD-Appraisal-Data.csv, joined on prop_id), whose `baths` field is a
decimal count (2.5 = 2 full + 1 half).
"""
import os

from app.stats import parse_date, to_float, to_int
from pipeline.build_db import insert_properties, open_table

SQFT_PER_ACRE = 43560


def split_baths(value):
    b = to_float(value)
    if b is None:
        return None, None
    full = int(b)
    return full, 1 if b - full >= 0.5 else 0


def build(conn, cfg, log=print):
    src, fmt = cfg["source"], cfg["date_format"]

    details = {}
    if cfg.get("details") and os.path.exists(cfg["details"]):
        log("  details (beds/baths)")
        for r in open_table(cfg["details"], os.path.basename(cfg["details"])):
            beds = to_int(r.get("beds"))
            full, half = split_baths(r.get("baths"))
            # 0 means "not recorded" in this file, not a zero-bedroom house.
            details[r["prop_id"].strip()] = (beds or None, full or None, half if full else None,
                                             to_float(r.get("land_sqft")) or None)
    else:
        log("  no details file; beds/baths will be empty")

    log("  appraisal data")

    def rows():
        for r in open_table(src, os.path.basename(src)):
            acct = (r.get("propID") or "").strip()
            if not acct:
                continue
            street = " ".join(p for p in (r["situsStreetPrefix"].strip(), r["situsStreetName"].strip(),
                                          r["situsStreetSuffix"].strip()) if p)
            beds, full, half, detail_lot = details.get(acct, (None,) * 4)
            lot = to_float(r["landSizeSqft"]) or detail_lot
            if not lot:
                acres = to_float(r["landSizeAcres"])
                lot = acres * SQFT_PER_ACRE if acres else None
            yield {
                "account": acct,
                "street_num": r["situsBldgNum"].strip(),
                "street_name": street,
                "city": r["situsCity"].strip(),
                "zip": r["situsZip"].strip()[:5],
                "state_cd": r["propCategoryCode"].strip(),
                "nbhd": r["nbhdCode"].strip(),
                "deed_date": parse_date(r["deedEffDate"], fmt),
                "appraised_val": to_float(r["currValAppraised"]),
                "improvement_val": to_float(r["currValImprv"]),
                "land_val": to_float(r["currValLand"]),
                "beds": beds,
                "full_baths": full,
                "half_baths": half,
                "living_sqft": to_float(r["imprvMainArea"]),
                "year_built": to_int(r["imprvYearBuilt"]),
                "lot_sqft": lot,
                "homestead": int(r["exemptHmstdFlag"].strip().upper() in ("T", "TRUE", "Y")),
                "parcel_id": acct,
            }

    return insert_properties(conn, rows())
