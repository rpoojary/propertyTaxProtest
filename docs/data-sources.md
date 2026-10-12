# County data sources

Verified 2026-10-12. Download with `python scripts/fetch_data.py [county ...]`;
files land in `data/<county>/raw/` (gitignored) with a `MANIFEST.json`
recording URL, size, sha256 and fetch time. None of these sources state a
license; all are published by the appraisal districts for public download.

**No county publishes sale prices** (Texas is a non-disclosure state). Deed
dates are available everywhere, so "recently transferred" can be derived, but
values are always *appraised* values.

All parcel shapefiles are NAD83 Texas State Plane North Central (EPSG:2276,
US feet). Reproject to WGS84 for lat/lon.

## Coverage summary

| | Dallas | Collin | Tarrant | Denton |
|---|---|---|---|---|
| Status | ✅ downloaded | ✅ downloaded | ✅ downloaded | ❌ host blocked here |
| Accounts | 827,412 | 509,444 (2027 roll) / 502,479 (2026) | 669,972 current | — |
| Appraised value | ✅ | ✅ | ✅ | |
| Living area / year built | ✅ | ✅ | ✅ | |
| Bedrooms / baths | ✅ | ✅ 84% / 88% of res. (`CCAD-Appraisal-Data.csv` only) | ❌ not published | |
| Land size | ✅ | ✅ | ✅ | |
| Quality / condition | CDU rating, bldg class | class code | ✅ comp attribute file | |
| Neighborhood code | ✅ | ✅ + nbhd adj. % | market area | |
| Deed / transfer date | ✅ | ✅ | ✅ | |
| Prior-year value | `PREV_MKT_VAL` | `prevVal*`, `cert_*` | 2025 certified file | |
| ARB protest outcomes | ✅ notified/new/panel value | ✅ `ARBProtests*.csv` (not fetched) | `ARB_Indicator` flag only | |
| Parcel geometry | ✅ key `Acct` | ✅ key `PROP_ID` | ✅ key `TAXPIN` = `GIS_Link` | |

## Dallas — Dallas Central Appraisal District

- Index page: `https://olp.dallascad.org/DataProducts.aspx` (the `www.` host
  currently returns an error page for DataProducts/GISDataProducts, but the
  file URLs themselves work).
- Files are served via
  `https://www.dallascad.org/ViewPDFs.aspx?type=3&id=\\DCAD.ORG\WEB\WEBDATA\WEBFORMS\<folder>\<file>`.

| File | Contents |
|---|---|
| `DCAD2026_CURRENT.zip` (188 MB) | 2026 certified roll with supplemental changes, comma-delimited |
| `DCAD2027_CURRENT.zip` (163 MB) | 2027 "most current ownership" (values still 2026 until notices) |
| `ARB_CURRENT.zip` | ARB protests 2022–2026: `NOTIFIED_VAL`, `NEW_VAL`, `PANEL_VAL`, dates, resolution codes |
| `PARCEL_GEOM.zip` (GIS PRODUCTS folder) | 697,554 polygons; fields `Acct`, `Type`, `RecAcs` |

Also available, not fetched: certified rolls 2022–2025, rolls frozen at
certification, BPP detail, fixed-format appraisal rolls, Mail 1/2/3 notice
data, `ARB_ARCHIVE.zip`.

Roll tables (inside the zip, all keyed by `ACCOUNT_NUM` + `APPRAISAL_YR`):
`ACCOUNT_INFO` (address, `NBHD_CD`, `DEED_TXFR_DATE`, owner),
`ACCOUNT_APPRL_YEAR` (`IMPR_VAL`, `LAND_VAL`, `TOT_VAL`, `HMSTD_CAP_VAL`,
`PREV_MKT_VAL`, `SPTD_CODE`), `RES_DETAIL` (`TOT_LIVING_AREA_SF`, `YR_BUILT`,
`EFF_YR_BUILT`, `CDU_RATING_DESC`, `NUM_BEDROOMS`, `NUM_FULL_BATHS`,
`NUM_HALF_BATHS`, `POOL_IND`, stories, construction), `RES_ADDL` (garages,
outbuildings with value), `LAND` (`AREA_SIZE`, `AREA_UOM_DESC`, `VAL_AMT`),
`APPLIED_STD_EXEMPT`, `ACCT_EXEMPT_VALUE`, `TOTAL_EXEMPTION`, `COM_DETAIL`,
`TAXABLE_OBJECT`, `MULTI_OWNER`, `ACCOUNT_TIF`. The zip includes
`DCAD_Certified_READ_ME.rtf` with the full field layout.

## Collin — Collin Central Appraisal District

- Index pages: `https://collincad.org/category/appraisal-data-exports/` and
  `/category/gis-downloads/`. Both link into a Cerberus FTP web share whose
  listing is JS-rendered, but direct `GET`s of file URLs work:
  - Appraisal data: `https://link.collincad.org/public/folder/1j1vp-rhx06rqkh3vz2ipw/AppraisalData/<file>`
  - GIS: `https://link.collincad.org/public/folder/blc8m6dbs0glddi_ixn5-a/CurrentGIS/<file>`
