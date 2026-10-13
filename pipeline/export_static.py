"""Export county DBs as static JSON for the serverless site (site/).

    python pipeline/export_static.py                 # all built counties -> site/data/
    python pipeline/export_static.py dallas --out /tmp/site-data

Layout per county (site/data/<county>/):
  meta.json            county settings, field list, area index (bbox and size
                       per area), neighborhood -> areas
  areas/<area>.json    every exported property in one area: its ZIP code; else
                       a 0.05-degree map tile; else its neighborhood
  search/<key>.json    address search entries keyed by the first two letters
                       of each street-name word
  accounts/<key>.json  account search entries keyed by the first three characters
                       after leading zeros

Only residential categories (state code A and B) are exported, from
property_summary, so confidential records are never included. The site's
engine (site/js/engine.js) reproduces app/comps.py and app/equity.py on
these rows; tests/test_static_parity.py checks they agree.
"""
import argparse
import json
import math
import os
import shutil
import sqlite3
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.config import PUBLIC, load_counties  # noqa: E402
from app.equity import PARAMS  # noqa: E402

FIELDS = ("account", "street_num", "street_name", "city", "zip", "state_cd", "nbhd", "deed_date", "appraised_val",
          "improvement_val", "land_val", "market_val", "prior_market_val", "beds", "full_baths", "half_baths",
          "living_sqft", "year_built", "eff_year_built", "quality", "condition", "lot_sqft", "homestead", "lat", "lon")
SEARCH_FIELDS = ("account", "street_num", "street_name", "city", "zip", "area", "appraised_val", "beds",
                 "full_baths", "half_baths", "living_sqft", "year_built")
CATEGORIES = ("A", "B")
TILE_DEG = 0.05
SKIP_WORDS = {"N", "S", "E", "W", "NE", "NW", "SE", "SW", "ST", "DR", "LN", "AVE", "AV", "RD", "CT", "TRL", "BLVD",
              "WAY", "PL", "CIR", "PKWY", "HWY", "TER", "LOOP", "PATH", "RUN", "PT", "XING", "FWY"}


def search_key(word):
    """Shard key for a street-name word or query word, or None if it is not indexed."""
    w = "".join(ch for ch in word.upper() if ch.isalnum())
    if len(w) < 2 or w in SKIP_WORDS or w.isdigit():
        return None
    return w[:2]


def account_key(account):
    """Shard key: first three characters after leading zeros (many Dallas accounts start '00000')."""
    return ("".join(ch for ch in account.upper() if ch.isalnum()).lstrip("0") or "0")[:3]


def area_of(row):
    if row["zip"]:
        return row["zip"]
    if row["lat"] is not None:
        return f"t{math.floor(row['lat'] / TILE_DEG)}_{math.floor(row['lon'] / TILE_DEG)}"
    if row["nbhd"]:
        return "n" + "".join(ch if ch.isalnum() else "_" for ch in row["nbhd"])
    return None


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, separators=(",", ":"))


def export_county(cfg, out_dir, log=print):
    db = sqlite3.connect(cfg["db"])
    db.row_factory = sqlite3.Row
    cats = ",".join(f"'{c}'" for c in CATEGORIES)
    rows = [dict(r) for r in db.execute(
        f"SELECT {','.join(FIELDS)} FROM property_summary WHERE substr(state_cd, 1, 1) IN ({cats}) "
        "AND appraised_val > 0 ORDER BY account")]
    meta_db = dict(db.execute("SELECT key, value FROM county_meta"))
    db.close()

    cities = sorted({r["city"] or "" for r in rows})
    city_ix = {c: i for i, c in enumerate(cities)}
    areas, nbhd_areas, skipped = defaultdict(list), defaultdict(set), 0
    search, accounts = defaultdict(list), defaultdict(list)
    for r in rows:
        area = area_of(r)
        if area is None:
            skipped += 1
            continue
        r["area"] = area
        areas[area].append(r)
        if r["nbhd"]:
            nbhd_areas[r["nbhd"]].add(area)
        entry = [r[f] if f != "city" else city_ix[r["city"] or ""] for f in SEARCH_FIELDS]
        for key in {k for k in map(search_key, (r["street_name"] or "").split()) if k}:
            search[key].append(entry)
        accounts[account_key(r["account"])].append(entry)

    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    index = {}
    for area, members in areas.items():
        write_json(os.path.join(out_dir, "areas", f"{area}.json"),
                   [[r[f] if f != "city" else city_ix[r["city"] or ""] for f in FIELDS] for r in members])
        lats = [r["lat"] for r in members if r["lat"] is not None]
        lons = [r["lon"] for r in members if r["lon"] is not None]
        index[area] = {"n": len(members), "bbox": [min(lats), min(lons), max(lats), max(lons)] if lats else None}
    for key, entries in search.items():
        write_json(os.path.join(out_dir, "search", f"{key}.json"), entries)
    for key, entries in accounts.items():
        write_json(os.path.join(out_dir, "accounts", f"{key}.json"), entries)
    write_json(os.path.join(out_dir, "meta.json"), {
        "county": {k: cfg[k] for k in PUBLIC} | {"id": cfg["id"]},
        "built_at": meta_db.get("built_at"), "fields": FIELDS, "search_fields": SEARCH_FIELDS, "cities": cities,
        "areas": index, "nbhd_areas": {k: sorted(v) for k, v in nbhd_areas.items()}, "params": PARAMS,
        "skip_words": sorted(SKIP_WORDS),
    })
    log(f"{cfg['id']}: {len(rows) - skipped} properties in {len(areas)} areas, {len(search)} search shards, "
        f"{len(accounts)} account shards ({skipped} without ZIP or location skipped)")
    files = len(areas) + len(search) + len(accounts) + 1
    return {"properties": len(rows) - skipped, "areas": len(areas), "files": files}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("counties", nargs="*")
    p.add_argument("--out", default=os.path.join(ROOT, "site", "data"))
    args = p.parse_args(argv)
    counties = load_counties()
    chosen = args.counties or [c for c, cfg in counties.items() if os.path.exists(cfg["db"])]
    listing = []
    for cid in chosen:
        export_county(counties[cid], os.path.join(args.out, cid))
        listing.append({k: counties[cid][k] for k in PUBLIC} | {"id": cid})
    write_json(os.path.join(args.out, "counties.json"), listing)


if __name__ == "__main__":
    main()
