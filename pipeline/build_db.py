"""Build a county's read-only app DB from its raw export.

Usage:
    python pipeline/build_db.py dallas                 # paths from counties/config.yaml
    python pipeline/build_db.py collin --source X.csv --output out.db

The DB is written to a temp file and renamed into place, so a running app
never sees a half-built file.
"""
import argparse
import csv
import importlib
import io
import os
import sqlite3
import sys
import zipfile
from datetime import UTC, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import load_counties  # noqa: E402
from app.db import COLUMNS, INDEXES, SCHEMA  # noqa: E402

csv.field_size_limit(10_000_000)


def open_table(source, name):
    """DictReader over `name` inside a zip, a directory, or a single CSV file."""
    if os.path.isdir(source):
        f = open(os.path.join(source, name), newline="", encoding="utf-8", errors="replace")
    elif zipfile.is_zipfile(source):
        zf = zipfile.ZipFile(source)
        member = next(m for m in zf.namelist() if m.upper() == name.upper())
        f = io.TextIOWrapper(zf.open(member), encoding="utf-8", errors="replace", newline="")
    else:
        f = open(source, newline="", encoding="utf-8", errors="replace")
    return csv.DictReader(f)


def insert_properties(conn, rows):
    sql = f"INSERT OR REPLACE INTO property ({','.join(COLUMNS)}) VALUES ({','.join('?' * len(COLUMNS))})"
    batch, n = [], 0
    for r in rows:
        batch.append(tuple(r.get(c) for c in COLUMNS))
        if len(batch) >= 50_000:
            conn.executemany(sql, batch)
            n += len(batch)
            batch = []
    conn.executemany(sql, batch)
    return n + len(batch)


def build(cfg, output=None, source=None, log=print):
    if not cfg.get("adapter"):
        raise SystemExit(f"no adapter for {cfg['id']} yet")
    cfg = dict(cfg)
    if source:
        cfg["source"] = source
    output = output or cfg["db"]
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    tmp = output + ".building"
    if os.path.exists(tmp):
        os.remove(tmp)
    conn = sqlite3.connect(tmp)
    conn.executescript(SCHEMA)
    adapter = importlib.import_module(f"counties.{cfg['adapter']}.adapter")
    n = adapter.build(conn, cfg, log=log)
    conn.executescript(INDEXES)
    meta = {
        "county": cfg["id"],
        "tax_year": str(cfg["tax_year"]),
        "source": os.path.basename(cfg["source"]),
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "rows": str(n),
    }
    conn.executemany("INSERT INTO county_meta VALUES (?, ?)", meta.items())
    conn.commit()
    conn.execute("VACUUM")
    conn.close()
    os.replace(tmp, output)
    log(f"{cfg['id']}: {n} properties -> {output}")
    return n


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("county")
    p.add_argument("--source", help="override the raw export path from config")
    p.add_argument("--output", help="override the output DB path from config")
    p.add_argument("--config", help="alternate counties config file")
    args = p.parse_args(argv)
    counties = load_counties(args.config)
    if args.county not in counties:
        raise SystemExit(f"unknown county {args.county!r}; choose from {', '.join(counties)}")
    build(counties[args.county], output=args.output, source=args.source)


if __name__ == "__main__":
    main()
