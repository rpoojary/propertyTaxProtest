import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.config import normalize  # noqa: E402
from pipeline.build_db import build  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "dallas")


def county_cfg(db, **extra):
    cfg = {
        "name": "Test County", "cad_name": "Test Central Appraisal District", "cad_abbrev": "TCAD",
        "cad_address": "1 Main St, Testville, TX 75000", "protest_url": "https://example.test/",
        "tax_year": 2026, "date_format": "%m/%d/%Y", "adapter": "dallas", "source": FIXTURE, "db": db,
    }
    cfg.update(extra)
    return cfg


@pytest.fixture(scope="session")
def dallas_db(tmp_path_factory):
    from pipeline.geo import LCC
    from tests.shapefile_util import PRJ_2276, square, write_zip

    tmp = tmp_path_factory.mktemp("db")
    x, y = LCC.from_prj(PRJ_2276).forward(32.89, -96.94)
    parcels = write_zip(tmp / "PARCEL_GEOM.zip", "Acct", [("S0001", [square(x, y, 40)]), ("NOPE", [square(x, y, 9)])])
    path = str(tmp / "dallas.db")
    build(normalize("dallas", county_cfg(path, parcels=str(parcels), parcels_key="Acct")), log=lambda *a: None)
    return path


@pytest.fixture(scope="session")
def counties(dallas_db, tmp_path_factory):
    missing = str(tmp_path_factory.mktemp("none") / "missing.db")
    return {
        "dallas": normalize("dallas", county_cfg(dallas_db)),
        "tarrant": normalize("tarrant", county_cfg(missing, adapter=None, name="Not Built County")),
    }
