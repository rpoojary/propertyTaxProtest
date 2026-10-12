import pytest

pytest.importorskip("flask")

from app.main import create_app  # noqa: E402


@pytest.fixture
def client(counties):
    return create_app(counties).test_client()


def test_index(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"Property Tax Protest Helper" in r.data


def test_counties(client):
    data = {c["id"]: c for c in client.get("/api/counties").get_json()}
    assert data["dallas"]["available"] is True
    assert data["dallas"]["cad_name"] == "Test Central Appraisal District"
    assert data["tarrant"]["available"] is False
    assert "db" not in data["dallas"]


def test_search(client):
    r = client.get("/api/dallas/search?q=100 test")
    assert [p["account"] for p in r.get_json()] == ["S0001"]


def test_property_has_no_owner(client):
    p = client.get("/api/dallas/property/S0001").get_json()
    assert p["appraised_val"] == 400000
    assert p["homestead"] is True
    assert not any("owner" in k.lower() for k in p)


def test_comps(client):
    data = client.get("/api/dallas/comps/S0001").get_json()
    assert data["neighborhood"]["stats"]["median"] == 350000
    assert data["zip"]["stats"]["count"] == 3
    assert data["all_similar"]["stats"]["median"] == 320000


@pytest.mark.parametrize("url", [
    "/api/nowhere/search?q=test",
    "/api/tarrant/search?q=test",
    "/api/dallas/property/NOPE",
    "/api/dallas/comps/NOPE",
])
def test_not_found(client, url):
    r = client.get(url)
    assert r.status_code == 404
    assert "error" in r.get_json()


def test_property_location(client):
    p = client.get("/api/dallas/property/S0001").get_json()
    assert p["lat"] == pytest.approx(32.89, abs=1e-5)
    assert p["lon"] == pytest.approx(-96.94, abs=1e-5)
    assert client.get("/api/dallas/property/C0001").get_json()["lat"] is None
