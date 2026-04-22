"""
Dallas County Property Tax Protest Helper
Flask app that queries local county appraisal data to find comps and generate protest documents.
"""

import os
import sqlite3
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder="static")
DB_PATH = os.environ.get("APPRAISAL_DB", os.path.join(os.path.dirname(__file__), "appraisal_lite.db"))


def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/search")
def search():
    q = request.args.get("q", "").strip()
    if len(q) < 3:
        return jsonify([])

    db = get_db()
    # Search by street number + name or account number
    parts = q.upper().split(None, 1)

    if len(parts) == 2 and parts[0].isdigit():
        rows = db.execute("""
            SELECT i.ACCOUNT_NUM, i.STREET_NUM, i.FULL_STREET_NAME,
                   i.PROPERTY_CITY, SUBSTR(i.PROPERTY_ZIPCODE,1,5) as ZIP,
                   a.TOT_VAL, r.NUM_BEDROOMS, r.NUM_FULL_BATHS, r.NUM_HALF_BATHS,
                   r.TOT_LIVING_AREA_SF, r.YR_BUILT
            FROM account_info i
            JOIN account_apprl a ON i.ACCOUNT_NUM = a.ACCOUNT_NUM
            LEFT JOIN res_detail r ON i.ACCOUNT_NUM = r.ACCOUNT_NUM
            WHERE i.STREET_NUM = ? AND i.FULL_STREET_NAME LIKE ?
            LIMIT 20
        """, [parts[0], f"%{parts[1]}%"]).fetchall()
    else:
        rows = db.execute("""
            SELECT i.ACCOUNT_NUM, i.STREET_NUM, i.FULL_STREET_NAME,
                   i.PROPERTY_CITY, SUBSTR(i.PROPERTY_ZIPCODE,1,5) as ZIP,
                   a.TOT_VAL, r.NUM_BEDROOMS, r.NUM_FULL_BATHS, r.NUM_HALF_BATHS,
                   r.TOT_LIVING_AREA_SF, r.YR_BUILT
            FROM account_info i
            JOIN account_apprl a ON i.ACCOUNT_NUM = a.ACCOUNT_NUM
            LEFT JOIN res_detail r ON i.ACCOUNT_NUM = r.ACCOUNT_NUM
            WHERE i.FULL_STREET_NAME LIKE ? OR i.ACCOUNT_NUM LIKE ?
            LIMIT 20
        """, [f"%{q.upper()}%", f"%{q}%"]).fetchall()

    db.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/property/<account>")
def property_detail(account):
    db = get_db()
    row = db.execute("""
        SELECT i.ACCOUNT_NUM, i.STREET_NUM, i.FULL_STREET_NAME,
               i.PROPERTY_CITY, SUBSTR(i.PROPERTY_ZIPCODE,1,5) as ZIP,
               i.DEED_TXFR_DATE, i.NBHD_CD, i.OWNER_NAME1,
               a.TOT_VAL, a.IMPR_VAL, a.LAND_VAL,
               r.NUM_BEDROOMS, r.NUM_FULL_BATHS, r.NUM_HALF_BATHS,
               r.TOT_LIVING_AREA_SF, r.YR_BUILT,
               l.AREA_SIZE
        FROM account_info i
        JOIN account_apprl a ON i.ACCOUNT_NUM = a.ACCOUNT_NUM
        LEFT JOIN res_detail r ON i.ACCOUNT_NUM = r.ACCOUNT_NUM
        LEFT JOIN land l ON i.ACCOUNT_NUM = l.ACCOUNT_NUM AND l.SECTION_NUM = '1'
        WHERE i.ACCOUNT_NUM = ?
    """, [account]).fetchone()

    if not row:
        db.close()
        return jsonify({"error": "Not found"}), 404

    prop = dict(row)

    # Check homestead
    exempt = db.execute("""
        SELECT HOMESTEAD_EFF_DT FROM applied_std_exempt
        WHERE ACCOUNT_NUM = ? AND HOMESTEAD_EFF_DT IS NOT NULL AND HOMESTEAD_EFF_DT != ''
    """, [account]).fetchone()
    prop["HOMESTEAD"] = bool(exempt)

    db.close()
    return jsonify(prop)


