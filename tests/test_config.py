import pytest

from app.config import load_counties, normalize, public_view


def test_repo_config_is_valid():
    counties = load_counties()
    assert set(counties) == {"dallas", "collin", "tarrant", "denton"}
    assert all(c.get("adapter") for c in counties.values())
    for cfg in counties.values():
        assert isinstance(cfg["tax_year"], int)
        assert cfg["db"].startswith("/")


def test_missing_field_rejected():
    with pytest.raises(ValueError, match="cad_address"):
        normalize("x", {"name": "X", "cad_name": "X CAD", "cad_abbrev": "X", "protest_url": "u",
                        "tax_year": 2026, "date_format": "%Y", "db": "x.db"})


def test_public_view_hides_paths(counties):
    view = public_view(counties["dallas"])
    assert view["available"] is True
    assert "db" not in view and "source" not in view
    assert public_view(counties["tarrant"])["available"] is False
