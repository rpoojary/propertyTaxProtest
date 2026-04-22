"""Build a trimmed SQLite DB for the web app."""
import sqlite3, os
import argparse

parser = argparse.ArgumentParser(description='Build a trimmed SQLite DB for the web app.')
parser.add_argument('--input', required=True, help='Input SQLite database file (e.g. County/Dallas/dcad.db)')
parser.add_argument('--output', default='webapp/appraisal_lite.db', help='Output trimmed SQLite database file')
args = parser.parse_args()

src = sqlite3.connect(args.input)
dst_path = args.output
if os.path.exists(dst_path):
    os.remove(dst_path)
dst = sqlite3.connect(dst_path)

print("Creating tables...")

dst.execute("""CREATE TABLE account_info (
    ACCOUNT_NUM TEXT, STREET_NUM TEXT, FULL_STREET_NAME TEXT,
    PROPERTY_CITY TEXT, PROPERTY_ZIPCODE TEXT, DEED_TXFR_DATE TEXT,
    NBHD_CD TEXT, OWNER_NAME1 TEXT)""")

dst.execute("""CREATE TABLE account_apprl (
    ACCOUNT_NUM TEXT, TOT_VAL TEXT, IMPR_VAL TEXT, LAND_VAL TEXT)""")

dst.execute("""CREATE TABLE res_detail (
    ACCOUNT_NUM TEXT, NUM_BEDROOMS TEXT, NUM_FULL_BATHS TEXT,
    NUM_HALF_BATHS TEXT, TOT_LIVING_AREA_SF TEXT, YR_BUILT TEXT)""")

dst.execute("""CREATE TABLE land (
    ACCOUNT_NUM TEXT, SECTION_NUM TEXT, AREA_SIZE TEXT)""")

dst.execute("""CREATE TABLE applied_std_exempt (
    ACCOUNT_NUM TEXT, HOMESTEAD_EFF_DT TEXT)""")

tables = [
    ("account_info", "SELECT ACCOUNT_NUM,STREET_NUM,FULL_STREET_NAME,PROPERTY_CITY,PROPERTY_ZIPCODE,DEED_TXFR_DATE,NBHD_CD,OWNER_NAME1 FROM account_info", 8),
    ("account_apprl", "SELECT ACCOUNT_NUM,TOT_VAL,IMPR_VAL,LAND_VAL FROM account_apprl", 4),
    ("res_detail", "SELECT ACCOUNT_NUM,NUM_BEDROOMS,NUM_FULL_BATHS,NUM_HALF_BATHS,TOT_LIVING_AREA_SF,YR_BUILT FROM res_detail", 6),
    ("land", "SELECT ACCOUNT_NUM,SECTION_NUM,AREA_SIZE FROM land", 3),
    ("applied_std_exempt", "SELECT ACCOUNT_NUM,HOMESTEAD_EFF_DT FROM applied_std_exempt", 2),
]

for tbl, query, ncols in tables:
    print(f"  Copying {tbl}...")
    ph = ",".join(["?"] * ncols)
    cur = src.execute(query)
    batch = []
    count = 0
    while True:
        row = cur.fetchone()
        if row is None:
            break
        batch.append(row)
        if len(batch) >= 50000:
            dst.executemany(f"INSERT INTO {tbl} VALUES ({ph})", batch)
            batch = []
            count += 50000
    if batch:
        dst.executemany(f"INSERT INTO {tbl} VALUES ({ph})", batch)
        count += len(batch)
    dst.commit()
    print(f"    {count} rows")

print("Creating indexes...")
for sql in [
    "CREATE INDEX idx_ai_acct ON account_info(ACCOUNT_NUM)",
    "CREATE INDEX idx_ai_street ON account_info(STREET_NUM, FULL_STREET_NAME)",
    "CREATE INDEX idx_ai_zip ON account_info(PROPERTY_ZIPCODE)",
    "CREATE INDEX idx_ai_nbhd ON account_info(NBHD_CD)",
    "CREATE INDEX idx_aa_acct ON account_apprl(ACCOUNT_NUM)",
    "CREATE INDEX idx_rd_acct ON res_detail(ACCOUNT_NUM)",
    "CREATE INDEX idx_ld_acct ON land(ACCOUNT_NUM)",
    "CREATE INDEX idx_ex_acct ON applied_std_exempt(ACCOUNT_NUM)",
]:
    dst.execute(sql)
dst.commit()

print("Vacuuming...")
dst.execute("VACUUM")
dst.close()
src.close()

size = os.path.getsize(dst_path)
print(f"Done! {size/1024/1024:.0f} MB")
