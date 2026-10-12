"""Write tiny polygon shapefiles (zipped .shp/.shx/.dbf/.prj) for tests."""
import struct
import zipfile

PRJ_2276 = (
    'PROJCS["NAD_1983_StatePlane_Texas_North_Central_FIPS_4202_Feet",GEOGCS["GCS_North_American_1983",'
    'DATUM["D_North_American_1983",SPHEROID["GRS_1980",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],'
    'UNIT["Degree",0.0174532925199433]],PROJECTION["Lambert_Conformal_Conic"],PARAMETER["False_Easting",1968500.0],'
    'PARAMETER["False_Northing",6561666.666666666],PARAMETER["Central_Meridian",-98.5],'
    'PARAMETER["Standard_Parallel_1",32.13333333333333],PARAMETER["Standard_Parallel_2",33.96666666666667],'
    'PARAMETER["Latitude_Of_Origin",31.66666666666667],UNIT["Foot_US",0.3048006096012192]]'
)


def _polygon(rings):
    if not rings:
        return struct.pack("<i", 0)
    pts = [p for r in rings for p in r]
    parts, i = [], 0
    for r in rings:
        parts.append(i)
        i += len(r)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    body = struct.pack("<i4d2i", 5, min(xs), min(ys), max(xs), max(ys), len(rings), len(pts))
    body += struct.pack(f"<{len(parts)}i", *parts)
    body += b"".join(struct.pack("<2d", *p) for p in pts)
    return body


def write_zip(path, key_name, records, key_len=20, name="parcels"):
    """records: list of (key, rings); rings is a list of [(x, y), ...] closed rings, or [] for a null shape."""
    shp, shx, off = b"", b"", 50
    for i, (_, rings) in enumerate(records, 1):
        content = _polygon(rings)
        shx += struct.pack(">ii", off, len(content) // 2)
        shp += struct.pack(">ii", i, len(content) // 2) + content
        off += 4 + len(content) // 2

    def header(total_bytes):
        big = struct.pack(">i5ii", 9994, 0, 0, 0, 0, 0, total_bytes // 2)
        return big + struct.pack("<ii4d4d", 1000, 5, *([0.0] * 8))

    shp = header(100 + len(shp)) + shp
    shx = header(100 + len(shx)) + shx
    dbf = struct.pack("<4BIHH20x", 3, 126, 1, 1, len(records), 32 + 32 + 1, 1 + key_len)
    dbf += key_name.encode().ljust(11, b"\0") + b"C" + b"\0" * 4 + bytes([key_len, 0]) + b"\0" * 14 + b"\r"
    dbf += b"".join(b" " + str(k).encode().ljust(key_len) for k, _ in records) + b"\x1a"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(f"{name}.shp", shp)
        z.writestr(f"{name}.shx", shx)
        z.writestr(f"{name}.dbf", dbf)
        z.writestr(f"{name}.prj", PRJ_2276)
    return path


def square(cx, cy, half):
    """Clockwise ring (shapefile outer-ring order) around (cx, cy)."""
    return [(cx - half, cy - half), (cx - half, cy + half), (cx + half, cy + half), (cx + half, cy - half),
            (cx - half, cy - half)]
