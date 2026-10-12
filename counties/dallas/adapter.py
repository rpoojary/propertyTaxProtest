"""Dallas CAD certified CSV export (DCAD<year>_CURRENT.zip) -> app DB.

Tables used (all keyed by ACCOUNT_NUM): ACCOUNT_INFO, ACCOUNT_APPRL_YEAR,
RES_DETAIL, LAND (section 1), APPLIED_STD_EXEMPT. Layout: the
DCAD_Certified_READ_ME.rtf inside the zip, and docs/data-sources.md.
"""
from app.stats import parse_date, to_float, to_int
from pipeline.build_db import insert_properties, open_table

SQFT_PER_ACRE = 43560


def lot_sqft(area_size, uom):
    size = to_float(area_size)
    if not size:
        return None
    if uom.strip().upper().startswith("ACRE"):
        return size * SQFT_PER_ACRE
    # 'SQUARE FEET'; 'UNASSIGNED' is used for flat-priced lots whose sizes are
    # in the same square-foot range (see docs/data-sources.md).
    return size


def build(conn, cfg, log=print):
    src, fmt = cfg["source"], cfg["date_format"]

    log("  ACCOUNT_APPRL_YEAR")
    apprl = {}
    for r in open_table(src, "ACCOUNT_APPRL_YEAR.CSV"):
        apprl[r["ACCOUNT_NUM"]] = (to_float(r["TOT_VAL"]), to_float(r["IMPR_VAL"]),
                                   to_float(r["LAND_VAL"]), (r.get("SPTD_CODE") or "").strip())

    log("  RES_DETAIL")
    res = {}
    for r in open_table(src, "RES_DETAIL.CSV"):
        sqft = to_float(r["TOT_LIVING_AREA_SF"])
        prev = res.get(r["ACCOUNT_NUM"])
        # A few accounts have several dwellings; keep the largest.
        if prev is None or (sqft or 0) > (prev[3] or 0):
            res[r["ACCOUNT_NUM"]] = (to_int(r["NUM_BEDROOMS"]), to_int(r["NUM_FULL_BATHS"]),
                                     to_int(r["NUM_HALF_BATHS"]), sqft, to_int(r["YR_BUILT"]))

    log("  LAND")
    land = {}
    for r in open_table(src, "LAND.CSV"):
        if r["SECTION_NUM"].strip() == "1":
            land[r["ACCOUNT_NUM"]] = lot_sqft(r["AREA_SIZE"], r["AREA_UOM_DESC"])

    log("  APPLIED_STD_EXEMPT")
    homestead = {r["ACCOUNT_NUM"] for r in open_table(src, "APPLIED_STD_EXEMPT.CSV")
                 if parse_date(r["HOMESTEAD_EFF_DT"], fmt)}

    log("  ACCOUNT_INFO")

    def rows():
        for r in open_table(src, "ACCOUNT_INFO.CSV"):
            acct = r["ACCOUNT_NUM"]
            val = apprl.get(acct)
            if val is None:
                continue
            beds, fb, hb, sqft, yr = res.get(acct, (None,) * 5)
            yield {
                "account": acct,
                "street_num": r["STREET_NUM"].strip(),
                "street_name": r["FULL_STREET_NAME"].strip(),
                "city": r["PROPERTY_CITY"].strip(),
                "zip": r["PROPERTY_ZIPCODE"].strip()[:5],
                "state_cd": val[3],
                "nbhd": r["NBHD_CD"].strip(),
                "deed_date": parse_date(r["DEED_TXFR_DATE"], fmt),
                "appraised_val": val[0],
                "improvement_val": val[1],
                "land_val": val[2],
                "beds": beds,
                "full_baths": fb,
                "half_baths": hb,
                "living_sqft": sqft,
                "year_built": yr,
                "lot_sqft": land.get(acct),
                "homestead": int(acct in homestead),
                "parcel_id": acct,
            }

    return insert_properties(conn, rows())
