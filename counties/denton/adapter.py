"""Denton CAD -> app DB.

Sources (see docs/data-sources.md):
  source   nightly_appraisals_<year>_Certified.zip: one CSV row per parcel
           and owner (multi-owner rows repeat the full value)
  details  <year> CERTIFIED DATA - REAL.zip: True Prodigy fixed-width export.
           APPRAISAL_INFO gives the neighborhood code (hood_cd);
           IMPROVEMENT_DETAIL_ATTR gives Bedrooms and Plumbing (bath count).
"""
import os

from app.stats import parse_date, to_float, to_int
from pipeline.build_db import insert_properties, open_table, open_text

# Fixed-width positions (0-based slices) from TP_Legacy8.0.32-AppraisalExportLayout.xlsx.
INFO_PROP_ID = slice(0, 12)
INFO_HOOD_CD = slice(1685, 1695)
ATTR_PROP_ID = slice(0, 12)
ATTR_DESC = slice(52, 77)
ATTR_CODE = slice(77, 87)

HOMESTEAD_CODES = {"HS", "DVHS", "DVHSS"}


def split_baths(value):
    b = to_float(value)
    if b is None or b <= 0:
        return None, None
    full = int(b)
    return full, 1 if b - full >= 0.5 else 0


def load_details(path, log=print):
    log("  neighborhood codes (APPRAISAL_INFO)")
    hood = {}
    with open_text(path, "APPRAISAL_INFO.TXT", encoding="latin-1") as f:
        for line in f:
            code = line[INFO_HOOD_CD].strip()
            if code:
                hood[str(int(line[INFO_PROP_ID]))] = code
    log("  bedrooms and baths (IMPROVEMENT_DETAIL_ATTR)")
    beds, baths = {}, {}
    with open_text(path, "IMPROVEMENT_DETAIL_ATTR.TXT", encoding="latin-1") as f:
        for line in f:
            desc = line[ATTR_DESC].strip()
            if desc not in ("Bedrooms", "Plumbing"):
                continue
            pid = str(int(line[ATTR_PROP_ID]))
            val = to_float(line[ATTR_CODE])
            if val is None or val <= 0:
                continue
            # A property can have several improvements; keep the largest count.
            target = beds if desc == "Bedrooms" else baths
            target[pid] = max(val, target.get(pid, 0))
    return hood, beds, baths


def build(conn, cfg, log=print):
    fmt = cfg["date_format"]
    hood, beds, baths = {}, {}, {}
    if cfg.get("details") and os.path.exists(cfg["details"]):
        hood, beds, baths = load_details(cfg["details"], log)
    else:
        log("  no details export; beds, baths and neighborhood will be empty")

    log("  appraisal CSV")

    def rows():
        seen = set()
        for r in open_table(cfg["source"]):
            pid = (r.get("pid") or "").strip()
            if not pid or pid in seen:
                continue
            seen.add(pid)
            street = " ".join(p for p in (r["situsStreetPrefix"].strip(), r["situsStreetName"].strip(),
                                          r["situsStreetSuff"].strip()) if p)
            codes = {c.strip().upper() for c in (r["exemptions"] or "").split(",")}
            full, half = split_baths(baths.get(pid))
            land = (to_float(r["landHSValue"]) or 0) + (to_float(r["landNHSValue"]) or 0)
            yield {
                "account": pid,
                "street_num": r["situsStreetNumb"].strip(),
                "street_name": street,
                "city": r["situsCity"].strip(),
                "zip": r["situsZip"].strip()[:5],
                "state_cd": (r["stateCodes"] or "").split(",")[0].strip(),
                "nbhd": hood.get(pid),
                "deed_date": parse_date(r["deedDt"], fmt),
                "appraised_val": to_float(r["ownerAppraisedValue"]),
                "improvement_val": to_float(r["improvementValue"]),
                "land_val": land or None,
                "beds": to_int(beds.get(pid)),
                "full_baths": full,
                "half_baths": half,
                "living_sqft": to_float(r["imprvMainArea"]) or None,
                "year_built": to_int(r["imprvActualYearBuilt"]) or None,
                "lot_sqft": to_float(r["land_sqft"]) or to_float(r["landTotalSqft"]) or None,
                "homestead": int(bool(codes & HOMESTEAD_CODES)),
                "parcel_id": pid,
            }

    return insert_properties(conn, rows())
