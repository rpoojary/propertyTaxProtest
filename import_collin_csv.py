import csv
import sqlite3
import os

CSV_PATH = 'County/Collin/Property_Tax_Protest_325402100A0260000.csv'
DB_PATH = 'County/Collin/collin.db'

if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

db = sqlite3.connect(DB_PATH)

print("Building Collin County Tables...")
db.execute("""CREATE TABLE account_info (
    ACCOUNT_NUM TEXT, STREET_NUM TEXT, FULL_STREET_NAME TEXT,
    PROPERTY_CITY TEXT, PROPERTY_ZIPCODE TEXT, DEED_TXFR_DATE TEXT,
    NBHD_CD TEXT, OWNER_NAME1 TEXT)""")

db.execute("""CREATE TABLE account_apprl (
    ACCOUNT_NUM TEXT, TOT_VAL TEXT, IMPR_VAL TEXT, LAND_VAL TEXT)""")

db.execute("""CREATE TABLE res_detail (
    ACCOUNT_NUM TEXT, NUM_BEDROOMS TEXT, NUM_FULL_BATHS TEXT,
    NUM_HALF_BATHS TEXT, TOT_LIVING_AREA_SF TEXT, YR_BUILT TEXT)""")

db.execute("""CREATE TABLE land (
    ACCOUNT_NUM TEXT, SECTION_NUM TEXT, AREA_SIZE TEXT)""")

db.execute("""CREATE TABLE applied_std_exempt (
    ACCOUNT_NUM TEXT, HOMESTEAD_EFF_DT TEXT)""")

def clean_num(val):
    if not val:
        return '0'
    return val.replace(',', '').strip()

print("Parsing CSV...")

batch_info = []
batch_apprl = []
batch_res = []
batch_land = []
batch_exempt = []

count = 0
with open(CSV_PATH, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        acct = row.get('propID', '').strip()
        if not acct:
            continue
            
        # Address construction
        st_num = row.get('situsBldgNum', '').strip()
        st_pre = row.get('situsStreetPrefix', '').strip()
        st_name = row.get('situsStreetName', '').strip()
        st_suf = row.get('situsStreetSuffix', '').strip()
        
        full_st = []
        if st_pre: full_st.append(st_pre)
        if st_name: full_st.append(st_name)
        if st_suf: full_st.append(st_suf)
        full_st_str = " ".join(full_st)
        
        # Info
        batch_info.append((
            acct,
            st_num,
            full_st_str,
            row.get('situsCity', '').strip(),
            row.get('situsZip', '').strip(),
            row.get('deedEffDate', '').strip(),
            row.get('nbhdCode', '').strip(),
            row.get('ownerName', '').strip()
        ))
        
        # Appraisal
        batch_apprl.append((
            acct,
            clean_num(row.get('currValAppraised', '')),
            clean_num(row.get('currValImprv', '')),
            clean_num(row.get('currValLand', ''))
        ))
        
        # Residential details (default beds and baths to 0 for missing columns)
        batch_res.append((
            acct,
            '0', '0', '0', # Beds, FBath, HBath
            clean_num(row.get('imprvMainArea', '')),
            row.get('imprvYearBuilt', '').strip()
        ))
        
        # Land
        batch_land.append((
            acct,
            '1',
            clean_num(row.get('landSizeSqft', ''))
        ))
        
        # Exemptions
        is_homestead = row.get('exemptHmstdFlag', '').strip().lower() == 'true'
        batch_exempt.append((
            acct,
            'Y' if is_homestead else ''
        ))
        
        count += 1
        if count % 20000 == 0:
            db.executemany("INSERT INTO account_info VALUES (?,?,?,?,?,?,?,?)", batch_info)
            db.executemany("INSERT INTO account_apprl VALUES (?,?,?,?)", batch_apprl)
            db.executemany("INSERT INTO res_detail VALUES (?,?,?,?,?,?)", batch_res)
            db.executemany("INSERT INTO land VALUES (?,?,?)", batch_land)
            db.executemany("INSERT INTO applied_std_exempt VALUES (?,?)", batch_exempt)
            
            batch_info, batch_apprl, batch_res, batch_land, batch_exempt = [], [], [], [], []
            print(f"Processed {count} rows...")

# Insert remaining
if batch_info:
    db.executemany("INSERT INTO account_info VALUES (?,?,?,?,?,?,?,?)", batch_info)
    db.executemany("INSERT INTO account_apprl VALUES (?,?,?,?)", batch_apprl)
    db.executemany("INSERT INTO res_detail VALUES (?,?,?,?,?,?)", batch_res)
    db.executemany("INSERT INTO land VALUES (?,?,?)", batch_land)
    db.executemany("INSERT INTO applied_std_exempt VALUES (?,?)", batch_exempt)

print(f"Total processed: {count} accounts.")
db.commit()
db.close()
print("Success! collin.db generated.")
