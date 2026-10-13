"""Dallas CAD certified CSV export (DCAD<year>_CURRENT.zip) -> canonical tables.

Tables used (all keyed by ACCOUNT_NUM): ACCOUNT_INFO, ACCOUNT_APPRL_YEAR,
RES_DETAIL, RES_ADDL, LAND, APPLIED_STD_EXEMPT. Layout: the
DCAD_Certified_READ_ME.rtf inside the zip, and docs/data-sources.md.
"""
from app.stats import parse_date, to_float, to_int
from pipeline.build_db import open_table

SQFT_PER_ACRE = 43560


def lot_sqft(area_size, uom):
    size = to_float(area_size)
    if not size:
        return None
    if (uom or "").strip().upper().startswith("ACRE"):
        return size * SQFT_PER_ACRE
    # 'SQUARE FEET'; 'UNASSIGNED' is used for flat-priced lots whose sizes are
    # in the same square-foot range (see docs/data-sources.md).
    return size


def valid_year(r, key):
    y = to_int(r.get(key))
    return y if y and y >= 1800 else None  # RES_ADDL uses 1000 as a placeholder


def text(r, key):
    v = (r.get(key) or "").strip()
    return v if v and v.upper() != "UNASSIGNED" else None


def yes(r, key):
    return int((r.get(key) or "").strip().upper() == "Y")


def build(out, cfg, log=print):
    src, fmt, year = cfg["source"], cfg["date_format"], cfg["tax_year"]

    log("  ACCOUNT_APPRL_YEAR")
    state_cd = {}
    for r in open_table(src, "ACCOUNT_APPRL_YEAR.CSV"):
        acct = r["ACCOUNT_NUM"]
        tot = to_float(r["TOT_VAL"])
        state_cd[acct] = (r.get("SPTD_CODE") or "").strip()
        out.add("valuation", {
            "account": acct, "tax_year": to_int(r.get("APPRAISAL_YR")) or year,
            "land_val": to_float(r["LAND_VAL"]), "improvement_val": to_float(r["IMPR_VAL"]),
            "market_val": tot, "appraised_val": tot, "assessed_val": to_float(r.get("HMSTD_CAP_VAL")),
        })
        prev = to_float(r.get("PREV_MKT_VAL"))
        if prev:
            out.add("valuation", {"account": acct, "tax_year": (to_int(r.get("APPRAISAL_YR")) or year) - 1,
                                  "market_val": prev})

    log("  RES_DETAIL")
    n_main = {}
    for r in open_table(src, "RES_DETAIL.CSV"):
        acct = r["ACCOUNT_NUM"]
        n_main[acct] = n_main.get(acct, 0) + 1  # file order; the summary keeps the first of equal size
        out.add("improvement", {
            "account": acct, "seq": n_main[acct], "kind": "main",
            "description": text(r, "BLDG_CLASS_DESC"),
            "year_built": valid_year(r, "YR_BUILT"), "eff_year_built": valid_year(r, "EFF_YR_BUILT"),
            "living_sqft": to_float(r["TOT_LIVING_AREA_SF"]),
            "beds": to_int(r["NUM_BEDROOMS"]), "full_baths": to_int(r["NUM_FULL_BATHS"]),
            "half_baths": to_int(r["NUM_HALF_BATHS"]),
            "stories": text(r, "NUM_STORIES_DESC"), "quality": text(r, "BLDG_CLASS_DESC"),
            "condition": text(r, "CDU_RATING_DESC"), "pool": yes(r, "POOL_IND"),
        })

    log("  RES_ADDL")
    n_other = {}
    for r in open_table(src, "RES_ADDL.CSV"):
        acct = r["ACCOUNT_NUM"]
        n_other[acct] = n_other.get(acct, 0) + 1
        out.add("improvement", {
            "account": acct, "seq": n_other[acct],
            "kind": "other", "description": text(r, "IMPR_TYP_DESC"),
            "year_built": valid_year(r, "YR_BUILT"),
            "area_sqft": to_float(r.get("AREA_SIZE")), "value": to_float(r.get("VAL_AMT")),
        })

    log("  LAND")
    for r in open_table(src, "LAND.CSV"):
        out.add("land", {
            "account": r["ACCOUNT_NUM"], "seq": to_int(r["SECTION_NUM"]) or 0,
            "size_sqft": lot_sqft(r["AREA_SIZE"], r.get("AREA_UOM_DESC")), "value": to_float(r.get("VAL_AMT")),
        })

    log("  APPLIED_STD_EXEMPT")
    for r in open_table(src, "APPLIED_STD_EXEMPT.CSV"):
        acct, yr = r["ACCOUNT_NUM"], to_int(r.get("APPRAISAL_YR")) or year
        if parse_date(r["HOMESTEAD_EFF_DT"], fmt):
            out.add("exemption", {"account": acct, "tax_year": yr, "code": "HS", "description": "Homestead"})
        for code, key in (("OV65", "OVER65_DESC"), ("DP", "DISABLED_DESC")):
            if text(r, key):
                out.add("exemption", {"account": acct, "tax_year": yr, "code": code, "description": text(r, key)})

    log("  ACCOUNT_INFO")
    for r in open_table(src, "ACCOUNT_INFO.CSV"):
        acct = r["ACCOUNT_NUM"]
        legal = " ".join(v for v in (text(r, f"LEGAL{i}") for i in range(1, 6)) if v)
        out.add("property", {
            "account": acct, "parcel_id": acct,
            "street_num": r["STREET_NUM"].strip(), "street_name": r["FULL_STREET_NAME"].strip(),
            "unit": text(r, "UNIT_ID"), "city": r["PROPERTY_CITY"].strip(),
            "zip": r["PROPERTY_ZIPCODE"].strip()[:5], "state_cd": state_cd.get(acct, ""),
            "nbhd": r["NBHD_CD"].strip(), "legal_desc": legal or None,
            # DCAD blanks the owner of confidential accounts and sets EXCLUDE_OWNER.
            "confidential": int((r.get("EXCLUDE_OWNER") or "").strip().upper() == "Y"),
        })
        deed = parse_date(r["DEED_TXFR_DATE"], fmt)
        if deed:
            out.add("deed", {"account": acct, "transfer_date": deed})
