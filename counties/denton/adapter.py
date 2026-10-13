"""Denton CAD -> canonical tables.

Sources (see docs/data-sources.md):
  source   nightly_appraisals_<year>_Certified.zip: one CSV row per parcel
           and owner (multi-owner rows repeat the full value)
  details  <year> CERTIFIED DATA - REAL.zip: True Prodigy fixed-width export.
           APPRAISAL_INFO gives the neighborhood code (hood_cd);
           IMPROVEMENT_DETAIL_ATTR gives Bedrooms, Plumbing (bath count) and Condition.
"""
import os
import re

from app.stats import parse_date, to_float, to_int
from pipeline.build_db import open_table, open_text

# Fixed-width positions (0-based slices) from TP_Legacy8.0.32-AppraisalExportLayout.xlsx.
INFO_PROP_ID = slice(0, 12)
INFO_HOOD_CD = slice(1685, 1695)
ATTR_PROP_ID = slice(0, 12)
ATTR_DESC = slice(52, 77)
ATTR_CODE = slice(77, 87)

HOMESTEAD_CODES = {"HS", "DVHS", "DVHSS"}


def dwelling_class(classes):
    """'1750S,GB2' -> 'GB2': the residence class among the segment classes."""
    codes = [c.strip() for c in (classes or "").split(",") if c.strip()]
    main = [c for c in codes if re.fullmatch(r"[A-Z]{2}\d+", c)]
    return (main or codes or [None])[0]


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
    beds, baths, condition = {}, {}, {}
    with open_text(path, "IMPROVEMENT_DETAIL_ATTR.TXT", encoding="latin-1") as f:
        for line in f:
            desc = line[ATTR_DESC].strip()
            if desc not in ("Bedrooms", "Plumbing", "Condition"):
                continue
            pid = str(int(line[ATTR_PROP_ID]))
            if desc == "Condition":
                condition.setdefault(pid, line[ATTR_CODE].strip() or None)
                continue
            val = to_float(line[ATTR_CODE])
            if val is None or val <= 0:
                continue
            # A property can have several improvements; keep the largest count.
            target = beds if desc == "Bedrooms" else baths
            target[pid] = max(val, target.get(pid, 0))
    return hood, beds, baths, condition


def build(out, cfg, log=print):
    fmt, year = cfg["date_format"], cfg["tax_year"]
    hood, beds, baths, condition = {}, {}, {}, {}
    if cfg.get("details") and os.path.exists(cfg["details"]):
        hood, beds, baths, condition = load_details(cfg["details"], log)
    else:
        log("  no details export; beds, baths and neighborhood will be empty")

    log("  appraisal CSV")
    seen = set()
    for r in open_table(cfg["source"]):
        pid = (r.get("pid") or "").strip()
        if not pid or pid in seen:  # one row per owner; values repeat
            continue
        seen.add(pid)
        street = " ".join(p for p in (r["situsStreetPrefix"].strip(), r["situsStreetName"].strip(),
                                      r["situsStreetSuff"].strip()) if p)
        out.add("property", {
            "account": pid, "parcel_id": pid,
            "street_num": r["situsStreetNumb"].strip(), "street_name": street,
            "city": r["situsCity"].strip(), "zip": r["situsZip"].strip()[:5],
            "state_cd": (r["stateCodes"] or "").split(",")[0].strip(), "nbhd": hood.get(pid),
            "legal_desc": (r.get("legalDescription") or "").strip() or None,
            "confidential": int((r.get("confidential") or "").strip() == "1"),
        })
        land = (to_float(r["landHSValue"]) or 0) + (to_float(r["landNHSValue"]) or 0)
        out.add("valuation", {
            "account": pid, "tax_year": to_int(r.get("pYear")) or year,
            "land_val": land or None, "improvement_val": to_float(r["improvementValue"]),
            "market_val": to_float(r.get("ownerMarketValue")), "appraised_val": to_float(r["ownerAppraisedValue"]),
            "assessed_val": to_float(r.get("ownerNetAppraisedValue")),
        })
        full, half = split_baths(baths.get(pid))
        out.add("improvement", {
            "account": pid, "seq": 1, "kind": "main",
            "year_built": to_int(r["imprvActualYearBuilt"]) or None,
            "eff_year_built": to_int(r.get("imprvEffYearBuilt")) or None,
            "living_sqft": to_float(r["imprvMainArea"]) or None,
            "beds": to_int(beds.get(pid)), "full_baths": full, "half_baths": half,
            "quality": dwelling_class(r.get("imprvClasses")), "condition": condition.get(pid),
        })
        out.add("land", {"account": pid, "seq": 1,
                         "size_sqft": to_float(r["land_sqft"]) or to_float(r["landTotalSqft"]) or None,
                         "value": land or None})
        codes = {c.strip().upper() for c in (r["exemptions"] or "").split(",") if c.strip()}
        if codes & HOMESTEAD_CODES:
            codes.add("HS")
        for code in sorted(codes):
            out.add("exemption", {"account": pid, "tax_year": to_int(r.get("pYear")) or year, "code": code})
        deed = parse_date(r["deedDt"], fmt)
        if deed:
            out.add("deed", {"account": pid, "transfer_date": deed,
                             "deed_type": (r.get("deedType") or "").strip() or None,
                             "instrument": (r.get("instrumentNum") or "").strip() or None})
