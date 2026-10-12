"""Download raw county appraisal exports into data/<county>/raw/.

Usage:
    python scripts/fetch_data.py                 # all counties, core files
    python scripts/fetch_data.py dallas collin   # selected counties
    python scripts/fetch_data.py --list          # print the manifest only

Files already present with the server's size are skipped. A manifest with
size, sha256 and download time is written to data/<county>/raw/MANIFEST.json.
Raw data is never committed (data/ is gitignored).

Sources and field notes: docs/data-sources.md
"""
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
UA = "Mozilla/5.0 (propertyTaxProtest data fetch)"


def dcad(path):
    """Dallas CAD serves files through ViewPDFs.aspx with a UNC-style id."""
    unc = "\\\\DCAD.ORG\\WEB\\WEBDATA\\WEBFORMS\\" + path
    return "https://www.dallascad.org/ViewPDFs.aspx?type=3&id=" + urllib.parse.quote(unc)


COLLIN_DATA = "https://link.collincad.org/public/folder/1j1vp-rhx06rqkh3vz2ipw/AppraisalData/"
COLLIN_GIS = "https://link.collincad.org/public/folder/blc8m6dbs0glddi_ixn5-a/CurrentGIS/"
TAD = "https://www.tad.org/content/"
DENTON = "https://dentoncad.net/data/_uploaded/files/datafiles/"

# (local filename, url). Core set: latest certified + current-year roll,
# parcel geometry, and the layout/code documents needed to read them.
MANIFEST = {
    "dallas": [
        ("DCAD2026_CURRENT.zip", dcad("DATA PRODUCTS\\DCAD2026_CURRENT.ZIP")),
        ("DCAD2027_CURRENT.zip", dcad("data products\\DCAD2027_CURRENT.zip")),
        ("ARB_CURRENT.zip", dcad("DATA PRODUCTS\\ARB_CURRENT.zip")),
        ("PARCEL_GEOM.zip", dcad("GIS PRODUCTS\\PARCEL_GEOM.zip")),
        ("PARCEL_GEOM.pdf", "https://www.dallascad.org/PARCEL_GEOM.pdf"),
    ],
    "collin": [
        ("CCAD-Appraisal-Data.csv", COLLIN_DATA + "CCAD-Appraisal-Data.csv"),
        ("AppraisalData-Public-2026.csv", COLLIN_DATA + "AppraisalData-Public-2026.csv"),
        ("AppraisalData-Public.csv", COLLIN_DATA + "AppraisalData-Public.csv"),
        ("CodeFileLists.csv", COLLIN_DATA + "CodeFileLists.csv"),
        ("NbhdList.csv", COLLIN_DATA + "NbhdList.csv"),
        ("LiteDatabase_FileLayout.pdf", COLLIN_DATA + "LiteDatabase_FileLayout.pdf"),
        ("parcels_with_appraisal_data_R5.zip", COLLIN_GIS + "parcels_with_appraisal_data_R5.zip"),
        ("parcels_with_appraisal_data_column_definitions.xls",
         COLLIN_GIS + "parcels_with_appraisal_data_column_definitions.xls"),
    ],
    "tarrant": [
        ("PropertyData_R_current.zip", TAD + "data-download/PropertyData(Delimited)_R.ZIP"),
        ("PropertyData_R_2025_certified.zip", TAD + "data-download/PropertyData_R_2025(Certified).ZIP"),
        ("PropertyData_Exemptions_2025_certified.zip",
         TAD + "data-download/PropertyData_Exemptions_2025(Certified).ZIP"),
        ("2026ResidentialCompAttributeData.zip", TAD + "data-download/2026ResidentialCompAttributeData_1.zip"),
        ("2026ResidentialFeaturesValue.zip", TAD + "data-download/2026ResidentialFeaturesValue.zip"),
        ("PropertyData_Layouts.pdf", TAD + "forms/PropertyData&PropertyLocationLayouts.pdf"),
        ("Parcels.zip", TAD + "gis-data/Parcels.zip"),
    ],
    "denton": [
        ("nightly_appraisals.zip", DENTON + "gis/nightly_appraisals.zip"),
        ("nightly_appraisals_2026_Certified.zip", DENTON + "gis/nightly_appraisals_2026_Certified.zip"),
        ("DCAD_Schema_2026.xlsx", DENTON + "gis/DCAD_Schema_2026.xlsx"),
        ("schema.ini", DENTON + "gis/schema.ini"),
        ("StateCodeDesc.pdf", DENTON + "gis/StateCodeDesc.pdf"),
        ("LandTypeCodes.pdf", DENTON + "gis/LandTypeCodes.pdf"),
        ("nightly_geodatabase.gdb.zip", DENTON + "gis/nightly_geodatabase.gdb.zip"),
        ("2026_CERTIFIED_DATA_REAL.zip", DENTON + "2026/CertifiedDataReal/2026 CERTIFIED DATA - REAL.zip"),
        ("TP_Legacy8.0.32-AppraisalExportLayout.xlsx",
         DENTON + "2026/AppraisalExportLayout/TP_Legacy8.0.32-AppraisalExportLayout(UPDATED-2:17:26).xlsx"),
    ],
}


def quote_url(url):
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(parts._replace(path=urllib.parse.quote(parts.path, safe="/%")))


def fetch(url, dest):
    req = urllib.request.Request(quote_url(url), headers={"User-Agent": UA})
    tmp = dest + ".part"
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=120) as r:
        ctype = r.headers.get("Content-Type", "")
        total = int(r.headers.get("Content-Length") or 0)
        if "text/html" in ctype:
            raise RuntimeError(f"got HTML instead of a file ({ctype}); URL likely moved")
        if os.path.exists(dest) and total and os.path.getsize(dest) == total:
            return None
        f = open(tmp, "wb")
        done, last = 0, time.time()
        while chunk := r.read(1 << 20):
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if time.time() - last > 15:
                pct = f"{100 * done / total:.0f}%" if total else ""
                print(f"    {done >> 20} MB {pct}", flush=True)
                last = time.time()
        f.close()
    if total and done != total:
        raise RuntimeError(f"short read: {done} of {total} bytes")
    os.replace(tmp, dest)
    return {"url": url, "bytes": done, "sha256": h.hexdigest(),
            "content_type": ctype, "fetched_at": datetime.now(UTC).isoformat()}


def main(argv):
    if "--list" in argv:
        for county, files in MANIFEST.items():
            for name, url in files:
                print(f"{county}\t{name}\t{url}")
        return 0
    counties = [a for a in argv if not a.startswith("-")] or list(MANIFEST)
    failures = 0
    for county in counties:
        outdir = os.path.join(DATA, county, "raw")
        os.makedirs(outdir, exist_ok=True)
        mpath = os.path.join(outdir, "MANIFEST.json")
        manifest = json.load(open(mpath)) if os.path.exists(mpath) else {}
        if not MANIFEST[county]:
            print(f"[{county}] no sources configured, skipping")
        for name, url in MANIFEST[county]:
            print(f"[{county}] {name}", flush=True)
            try:
                info = fetch(url, os.path.join(outdir, name))
            except Exception as e:  # keep going; report at the end
                print(f"    FAILED: {e}")
                failures += 1
                continue
            if info is None:
                print("    up to date")
            else:
                manifest[name] = info
                print(f"    {info['bytes'] >> 20} MB")
            with open(mpath, "w") as f:
                json.dump(manifest, f, indent=2)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