- Updated nightly; this replaces the data.gov / data.austintexas.gov guess.

| File | Contents |
|---|---|
| `CCAD-Appraisal-Data.csv` (359 MB) | 2027 roll, snake_case columns, **includes `beds`, `baths`, `stories`, `pool`, `class_cd`, `hood_cd`, `eff_yr_blt`**; 2026 certified values in `cert_*` |
| `AppraisalData-Public-2026.csv` (378 MB) | 2026 roll, camelCase; `currVal*`, `prevVal*`, `noticeVal*`. No beds/baths. This is the format the current `import_collin_csv.py` reads. |
| `AppraisalData-Public.csv` | Same layout, current (2027) year |
| `CodeFileLists.csv` | Code tables (protest reasons, state codes, etc.) |
| `NbhdList.csv` | Neighborhood codes with land/improvement adjustment % by year |
| `LiteDatabase_FileLayout.pdf` | Layout for `LiteDatabaseCurrent.zip` (not fetched) |
| `parcels_with_appraisal_data_R5.zip` | 441,317 polygons with the full `CCAD-Appraisal-Data` attributes joined; key `PROP_ID` |

Also available, not fetched: `AppraisalData-Public-2011…2025.csv`,
`PropEntityVal-Public*.csv` (per-taxing-unit taxable values),
`ARBProtests.csv` + `ARBProtests_2018-2025.csv`, `BuildingPermits.csv`,
`ApprNotices.csv`, `EntityList.csv`, `LiteDatabaseCurrent.zip`,
`parcels_no_AD.zip`, `subdivisions.zip`, `Schools.zip`, `City_limits.zip`.
`OwnerPropList.csv` / `AgentPropList.csv` exist but carry owner data we
should not surface.

**Fix for known issue:** `import_collin_csv.py` sets beds/baths to 0 because
it reads `AppraisalData-Public`. Use `CCAD-Appraisal-Data.csv` (join on
`prop_id` = `propID`) for beds/baths.

## Tarrant — Tarrant Appraisal District

- Index page: `https://www.tad.org/resources/data-downloads` (the `www6.`
  host in the old roadmap 404s). Files under `https://www.tad.org/content/`.

| File | Contents |
|---|---|
| `PropertyData(Delimited)_R.ZIP` | Current (2026) residential roll, pipe-delimited, 669,972 rows |
| `PropertyData_R_2025(Certified).ZIP` | 2025 certified residential roll (fixed-width padded, pipe-delimited) |
| `PropertyData_Exemptions_2025(Certified).ZIP` | Exemptions per account |
| `2026ResidentialCompAttributeData_1.zip` | xlsx keyed by `PIN`: market area, improvement type/style, **quality, condition**, year built, effective year, main area, land/garage/pool/outbuilding values, **Market Indicated Value, Equity Indicated Value** |
| `2026ResidentialFeaturesValue.zip` | xlsx: per-PIN improvement detail (garage, pool, …) and value |
| `PropertyData&PropertyLocationLayouts.pdf` | Field layout |
| `gis-data/Parcels.zip` | `parcels_20260730.shp`, 696,473 polygons; key `TAXPIN` (matches `GIS_Link`) |

Main roll fields: `Account_Num`, `Situs_Address`, `Property_Class`,
`State_Use_Code`, `Deed_Date`, `Land_Value`, `Improvement_Value`,
`Total_Value`, `Appraised_Value`, `Living_Area`, `Year_Built`, `Land_SqFt`,
`Swimming_Pool_Ind`, `ARB_Indicator`, `GIS_Link`. `Num_Bedrooms`,
`Num_Bathrooms` and `Garage_Capacity` are present but **0 for 100% of
residential rows**, so Tarrant comps must not rely on beds/baths.

Also available, not fetched: commercial/mineral/personal rolls (`_C`, `_M`,
`_P`), supplemental certified files 2021–2025, certified rolls 2021–2024,
median ratio PDFs by ISD, residential appraisal manual, prior-year comp
attribute files, `Parcels_GeoDatabase.zip`, neighborhoods/schools/cities layers.

## Denton — Denton Central Appraisal District

Not downloaded: `www.dentoncad.com` is a True Prodigy app that calls
`prod-container.trueprodigyapi.com`, and the exports are hosted on
`dentoncad.net` and `denton.prodigycad.com`. All three are denied by this
cloud environment's network policy. Leads to verify once allowed:

- `https://denton.prodigycad.com/data-downloads` — bulk appraisal CSV, code
  tables, weekly GIS shapefile exports.
- `https://dentoncad.net/data/_uploaded/files/datafiles/2025/CertifiedDataAllProperty/Denton_AppraisalDataExtracts_ALL(CERTIFIED).zip`
  (~413 MB, July 2025); look for a `2026/` sibling.

Domains to add to the environment's allowed list: `dentoncad.net`,
`*.dentoncad.net`, `*.prodigycad.com`, `*.trueprodigyapi.com`.
