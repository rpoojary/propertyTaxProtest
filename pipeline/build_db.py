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
from app.db import CANONICAL_TABLES, INDEXES, PARCEL_INDEX, SCHEMA, SUMMARY_SQL, columns  # noqa: E402
from pipeline.geo import parcel_points  # noqa: E402

csv.field_size_limit(10_000_000)


def open_text(source, name=None, encoding="utf-8"):
    """Text stream for a file in a directory or zip, or `source` itself.

    `name` matches a file name exactly or as a suffix (case-insensitive), so
    'APPRAISAL_INFO.TXT' finds '2026-07-24_2026_APPRAISAL_INFO.TXT'. With no
    name, a zip must hold exactly one data file.
    """
    def pick(names):
        if name is None:
            data = [n for n in names if not n.lower().endswith((".pdf", "/"))]
            if len(data) != 1:
                raise ValueError(f"{source}: expected one data file, found {data}")
            return data[0]
        exact = [n for n in names if os.path.basename(n).upper() == name.upper()]
        found = exact or [n for n in names if n.upper().endswith(name.upper())]
        if len(found) != 1:
            raise ValueError(f"{source}: expected one file matching {name!r}, found {found}")
        return found[0]

    if os.path.isdir(source):
        path = os.path.join(source, pick(os.listdir(source)))
        return open(path, newline="", encoding=encoding, errors="replace")
    if zipfile.is_zipfile(source):
        zf = zipfile.ZipFile(source)
        return io.TextIOWrapper(zf.open(pick(zf.namelist())), encoding=encoding, errors="replace", newline="")
    return open(source, newline="", encoding=encoding, errors="replace")


def open_table(source, name=None, delimiter=","):
    """DictReader over a delimited file (see open_text for how it is found)."""
    return csv.DictReader(open_text(source, name), delimiter=delimiter)


class Writer:
    """Buffered inserts into the canonical tables. Adapters call add(table, row)."""

    BATCH = 50_000

    def __init__(self, conn):
        self.conn = conn
        self.cols = {t: columns(t) for t in CANONICAL_TABLES}
        self.buf = {t: [] for t in CANONICAL_TABLES}

    def add(self, table, row):
        unknown = set(row) - set(self.cols[table])
        if unknown:
            raise KeyError(f"{table} has no column(s) {sorted(unknown)}")
        self.buf[table].append(tuple(row.get(c) for c in self.cols[table]))
        if len(self.buf[table]) >= self.BATCH:
            self.flush(table)

    def flush(self, table=None):
        for t in [table] if table else CANONICAL_TABLES:
            if self.buf[t]:
                cols = self.cols[t]
                self.conn.executemany(
                    f"INSERT OR REPLACE INTO {t} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", self.buf[t])
                self.buf[t] = []


def add_locations(conn, parcels, key_column, log=print):
    """Set lat/lon from parcel centroids, joining the parcel key to property.parcel_id."""
    log("  parcel centroids")
    points = parcel_points(parcels, key_column)
    conn.execute(PARCEL_INDEX)
    conn.executemany("UPDATE property SET lat = ?, lon = ? WHERE parcel_id = ?",
                     ((lat, lon, key) for key, (lat, lon) in points.items()))
    located = conn.execute("SELECT count(*) FROM property WHERE lat IS NOT NULL").fetchone()[0]
    log(f"  {len(points)} parcels, {located} properties located")
    return located


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
    out = Writer(conn)
    adapter.build(out, cfg, log=log)
    out.flush()
    located = 0
    if cfg.get("parcels") and os.path.exists(cfg["parcels"]):
        located = add_locations(conn, cfg["parcels"], cfg["parcels_key"], log=log)
    elif cfg.get("parcels"):
        log(f"  {cfg['parcels']} not found; skipping lat/lon")
    conn.execute(SUMMARY_SQL, {"tax_year": cfg["tax_year"]})
    n = conn.execute("SELECT count(*) FROM property_summary").fetchone()[0]
    conn.executescript(INDEXES)
    meta = {
        "county": cfg["id"],
        "tax_year": str(cfg["tax_year"]),
        "source": os.path.basename(cfg["source"]),
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "rows": str(n),
        "located": str(located),
        **{f"{t}_rows": str(conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]) for t in CANONICAL_TABLES},
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
