"""Print a property and its comparable properties from a county app DB.

Usage:
    python scripts/query_comps.py dallas 325402100A0260000
    python scripts/query_comps.py dallas 325402100A0260000 --set zip
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.comps import find_comps, get_property  # noqa: E402
from app.config import load_counties  # noqa: E402
from app.db import connect_ro  # noqa: E402


def money(v):
    return f"${v:,.0f}" if v is not None else "-"


def baths(full, half):
    if full is None:
        return "-"
    return f"{full}F/{half}H" if half else str(full)


def print_row(r, marker=""):
    sqft, val, lot = r.get("living_sqft"), r.get("appraised_val"), r.get("lot_sqft")
    ppsf = money(val / sqft) if val and sqft else "-"
    beds = r["beds"] if r.get("beds") is not None else "-"
    print(f"{(r.get('address') or '')[:27]:<28} {r.get('deed_date') or '':<11} {money(val):>11} "
          f"{beds:>4} {baths(r.get('full_baths'), r.get('half_baths')):>5} "
          f"{f'{sqft:,.0f}' if sqft else '-':>7} {f'{lot:,.0f}' if lot else '-':>9} "
          f"{r.get('year_built') or '-':>5} {ppsf:>7}{marker}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("county")
    p.add_argument("account")
    p.add_argument("--set", choices=["neighborhood", "zip"], default="neighborhood")
    p.add_argument("--db", help="override the app DB path from config")
    args = p.parse_args(argv)

    cfg = load_counties()[args.county]
    path = args.db or cfg["db"]
    if not os.path.exists(path):
        raise SystemExit(f"{path} not found; build it with: python pipeline/build_db.py {args.county}")
    db = connect_ro(path)
    subject = get_property(db, args.account)
    if subject is None:
        raise SystemExit(f"account {args.account} not found")
    result = find_comps(db, subject, cfg["tax_year"])[args.set]

    print(f"{cfg['cad_abbrev']} {cfg['tax_year']} appraised values; {args.set} set: {result['criteria']}")
    print(f"{'Address':<28} {'Deed date':<11} {'Appraised':>11} {'Bed':>4} {'Bath':>5} "
          f"{'SqFt':>7} {'Lot sqft':>9} {'Year':>5} {'$/SqFt':>7}")
    print("-" * 100)
    subject["address"] = f"{subject['street_num']} {subject['street_name']}"
    print_row(subject, "  <<< subject")
    for r in result["comps"]:
        print_row(r)
    s = result["stats"]
    if s["count"]:
        print(f"\n{s['count']} comps; median {money(s['median'])}, range {money(s['low'])}-{money(s['high'])}")
    db.close()


if __name__ == "__main__":
    main()
