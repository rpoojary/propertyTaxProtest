"""Unequal-appraisal (equity) analysis, Texas Tax Code §42.26(a)(3).

§42.26(a)(3) grants relief when a property's appraised value exceeds "the
median appraised value of a reasonable number of comparable properties
appropriately adjusted". This module:

1. selects comparable homes near the subject (same property category and,
   where published, the same quality grade; similar living area and age;
   widening the search radius until there are enough),
2. adjusts each comparable's appraised value toward the subject for
   differences in living area, age and land value (the adjustment grid),
3. takes the median of the adjusted values.

Every number used and produced is returned, so the letter can show the full
grid. Inputs are appraisal-district values only; Texas publishes no sale
prices. Bedrooms and baths are shown but not adjusted: district values are
driven by living area, which is adjusted.
"""
import math

from app.stats import median

PARAMS = {
    "radius_steps_mi": (0.5, 1.0, 2.0, 3.0),
    "min_comps": 5,
    "max_comps": 15,
    "sqft_band": 0.20,      # comparable living area within ±20%
    "year_band": 10,        # comparable (effective) year built within ±10 years
    "age_rate": 0.005,      # 0.5% of improvement value per year of age difference
}

MILES_PER_DEG_LAT = 69.0


def distance_mi(lat1, lon1, lat2, lon2):
    """Great-circle distance in miles."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(a))


def effective_year(p, use_effective):
    return p.get("eff_year_built") if use_effective else p.get("year_built")


def adjust(subject, comp, use_effective, params=PARAMS):
    """Adjustment grid row: comp's appraised value adjusted toward the subject."""
    impr, sqft = comp["improvement_val"], comp["living_sqft"]
    rate = impr / sqft
    size = (subject["living_sqft"] - sqft) * rate
    age = impr * params["age_rate"] * (effective_year(subject, use_effective) - effective_year(comp, use_effective))
    land = (subject.get("land_val") or 0) - (comp.get("land_val") or 0)
    adjusted = comp["appraised_val"] + size + age + land
    return {
        "improvement_rate": round(rate, 2),
        "size_adj": round(size),
        "age_adj": round(age),
        "land_adj": round(land),
        "adjusted_val": round(adjusted),
    }


CANDIDATE_FIELDS = """account, street_num || ' ' || street_name AS address, nbhd, zip, deed_date, appraised_val,
    improvement_val, land_val, beds, full_baths, half_baths, living_sqft, year_built, eff_year_built,
    quality, condition, lot_sqft, lat, lon"""


def _candidates(db, subject, where, params):
    year_col = "eff_year_built" if subject["_use_effective"] else "year_built"
    year = effective_year(subject, subject["_use_effective"])
    sqft = subject["living_sqft"]
    sql = [f"SELECT {CANDIDATE_FIELDS} FROM property_summary WHERE account != ?",
           "appraised_val > 0", "improvement_val > 0", "living_sqft BETWEEN ? AND ?",
           f"{year_col} BETWEEN ? AND ?", "substr(state_cd, 1, 1) = ?"]
    args = [subject["account"], sqft * (1 - params["sqft_band"]), sqft * (1 + params["sqft_band"]),
            year - params["year_band"], year + params["year_band"], (subject.get("state_cd") or "")[:1]]
    for grade in ("quality", "condition"):
        if subject.get(grade):
            sql.append(f"{grade} = ?")
            args.append(subject[grade])
    for clause, values in where:
        sql.append(clause)
        args += values
    return [dict(r) for r in db.execute(" AND ".join(sql), args)]


