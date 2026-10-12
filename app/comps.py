"""Property lookup and comparable-property queries against an app DB.

Every value returned is an appraised value from the county roll. Deed dates
mark ownership transfers; Texas does not publish sale prices.
"""
from app.stats import summarize

ROW_FIELDS = """account, street_num || ' ' || street_name AS address, deed_date,
    appraised_val, beds, full_baths, half_baths, living_sqft, lot_sqft, year_built"""

PROPERTY_FIELDS = """account, street_num, street_name, city, zip, state_cd, nbhd, deed_date,
    appraised_val, improvement_val, land_val, beds, full_baths, half_baths,
    living_sqft, year_built, lot_sqft, homestead, lat, lon"""

SQFT_BAND = 0.15
MAX_ROWS = 200


def like_escape(s):
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search(db, q, limit=20):
    q = q.strip().upper()
    if len(q) < 3:
        return []
    parts = q.split(None, 1)
    fields = ("account, street_num, street_name, city, zip, appraised_val, beds, full_baths, half_baths, "
              "living_sqft, year_built")
    if len(parts) == 2 and parts[0].isdigit():
        rows = db.execute(
            f"SELECT {fields} FROM property WHERE street_num = ? AND street_name LIKE ? ESCAPE '\\' "
            "ORDER BY street_name LIMIT ?",
            [parts[0], f"%{like_escape(parts[1])}%", limit])
    else:
        rows = db.execute(
            f"SELECT {fields} FROM property WHERE street_name LIKE ? ESCAPE '\\' OR account LIKE ? ESCAPE '\\' "
            "ORDER BY street_name, street_num LIMIT ?",
            [f"%{like_escape(q)}%", f"{like_escape(q)}%", limit])
    return [dict(r) for r in rows]


def get_property(db, account):
    row = db.execute(f"SELECT {PROPERTY_FIELDS} FROM property WHERE account = ?", [account]).fetchone()
    if not row:
        return None
    prop = dict(row)
    prop["homestead"] = bool(prop["homestead"])
    return prop


def _query(db, where, params):
    rows = db.execute(
        f"SELECT {ROW_FIELDS} FROM property WHERE {' AND '.join(where)} ORDER BY appraised_val",
        params).fetchall()
    return [dict(r) for r in rows]


def _result(criteria, rows, include_rows=True):
    out = {"criteria": criteria, "stats": summarize([r["appraised_val"] for r in rows])}
    if include_rows:
        out["comps"] = rows[:MAX_ROWS]
        out["truncated"] = len(rows) > MAX_ROWS
    return out


def find_comps(db, subject, tax_year):
    """Three comparison sets for `subject` (a get_property dict)."""
    since = f"{tax_year - 1}-01-01"
    base = ["account != ?", "appraised_val > 0"]
    base_params = [subject["account"]]
    category = (subject.get("state_cd") or "")[:1]
    if category:
        base.append("substr(state_cd, 1, 1) = ?")
        base_params.append(category)

    sqft = subject.get("living_sqft") or 0
    low, high = sqft * (1 - SQFT_BAND), sqft * (1 + SQFT_BAND)
    beds, full, half = subject.get("beds"), subject.get("full_baths"), subject.get("half_baths")
    has_rooms = beds is not None and full is not None

    # 1. Same neighborhood code, transferred since `since`.
    nbhd = subject.get("nbhd")
    if nbhd and nbhd.upper() != "UNASSIGNED":
        rows = _query(db, base + ["nbhd = ?", "deed_date >= ?"], base_params + [nbhd, since])
    else:
        rows = []
    neighborhood = _result({"nbhd": nbhd, "deed_since": since, "state_category": category}, rows)

    # 2. Same ZIP, similar size and rooms, transferred since `since`.
    crit = {"zip": subject["zip"], "deed_since": since, "state_category": category}
    where, params = base + ["zip = ?", "deed_date >= ?"], base_params + [subject["zip"], since]
    if sqft:
        where.append("living_sqft BETWEEN ? AND ?")
        params += [low, high]
        crit.update(sqft_low=round(low), sqft_high=round(high))
    if has_rooms:
        where += ["beds = ?", "full_baths >= ?"]
        params += [beds, full]
        crit.update(beds=beds, min_full_baths=full)
    zip_rows = _query(db, where, params) if sqft or has_rooms else []
    zip_set = _result(crit, zip_rows)

    # 3. Same ZIP, same size band and rooms, regardless of transfer date.
    crit = {"zip": subject["zip"], "state_category": category}
    where, params = base + ["zip = ?"], base_params + [subject["zip"]]
    if sqft:
        where.append("living_sqft BETWEEN ? AND ?")
        params += [low, high]
        crit.update(sqft_low=round(low), sqft_high=round(high))
    if has_rooms:
        where += ["beds = ?", "full_baths = ?", "coalesce(half_baths, 0) = ?"]
        params += [beds, full, half or 0]
        crit.update(beds=beds, full_baths=full, half_baths=half or 0)
    all_rows = _query(db, where, params) if sqft or has_rooms else []
    all_similar = _result(crit, all_rows, include_rows=False)

    return {"neighborhood": neighborhood, "zip": zip_set, "all_similar": all_similar}
