"""Collin CAD AppraisalData-Public-<year>.csv -> canonical tables.

Bedrooms and baths are not in AppraisalData-Public, and its lot size is
mostly blank; they come from the optional `details` file
(CCAD-Appraisal-Data.csv, joined on prop_id), whose `baths` field is a
decimal count (2.5 = 2 full + 1 half).
"""
import os

from app.stats import parse_date, to_float, to_int
from pipeline.build_db import open_table

SQFT_PER_ACRE = 43560
EXEMPT_NAMES = {"HS": "Homestead", "OV65": "Over 65", "DP": "Disabled person"}


def split_baths(value):
    b = to_float(value)
    if b is None:
        return None, None
    full = int(b)
    return full, 1 if b - full >= 0.5 else 0


def val(r, prefix):
    return {
        "land_val": to_float(r[f"{prefix}Land"]), "improvement_val": to_float(r[f"{prefix}Imprv"]),
        "market_val": to_float(r[f"{prefix}Market"]), "appraised_val": to_float(r[f"{prefix}Appraised"]),
        "assessed_val": to_float(r[f"{prefix}Assessed"]),
    }


def build(out, cfg, log=print):
    src, fmt, year = cfg["source"], cfg["date_format"], cfg["tax_year"]

    details = {}
    if cfg.get("details") and os.path.exists(cfg["details"]):
        log("  details (beds/baths)")
        for r in open_table(cfg["details"], os.path.basename(cfg["details"])):
            beds = to_int(r.get("beds"))
            full, half = split_baths(r.get("baths"))
            # 0 means "not recorded" in this file, not a zero-bedroom house.
            details[r["prop_id"].strip()] = {
                "beds": beds or None, "full_baths": full or None, "half_baths": half if full else None,
                "stories": (r.get("stories") or "").strip() or None,
                "eff_year_built": to_int(r.get("eff_yr_blt")) or None,
                "lot": to_float(r.get("land_sqft")) or None,
            }
    else:
        log("  no details file; beds/baths will be empty")

    log("  appraisal data")
    for r in open_table(src, os.path.basename(src)):
        acct = (r.get("propID") or "").strip()
        if not acct:
            continue
        d = details.get(acct, {})
        street = " ".join(p for p in (r["situsStreetPrefix"].strip(), r["situsStreetName"].strip(),
                                      r["situsStreetSuffix"].strip()) if p)
        out.add("property", {
            "account": acct, "parcel_id": acct,
            "street_num": r["situsBldgNum"].strip(), "street_name": street,
            "unit": (r.get("situsUnit") or "").strip() or None,
            "city": r["situsCity"].strip(), "zip": r["situsZip"].strip()[:5],
            "state_cd": r["propCategoryCode"].strip(), "nbhd": r["nbhdCode"].strip(),
            "legal_desc": (r.get("legalDescription") or "").strip() or None,
        })
        out.add("valuation", {"account": acct, "tax_year": to_int(r.get("currValYear")) or year, **val(r, "currVal")})
        prev_year = to_int(r.get("prevValYear"))
        if prev_year:
            out.add("valuation", {"account": acct, "tax_year": prev_year, **val(r, "prevVal")})

        out.add("improvement", {
            "account": acct, "seq": 1, "kind": "main",
            "year_built": to_int(r["imprvYearBuilt"]), "eff_year_built": d.get("eff_year_built"),
            "living_sqft": to_float(r["imprvMainArea"]),
            "beds": d.get("beds"), "full_baths": d.get("full_baths"), "half_baths": d.get("half_baths"),
            "stories": d.get("stories"), "quality": (r.get("imprvClassCd") or "").strip() or None,
            "pool": int((r.get("imprvPoolFlag") or "").strip().upper() == "T"),
        })

        lot = to_float(r["landSizeSqft"]) or d.get("lot")
        if not lot:
            acres = to_float(r["landSizeAcres"])
            lot = acres * SQFT_PER_ACRE if acres else None
        out.add("land", {"account": acct, "seq": 1, "size_sqft": lot, "value": to_float(r["currValLand"])})

        codes = {c.strip().upper() for c in (r.get("exemptCodes") or "").split(",") if c.strip()}
        if r["exemptHmstdFlag"].strip().upper() in ("T", "TRUE", "Y"):
            codes.add("HS")
        for code in sorted(codes):
            out.add("exemption", {"account": acct, "tax_year": year, "code": code,
                                  "description": EXEMPT_NAMES.get(code)})

        deed = parse_date(r["deedEffDate"], fmt)
        if deed:
            out.add("deed", {"account": acct, "transfer_date": deed,
                             "deed_type": (r.get("deedTypeCd") or "").strip() or None,
                             "instrument": (r.get("deedNum") or "").strip() or None})
