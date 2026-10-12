"""Tarrant Appraisal District residential roll -> canonical tables.

Sources (see docs/data-sources.md):
  source        PropertyData(Delimited)_R.ZIP, pipe-delimited current roll
  prior_source  PropertyData_R_<year-1>(Certified).ZIP: prior-year values
  market_areas  <year>ResidentialCompAttributeData zip (xlsx): TAD market
                area (used as the neighborhood code), quality, condition and
                effective year built per PIN
  exemptions    PropertyData_Exemptions_<year>(Certified).ZIP

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
from pipeline.build_db import open_table


def norm_addr(s):
    return re.sub(r"\s+", " ", (s or "").upper()).strip()


def split_situs(addr):
    """'704 E WEATHERFORD ST' -> ('704', 'E WEATHERFORD ST')."""
    addr = norm_addr(addr)
    m = re.match(r"^(\d+[A-Z]?)\s+(.*)$", addr)
    return (m.group(1), m.group(2)) if m else ("", addr)


def pin(account):
    return (account or "").strip().zfill(8)


def load_comp_attributes(path):
    """{PIN: {'nbhd', 'quality', 'condition', 'eff_year_built'}} from the comp attribute workbook."""
    import openpyxl

    if not str(path).lower().endswith(".xlsx"):  # TAD ships the workbook inside a .zip
        zf = zipfile.ZipFile(path)
        name = next(n for n in zf.namelist() if n.lower().endswith(".xlsx"))
        path = io.BytesIO(zf.read(name))
    wb = openpyxl.load_workbook(path, read_only=True)
    rows = wb.worksheets[0].iter_rows(values_only=True)
    header = [str(h).strip() if h else "" for h in next(rows)]
    col = {name: header.index(name) for name in header if name}

    def get(r, name):
        i = col.get(name)
        v = r[i] if i is not None and i < len(r) else None
        return str(v).strip() if v not in (None, "") else None

    out = {}
    for r in rows:
        p = get(r, "PIN")
        if p:
            out[p.zfill(8)] = {"nbhd": get(r, "Market Area"), "quality": get(r, "Quality"),
                               "condition": get(r, "Condition"),
                               "eff_year_built": to_int(get(r, "Effective Year Built"))}
    wb.close()
    return out


def build(out, cfg, log=print):
    fmt, year = cfg["date_format"], cfg["tax_year"]

    attrs = {}
    if cfg.get("market_areas") and os.path.exists(cfg["market_areas"]):
        log("  comp attributes (market area, quality, condition)")
        attrs = load_comp_attributes(cfg["market_areas"])

    if cfg.get("exemptions") and os.path.exists(cfg["exemptions"]):
        log("  exemptions")
        for r in open_table(cfg["exemptions"], delimiter="|"):
            desc = (r.get("Exemption") or "").strip()
            if desc.upper().startswith("HOMESTEAD"):
                out.add("exemption", {"account": pin(r["Account_Num"]).lstrip("0") or "0",
                                      "tax_year": to_int(r.get("TaxYear")) or year - 1,
                                      "code": "HS", "description": desc})

    if cfg.get("prior_source") and os.path.exists(cfg["prior_source"]):
        log("  prior-year values")
        for r in open_table(cfg["prior_source"], delimiter="|"):
            acct = (r.get("Account_Num") or "").strip().lstrip("0")
            if acct:
                total = to_float(r.get("Total_Value"))
                out.add("valuation", {
                    "account": acct, "tax_year": to_int(r.get("Appraisal_Year")) or year - 1,
                    "land_val": to_float(r.get("Land_Value")), "improvement_val": to_float(r.get("Improvement_Value")),
                    "market_val": total, "appraised_val": total, "assessed_val": to_float(r.get("Appraised_Value")),
                })

    log("  residential roll")
    for r in open_table(cfg["source"], delimiter="|"):
        acct = (r.get("Account_Num") or "").strip().lstrip("0")
        if not acct:
            continue
        a = attrs.get(pin(acct), {})
        num, street = split_situs(r["Situs_Address"])
        owner_occupied = street and norm_addr(r["Owner_Address"]) == norm_addr(r["Situs_Address"])
        city = zip5 = None
        if owner_occupied:
            city = (r["Owner_CityState"] or "").split(",")[0].strip() or None
            zip5 = (r["Owner_Zip"] or "").strip()[:5] or None
        out.add("property", {
            "account": acct, "parcel_id": (r["GIS_Link"] or "").strip() or None,
            "street_num": num, "street_name": street, "city": city, "zip": zip5,
            "state_cd": (r["Property_Class"] or "").strip(), "nbhd": a.get("nbhd"),
            "legal_desc": (r.get("LegalDescription") or "").strip() or None,
        })
        # Total_Value is the market value; TAD's Appraised_Value can carry the
        # homestead cap, so it is stored as the assessed value.
        total = to_float(r["Total_Value"])
        out.add("valuation", {
            "account": acct, "tax_year": to_int(r.get("Appraisal_Year")) or year,
            "land_val": to_float(r["Land_Value"]), "improvement_val": to_float(r["Improvement_Value"]),
            "market_val": total, "appraised_val": total, "assessed_val": to_float(r.get("Appraised_Value")),
        })
        out.add("improvement", {
            "account": acct, "seq": 1, "kind": "main",
            "year_built": to_int(r["Year_Built"]) or None, "eff_year_built": a.get("eff_year_built"),
            "living_sqft": to_float(r["Living_Area"]) or None,
            "quality": a.get("quality"), "condition": a.get("condition"),
            "pool": int((r.get("Swimming_Pool_Ind") or "").strip().upper() == "Y"),
        })
        acres = to_float(r["Land_Acres"])
        out.add("land", {"account": acct, "seq": 1,
                         "size_sqft": to_float(r["Land_SqFt"]) or (acres * 43560 if acres else None),
                         "value": to_float(r["Land_Value"])})
        deed = parse_date(r["Deed_Date"], fmt)
        if deed:
            out.add("deed", {"account": acct, "transfer_date": deed,
                             "instrument": (r.get("Instrument_No") or "").strip() or None})
