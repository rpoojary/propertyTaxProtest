import io

import pytest

from app import letter
from tests.test_equity import home, make_db

pypdf = pytest.importorskip("pypdf")
pytest.importorskip("reportlab")

CFG = {"id": "test", "name": "Test County", "cad_name": "Test Central Appraisal District", "cad_abbrev": "TCAD",
       "cad_address": "1 Main St, Testville, TX 75000", "protest_url": "https://example.test/", "tax_year": 2026}
NO_SETS = {k: {"criteria": {}, "stats": {"count": 0}} for k in ("neighborhood", "zip", "all_similar")}


def analysis(subject_val=450000):
    from app import equity
    db = make_db([home("SUBJ", val=subject_val)] + [home(f"C{i}", dlat_mi=0.1, val=v) for i, v in
                                                  enumerate([380000, 390000, 400000, 410000, 420000])])
    s = dict(db.execute("SELECT * FROM property_summary WHERE account='SUBJ'").fetchone())
    return s, equity.analyze(db, s)


def pdf_text(content):
    pdf = letter.render_pdf(content)
    assert pdf.startswith(b"%PDF")
    return " ".join(page.extract_text() for page in pypdf.PdfReader(io.BytesIO(pdf)).pages)


def test_equity_letter():
    s, eq = analysis()
    owner = letter.clean_owner_input({"owner_name": "Pat <b>Tester</b> & Co",
                                      "conditions": ["Roof <i>leaks</i>"],
                                      "repairs": [{"desc": "Roof", "cost": "15000"}, {"desc": "x", "cost": "abc"}]})
    content = letter.build(CFG, s, eq, NO_SETS, owner)
    assert content["opinion"] == {"base": 400000, "basis": "equity", "requested": 385000, "reduction": 65000}
    text = pdf_text(content)
    for expected in ("$450,000", "$385,000", "$400,000", "§42.26(a)(3)", "Pat <b>Tester</b> & Co", "Roof <i>leaks</i>",
                     "Test Central Appraisal District", "1 Main St, Testville, TX 75000", "C0 ST", "Median adjusted"):
        assert expected in text, expected
    for fabricated in ("highest", "smallest lot", "sale price of", "sold for"):
        assert fabricated not in text


def test_no_reduction():
    s, eq = analysis(subject_val=390000)
    assert not eq["supports_reduction"]
    with pytest.raises(letter.NoReduction):
        letter.build(CFG, s, eq, NO_SETS, letter.clean_owner_input({}))


def test_fallback_to_set_medians():
    s, _ = analysis()
    stats = {"count": 4, "median": 401234, "low": 1, "high": 2}
    sets = dict(NO_SETS, zip={"criteria": {"zip": "75000"}, "stats": stats})
    content = letter.build(CFG, s, {"available": False}, sets, letter.clean_owner_input({}))
    assert content["opinion"]["basis"] == "set_medians" and content["opinion"]["requested"] == 401000
    assert "ZIP 75000" in pdf_text(content)


def test_clean_owner_input_limits():
    o = letter.clean_owner_input({"owner_name": "x" * 500, "conditions": ["a"] * 50,
                                  "repairs": [{"cost": -5}, {"cost": 1e9}, {"cost": 100}, "junk"]})
    assert len(o["name"]) == 120 and len(o["conditions"]) == 20
    assert o["repairs"] == [{"desc": "Repair", "cost": 100}]
    assert letter.clean_owner_input({})["name"] == "Property Owner"