def find_equity_comps(db, subject, params=PARAMS):
    """Select comparables. Returns (rows, how) where `how` describes the search.

    Searches outward from the subject's parcel centroid until at least
    min_comps are found; if the widest radius still falls short (or the
    subject has no location), the subject's neighborhood is used when it
    yields more.
    """
    s = subject
    rows, how = [], {"method": "none"}
    if s.get("lat") is not None and s.get("lon") is not None:
        for radius in params["radius_steps_mi"]:
            dlat = radius / MILES_PER_DEG_LAT
            dlon = radius / (MILES_PER_DEG_LAT * math.cos(math.radians(s["lat"])))
            found = _candidates(db, s, [("lat BETWEEN ? AND ?", [s["lat"] - dlat, s["lat"] + dlat]),
                                        ("lon BETWEEN ? AND ?", [s["lon"] - dlon, s["lon"] + dlon])], params)
            for r in found:
                r["distance_mi"] = round(distance_mi(s["lat"], s["lon"], r["lat"], r["lon"]), 2)
            rows = [r for r in found if r["distance_mi"] <= radius]
            how = {"method": "radius", "radius_mi": radius}
            if len(rows) >= params["min_comps"]:
                return rows, how
    if s.get("nbhd"):
        found = _candidates(db, s, [("nbhd = ?", [s["nbhd"]])], params)
        if len(found) > len(rows):
            for r in found:
                r["distance_mi"] = (round(distance_mi(s["lat"], s["lon"], r["lat"], r["lon"]), 2)
                                    if None not in (s.get("lat"), r.get("lat")) else None)
            return found, {"method": "neighborhood", "nbhd": s["nbhd"]}
    return rows, how


def rank(subject, rows, use_effective):
    """Most similar first: same neighborhood, then distance, relative size and age."""
    year = effective_year(subject, use_effective)

    def score(r):
        d = r["distance_mi"] or 0
        other_nbhd = 1 if subject.get("nbhd") and r.get("nbhd") != subject["nbhd"] else 0
        return (other_nbhd + d + abs(r["living_sqft"] - subject["living_sqft"]) / subject["living_sqft"] * 2
                + abs(effective_year(r, use_effective) - year) / 10)
    return sorted(rows, key=lambda r: (score(r), r["account"]))


def analyze(db, subject, params=PARAMS):
    """Equity analysis for `subject` (a property_summary dict). Never raises on thin data."""
    s = dict(subject)
    missing = [k for k in ("living_sqft", "improvement_val", "appraised_val") if not s.get(k)]
    if not s.get("year_built") and not s.get("eff_year_built"):
        missing.append("year_built")
    if missing:
        return {"available": False, "reason": f"subject is missing {', '.join(missing)}", "params": params}
    s["_use_effective"] = bool(s.get("eff_year_built"))
    rows, how = find_equity_comps(db, s, params)
    if s["_use_effective"]:
        rows = [r for r in rows if r.get("eff_year_built")]
    comps = rank(s, rows, s["_use_effective"])[: params["max_comps"]]
    for c in comps:
        c.update(adjust(s, c, s["_use_effective"], params))
    out = {
        "available": len(comps) >= params["min_comps"],
        "params": params,
        "search": how,
        "criteria": {
            "state_category": (s.get("state_cd") or "")[:1],
            "quality": s.get("quality"),
            "condition": s.get("condition"),
            "sqft_low": round(s["living_sqft"] * (1 - params["sqft_band"])),
            "sqft_high": round(s["living_sqft"] * (1 + params["sqft_band"])),
            "year_basis": "effective year built" if s["_use_effective"] else "year built",
            "year_low": effective_year(s, s["_use_effective"]) - params["year_band"],
            "year_high": effective_year(s, s["_use_effective"]) + params["year_band"],
        },
        "candidates_found": len(rows),
        "comps": comps,
    }
    if not out["available"]:
        out["reason"] = f"only {len(comps)} comparable homes found (need {params['min_comps']})"
        return out
    adjusted = [c["adjusted_val"] for c in comps]
    med = median(adjusted)
    out.update({
        "count": len(comps),
        "median_adjusted": round(med),
        "unadjusted_median": round(median([c["appraised_val"] for c in comps])),
        "subject_value": s["appraised_val"],
        "supports_reduction": s["appraised_val"] > med,
        "difference": round(s["appraised_val"] - med),
    })
    return out
