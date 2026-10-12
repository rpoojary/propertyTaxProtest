"""Parcel centroids from ESRI shapefiles, converted to WGS84 lat/lon.

Pure Python (no GDAL/pyproj): reads polygon .shp records and the matching
.dbf key column, and inverts the Lambert Conformal Conic projection given in
the .prj. All four counties publish NAD83 Texas North Central (EPSG:2276, US
feet); NAD83 and WGS84 differ by about a metre here, which we ignore.
"""
import math
import re
import struct
import zipfile

# GRS80 ellipsoid
A = 6378137.0
F = 1 / 298.257222101
E = math.sqrt(2 * F - F * F)


class LCC:
    """Lambert Conformal Conic (2 standard parallels) on GRS80."""

    def __init__(self, lat1, lat2, lat0, lon0, false_easting, false_northing, unit_m):
        self.unit = unit_m
        self.fe, self.fn = false_easting * unit_m, false_northing * unit_m
        self.lon0 = math.radians(lon0)
        p1, p2, p0 = map(math.radians, (lat1, lat2, lat0))
        m1, m2 = self._m(p1), self._m(p2)
        t1, t2, t0 = self._t(p1), self._t(p2), self._t(p0)
        self.n = (math.log(m1) - math.log(m2)) / (math.log(t1) - math.log(t2))
        self.aF = A * m1 / (self.n * t1 ** self.n)
        self.rho0 = self.aF * t0 ** self.n

    @staticmethod
    def _m(phi):
        return math.cos(phi) / math.sqrt(1 - (E * math.sin(phi)) ** 2)

    @staticmethod
    def _t(phi):
        s = E * math.sin(phi)
        return math.tan(math.pi / 4 - phi / 2) / ((1 - s) / (1 + s)) ** (E / 2)

    @classmethod
    def from_prj(cls, wkt):
        if "Lambert_Conformal_Conic" not in wkt:
            raise ValueError("only Lambert Conformal Conic projections are supported")
        params = {k.lower(): float(v) for k, v in re.findall(r'PARAMETER\["([^"]+)",\s*([-0-9.eE]+)\]', wkt)}
        units = re.findall(r'UNIT\["([^"]+)",\s*([-0-9.eE]+)\]', wkt)
        unit_m = float(units[-1][1])  # the last UNIT belongs to PROJCS
        return cls(params["standard_parallel_1"], params["standard_parallel_2"], params["latitude_of_origin"],
                   params["central_meridian"], params["false_easting"], params["false_northing"], unit_m)

    def forward(self, lat, lon):
        phi = math.radians(lat)
        rho = self.aF * self._t(phi) ** self.n
        theta = self.n * (math.radians(lon) - self.lon0)
        x = self.fe + rho * math.sin(theta)
        y = self.fn + self.rho0 - rho * math.cos(theta)
        return x / self.unit, y / self.unit

    def inverse(self, x, y):
        dx, dy = x * self.unit - self.fe, self.rho0 - (y * self.unit - self.fn)
        rho = math.copysign(math.hypot(dx, dy), self.n)
        theta = math.atan2(dx, dy)
        t = (rho / self.aF) ** (1 / self.n)
        phi = math.pi / 2 - 2 * math.atan(t)
        for _ in range(10):
            s = E * math.sin(phi)
            nxt = math.pi / 2 - 2 * math.atan(t * ((1 - s) / (1 + s)) ** (E / 2))
            if abs(nxt - phi) < 1e-12:
                break
            phi = nxt
        return math.degrees(phi), math.degrees(theta / self.n + self.lon0)


def polygon_centroid(parts, points):
    """Area-weighted centroid over all rings (holes subtract); bbox centre if degenerate."""
    area2 = cx = cy = 0.0
    bounds = parts[1:] + [len(points)]
    for start, end in zip(parts, bounds, strict=True):
        ring = points[start:end]
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1], strict=True):
            cross = x1 * y2 - x2 * y1
            area2 += cross
            cx += (x1 + x2) * cross
            cy += (y1 + y2) * cross
    if abs(area2) < 1e-9:
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    return cx / (3 * area2), cy / (3 * area2)


def read_shp_centroids(f):
    """Yield one (x, y) centroid or None per record of a polygon .shp stream."""
    header = f.read(100)
    if struct.unpack(">i", header[:4])[0] != 9994:
        raise ValueError("not a shapefile")
    while True:
        rec = f.read(8)
        if len(rec) < 8:
            return
        _, words = struct.unpack(">ii", rec)
        content = f.read(words * 2)
        shape_type = struct.unpack("<i", content[:4])[0]
        if shape_type == 0:
            yield None
            continue
        if shape_type not in (5, 15, 25):  # Polygon, PolygonZ, PolygonM
            raise ValueError(f"unsupported shape type {shape_type}")
        nparts, npoints = struct.unpack("<ii", content[36:44])
        if nparts == 0 or npoints == 0:
            yield None
            continue
        parts = list(struct.unpack(f"<{nparts}i", content[44:44 + 4 * nparts]))
        off = 44 + 4 * nparts
        flat = struct.unpack(f"<{2 * npoints}d", content[off:off + 16 * npoints])
        yield polygon_centroid(parts, list(zip(flat[0::2], flat[1::2], strict=True)))


def normalize_key(value):
    """Numeric dbf keys come back as '247591.0000' or '2.47591000000e+05'; the roll uses '247591'."""
    if re.fullmatch(r"-?\d+\.0*", value):
        return value.split(".")[0]
    if re.fullmatch(r"-?\d+(\.\d+)?[eE][-+]?\d+", value):
        f = float(value)
        if f.is_integer():
            return str(int(f))
    return value


def read_dbf_column(f, column):
    """Yield the stripped text of `column` for each .dbf record (deleted rows yield None)."""
    head = f.read(32)
    nrec, hlen, rlen = struct.unpack("<IHH", head[4:12])
    fields, offset, col = [], 1, None
    for _ in range((hlen - 33) // 32):
        d = f.read(32)
        name = d[:11].split(b"\0")[0].decode("latin-1")
        length = d[16]
        if name.lower() == column.lower():
            col = (offset, length)
        fields.append(name)
        offset += length
    f.read(hlen - 32 - 32 * len(fields))
    if col is None:
        raise KeyError(f"{column!r} not in dbf fields {fields}")
    start, length = col
    for _ in range(nrec):
        r = f.read(rlen)
        if r[:1] == b"*":
            yield None
            continue
        value = r[start:start + length].decode("latin-1").strip()
        yield normalize_key(value)


def parcel_points(zip_path, key_column):
    """{key: (lat, lon)} for every parcel in a zipped shapefile."""
    zf = zipfile.ZipFile(zip_path)
    names = zf.namelist()

    def member(ext):
        found = [n for n in names if n.lower().endswith(ext)]
        if len(found) != 1:
            raise ValueError(f"expected one {ext} in {zip_path}, found {found}")
        return found[0]

    proj = LCC.from_prj(zf.read(member(".prj")).decode("latin-1"))
    out = {}
    with zf.open(member(".shp")) as shp, zf.open(member(".dbf")) as dbf:
        for xy, key in zip(read_shp_centroids(shp), read_dbf_column(dbf, key_column), strict=True):
            if xy is None or not key:
                continue
            out[key] = tuple(round(v, 6) for v in proj.inverse(*xy))
    return out
