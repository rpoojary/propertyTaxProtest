"""The static site's engine (site/js/engine.js) must match the Python code exactly.

Exports each county fixture with pipeline/export_static.py, runs the engine in
Node on the exported JSON, and compares comparison sets, the equity analysis
and the letter blocks with app/comps.py, app/equity.py and app/letter.py on
the same database. Skipped when Node is not installed.
"""
import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

from app import comps, equity, letter
from app.config import normalize
from app.db import connect_ro
from pipeline.export_static import CATEGORIES, export_county
from tests.conftest import county_cfg

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")
SCRIPT = Path(__file__).parent / "js" / "parity.js"
TODAY = date(2026, 10, 13)
OWNER = {"owner_name": "Pat Tester", "conditions": ["Roof leaks"], "repairs": [{"desc": "Roof", "cost": "1234.5"}]}


def python_results(db_path, cfg, accounts):
    db = connect_ro(db_path)
    owner = letter.clean_owner_input(OWNER)
    out = {}
    for account in accounts:
        s = comps.get_property(db, account)
        sets = comps.find_comps(db, s, cfg["tax_year"])
        eq = equity.analyze(db, s)
        try:
            lt = letter.build(cfg, s, eq, sets, owner, today=TODAY)
        except letter.NoReduction as exc:
            lt = {"error": str(exc)}
        out[account] = {"comps": sets, "equity": eq, "letter": lt}
    return json.loads(json.dumps(out))


def js_results(data_dir, cid, cfg, accounts):
    today = TODAY.strftime("%B %d, %Y").replace(" 0", " ")
    proc = subprocess.run([NODE, str(SCRIPT), str(data_dir), cid, str(cfg["tax_year"]), today, json.dumps(OWNER),
                           *accounts], capture_output=True, text=True, check=True)
    return json.loads(proc.stdout)


def compare(py, js, path=""):
    """Deep equality with a tiny tolerance for floats that are never shown rounded (averages)."""
    if isinstance(py, dict):
        assert isinstance(js, dict) and set(py) == set(js), f"{path}: keys {sorted(py)} != {sorted(js)}"
        for k in py:
            compare(py[k], js[k], f"{path}.{k}")
    elif isinstance(py, list):
        assert isinstance(js, list) and len(py) == len(js), f"{path}: length {len(py)} != {js!r:.80}"
        for i, (a, b) in enumerate(zip(py, js, strict=True)):
            compare(a, b, f"{path}[{i}]")
    elif isinstance(py, float) and isinstance(js, (int, float)):
        assert js == pytest.approx(py, rel=1e-12, abs=1e-9), f"{path}: {py} != {js}"
    else:
        assert py == js, f"{path}: {py!r} != {js!r}"


@pytest.mark.parametrize("county", ["dallas", "collin", "tarrant", "denton"])
def test_engine_matches_python(county, request, tmp_path):
    db_path = request.getfixturevalue(f"{county}_db")
    cfg = normalize(county, county_cfg(db_path, adapter=county))
    export_county(cfg, tmp_path / county, log=lambda *a: None)
    cats = ",".join(f"'{c}'" for c in CATEGORIES)
    accounts = [r[0] for r in connect_ro(db_path).execute(
        f"SELECT account FROM property_summary WHERE substr(state_cd,1,1) IN ({cats}) AND appraised_val > 0"
        # homes with no ZIP, location or neighborhood have nothing to compare against and are not exported
        " AND (zip IS NOT NULL OR lat IS NOT NULL OR nbhd IS NOT NULL)")]
    assert accounts
    py = python_results(db_path, cfg, accounts)
    js = js_results(tmp_path, county, cfg, accounts)
    for account in accounts:
        compare(py[account], js[account], f"{county}:{account}")


def test_browser_pdf_contains_every_word(tmp_path):
    """site/js/pdf.js draws every word of the letter blocks, across pages, as a valid PDF."""
    pypdf = pytest.importorskip("pypdf")
    from tests.test_letter import CFG, NO_SETS, analysis

    s, eq = analysis()
    owner = letter.clean_owner_input({"owner_name": "Pat (O'Brien) \\ Tester", "conditions": ["Roof leaks"] * 12,
                                      "repairs": [{"desc": "Roof", "cost": 1500}]})
    content = letter.build(CFG, s, eq, NO_SETS, owner, today=TODAY)
    out = tmp_path / "letter.pdf"
    subprocess.run([NODE, str(SCRIPT.parent / "render_pdf.js"), str(out)], input=json.dumps(content), text=True,
                   check=True)
    reader = pypdf.PdfReader(str(out))
    text = "".join(page.extract_text() for page in reader.pages).replace("\n", "").replace(" ", "")
    words = []
    for b in content["blocks"]:
        if b["t"] == "p":
            words += "".join(t for t, _ in b["runs"]).split()
        elif b["t"] == "table":
            words += [w for row in b["rows"] for cell in row for w in cell.split()]
        elif b["t"] != "space":
            words += b["text"].split()
    assert [w for w in words if w not in text] == []
    assert len(reader.pages) >= 2
    assert reader.metadata.title == f"Property Tax Protest - {content['address']}"
