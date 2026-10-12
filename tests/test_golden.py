"""Golden-file tests: each county adapter's full output on its fixture.

Every canonical table and property_summary is dumped as sorted JSON and
compared with tests/golden/<county>.json. Any change in what an adapter
writes fails here. If the change is intended, regenerate and review the diff:

    UPDATE_GOLDEN=1 pytest tests/test_golden.py
"""
import json
import os
import sqlite3

import pytest

from app.db import CANONICAL_TABLES

GOLDEN = os.path.join(os.path.dirname(__file__), "golden")


def dump(db_path):
    db = sqlite3.connect(db_path)
    out = {}
    for table in (*CANONICAL_TABLES, "property_summary"):
        cur = db.execute(f"SELECT * FROM {table}")
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r, strict=True)) for r in cur]
        out[table] = sorted(rows, key=lambda r: json.dumps(r, sort_keys=True))
    db.close()
    return out


@pytest.mark.parametrize("county", ["dallas", "collin", "tarrant", "denton"])
def test_golden(county, request):
    actual = dump(request.getfixturevalue(f"{county}_db"))
    path = os.path.join(GOLDEN, f"{county}.json")
    if os.environ.get("UPDATE_GOLDEN"):
        os.makedirs(GOLDEN, exist_ok=True)
        with open(path, "w") as f:
            json.dump(actual, f, indent=1, sort_keys=True)
            f.write("\n")
    with open(path) as f:
        expected = json.load(f)
    for table in expected:
        assert actual[table] == expected[table], f"{county}.{table} differs from {path}"
