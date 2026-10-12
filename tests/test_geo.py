import pytest

from pipeline.geo import LCC, normalize_key, parcel_points, polygon_centroid
from tests.shapefile_util import PRJ_2276, square, write_zip

PROJ = LCC.from_prj(PRJ_2276)


def test_origin_maps_to_latitude_of_origin():
    lat, lon = PROJ.inverse(1968500.0, 6561666.666666666)
    assert lat == pytest.approx(31 + 40 / 60, abs=1e-9)
    assert lon == pytest.approx(-98.5, abs=1e-9)


@pytest.mark.parametrize("lat,lon", [(32.7767, -96.7970), (33.2148, -97.1331), (32.7555, -97.3308)])
def test_round_trip(lat, lon):
    assert PROJ.inverse(*PROJ.forward(lat, lon)) == pytest.approx((lat, lon), abs=1e-9)


def test_polygon_centroid_with_hole():
    outer = square(0, 0, 10)
    hole = [(5, 5), (9, 5), (9, 9), (5, 9), (5, 5)]  # counter-clockwise: subtracts
    pts = outer + hole
    cx, cy = polygon_centroid([0, len(outer)], pts)
    assert cx < 0 and cy < 0  # pulled away from the hole
    assert polygon_centroid([0], square(3, 4, 1)) == pytest.approx((3, 4))


def test_normalize_key():
    assert normalize_key("2.05420000000e+05") == "205420"
    assert normalize_key("247591.0000") == "247591"
    assert normalize_key("25583-7-5") == "25583-7-5"
    assert normalize_key("12.5") == "12.5"


def test_parcel_points(tmp_path):
    x, y = PROJ.forward(32.89, -96.94)
    path = write_zip(tmp_path / "p.zip", "Acct", [("A1", [square(x, y, 50)]), ("A2", []), ("", [square(x, y, 5)])])
    pts = parcel_points(str(path), "acct")
    assert set(pts) == {"A1"}  # null shape and blank key skipped
    assert pts["A1"] == pytest.approx((32.89, -96.94), abs=1e-6)
