import sqlite3

db = sqlite3.connect('County/Dallas/dcad.db')

YOUR_ACCT = '325402100A0260000'

# Get comp account numbers
comps = db.execute("""
    SELECT i.ACCOUNT_NUM
    FROM account_info i
    WHERE i.NBHD_CD = '5AST09'
      AND i.ACCOUNT_NUM != ?
      AND (i.DEED_TXFR_DATE LIKE '%/2025' OR i.DEED_TXFR_DATE LIKE '%/2026')
""", [YOUR_ACCT]).fetchall()

all_accts = [YOUR_ACCT] + [c[0] for c in comps]
placeholders = ','.join(['?' for _ in all_accts])

rows = db.execute(f"""
    SELECT 
        i.ACCOUNT_NUM,
        i.STREET_NUM || ' ' || i.FULL_STREET_NAME as ADDRESS,
        i.DEED_TXFR_DATE,
        a.TOT_VAL,
        r.NUM_BEDROOMS,
        r.NUM_FULL_BATHS,
        r.NUM_HALF_BATHS,
        r.TOT_LIVING_AREA_SF,
        r.YR_BUILT,
        l.AREA_SIZE,
        l.AREA_UOM_DESC
    FROM account_info i
    LEFT JOIN account_apprl a ON i.ACCOUNT_NUM = a.ACCOUNT_NUM
    LEFT JOIN res_detail r ON i.ACCOUNT_NUM = r.ACCOUNT_NUM
    LEFT JOIN land l ON i.ACCOUNT_NUM = l.ACCOUNT_NUM AND l.SECTION_NUM = '1'
    WHERE i.ACCOUNT_NUM IN ({placeholders})
    ORDER BY CASE WHEN i.ACCOUNT_NUM = ? THEN 0 ELSE 1 END,
             i.DEED_TXFR_DATE DESC
""", all_accts + [YOUR_ACCT]).fetchall()

hdr = f"{'Address':<28} {'Sold':<12} {'Appraised':>10} {'Bed':>4} {'Bath':>6} {'SqFt':>7} {'Lot':>10} {'Yr':>5} {'$/SqFt':>7}"
print(hdr)
print('-' * 100)

for r in rows:
    addr = r[1][:27] if r[1] else '?'
    sold = r[2] if r[2] else ''
    tot = float(r[3]) if r[3] else 0
    beds = r[4] if r[4] else '-'
    full_bath = int(r[5]) if r[5] else 0
    half_bath = int(r[6]) if r[6] else 0
    bath_str = f"{full_bath}.5" if half_bath else str(full_bath)
    sqft = r[7] if r[7] else '-'
    yr = r[8] if r[8] else '-'
    lot_val = f"{float(r[9]):,.0f}" if r[9] else '-'
    lot_uom = (r[10] or '')[:4].strip()
    lot = f"{lot_val} {lot_uom}" if r[9] else '-'
    ppsf = f"${tot/float(sqft):,.0f}" if sqft != '-' and float(sqft) > 0 else '-'
    
    marker = ' <<<' if r[0] == YOUR_ACCT else ''
    print(f"{addr:<28} {sold:<12} ${tot:>9,.0f} {beds:>4} {bath_str:>6} {sqft:>7} {lot:>10} {yr:>5} {ppsf:>7}{marker}")

db.close()