@app.route("/api/comps/<account>")
def comps(account):
    db = get_db()

    # Get subject property
    subj = db.execute("""
        SELECT i.ACCOUNT_NUM, SUBSTR(i.PROPERTY_ZIPCODE,1,5) as ZIP, i.NBHD_CD,
               r.NUM_BEDROOMS, r.NUM_FULL_BATHS, r.NUM_HALF_BATHS,
               r.TOT_LIVING_AREA_SF, r.YR_BUILT
        FROM account_info i
        LEFT JOIN res_detail r ON i.ACCOUNT_NUM = r.ACCOUNT_NUM
        WHERE i.ACCOUNT_NUM = ?
    """, [account]).fetchone()

    if not subj:
        db.close()
        return jsonify({"error": "Not found"}), 404

    subj = dict(subj)
    beds = int(subj["NUM_BEDROOMS"] or 0)
    fb = int(subj["NUM_FULL_BATHS"] or 0)
    hb = int(subj["NUM_HALF_BATHS"] or 0)
    sqft = float(subj["TOT_LIVING_AREA_SF"] or 0)
    zipcode = subj["ZIP"]
    nbhd = subj["NBHD_CD"]

    sqft_low = sqft * 0.85
    sqft_high = sqft * 1.15

    # Neighborhood comps — sold last year
    nbhd_comps = db.execute("""
        SELECT i.STREET_NUM || ' ' || i.FULL_STREET_NAME as ADDRESS,
               i.DEED_TXFR_DATE, a.TOT_VAL,
               r.NUM_BEDROOMS, r.NUM_FULL_BATHS, r.NUM_HALF_BATHS,
               r.TOT_LIVING_AREA_SF, r.YR_BUILT, l.AREA_SIZE
        FROM account_info i
        JOIN account_apprl a ON i.ACCOUNT_NUM = a.ACCOUNT_NUM
        LEFT JOIN res_detail r ON i.ACCOUNT_NUM = r.ACCOUNT_NUM
        LEFT JOIN land l ON i.ACCOUNT_NUM = l.ACCOUNT_NUM AND l.SECTION_NUM = '1'
        WHERE i.NBHD_CD = ? AND i.ACCOUNT_NUM != ?
          AND (i.DEED_TXFR_DATE LIKE '%/2025' OR i.DEED_TXFR_DATE LIKE '%/2026')
          AND CAST(a.TOT_VAL AS REAL) > 0
        ORDER BY CAST(a.TOT_VAL AS REAL)
    """, [nbhd, account]).fetchall()

    # Zip comps — similar specs, sold last year
    zip_comps = db.execute("""
        SELECT i.STREET_NUM || ' ' || i.FULL_STREET_NAME as ADDRESS,
               i.DEED_TXFR_DATE, a.TOT_VAL,
               r.NUM_BEDROOMS, r.NUM_FULL_BATHS, r.NUM_HALF_BATHS,
               r.TOT_LIVING_AREA_SF, r.YR_BUILT, l.AREA_SIZE
        FROM account_info i
        JOIN account_apprl a ON i.ACCOUNT_NUM = a.ACCOUNT_NUM
        LEFT JOIN res_detail r ON i.ACCOUNT_NUM = r.ACCOUNT_NUM
        LEFT JOIN land l ON i.ACCOUNT_NUM = l.ACCOUNT_NUM AND l.SECTION_NUM = '1'
        WHERE SUBSTR(i.PROPERTY_ZIPCODE,1,5) = ? AND i.ACCOUNT_NUM != ?
          AND (i.DEED_TXFR_DATE LIKE '%/2025' OR i.DEED_TXFR_DATE LIKE '%/2026')
          AND CAST(r.NUM_BEDROOMS AS INT) = ?
          AND CAST(r.NUM_FULL_BATHS AS INT) >= ?
          AND CAST(r.TOT_LIVING_AREA_SF AS REAL) BETWEEN ? AND ?
          AND CAST(a.TOT_VAL AS REAL) > 0
        ORDER BY CAST(a.TOT_VAL AS REAL)
    """, [zipcode, account, beds, fb, sqft_low, sqft_high]).fetchall()

    # All similar in zip (not just sold)
    all_similar = db.execute("""
        SELECT CAST(a.TOT_VAL AS REAL) as val
        FROM account_info i
        JOIN account_apprl a ON i.ACCOUNT_NUM = a.ACCOUNT_NUM
        JOIN res_detail r ON i.ACCOUNT_NUM = r.ACCOUNT_NUM
        WHERE SUBSTR(i.PROPERTY_ZIPCODE,1,5) = ?
          AND CAST(r.NUM_BEDROOMS AS INT) = ?
          AND CAST(r.NUM_FULL_BATHS AS INT) = ?
          AND CAST(r.NUM_HALF_BATHS AS INT) = ?
          AND CAST(r.TOT_LIVING_AREA_SF AS REAL) BETWEEN ? AND ?
          AND CAST(a.TOT_VAL AS REAL) > 0
        ORDER BY val
    """, [zipcode, beds, fb, hb, sqft_low, sqft_high]).fetchall()

    all_vals = sorted([float(r["val"]) for r in all_similar])
    zip_vals = sorted([float(r["TOT_VAL"]) for r in zip_comps])
    nbhd_vals = sorted([float(r["TOT_VAL"]) for r in nbhd_comps])

    def stats(vals):
        if not vals:
            return {"count": 0}
        n = len(vals)
        return {
            "count": n,
            "median": vals[n // 2],
            "average": sum(vals) / n,
            "low": vals[0],
            "high": vals[-1]
        }

    db.close()
    return jsonify({
        "neighborhood_comps": [dict(r) for r in nbhd_comps],
        "zip_comps": [dict(r) for r in zip_comps],
        "neighborhood_stats": stats(nbhd_vals),
        "zip_stats": stats(zip_vals),
        "all_similar_stats": stats(all_vals),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
