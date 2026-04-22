# Local Appraisal District Property Tax Protest Helper

A lean, flexible web application designed to help homeowners explore local appraisal district property records, find comparable sales (comps), and build formatted cases to protest their property tax valuations. 

This system has been generalized to accept databases from any county, provided the raw SQLite export follows the standard layout.

## 1. Setup & Installation
Ensure you have Python 3 installed on your computer.

1. Open your terminal and navigate to the project folder (`DCAD2026_CURRENT`).
2. Install the required web dependencies via pip:
   ```bash
   pip3 install -r webapp/requirements.txt
   ```

## 2. Preparing the Database

The web app requires a lightweight version of the appraisal database to remain fast. You must build this `appraisal_lite.db` file from your county's raw SQLite export.

1. Place your county's raw database in its respective folder (e.g., `County/Collin/collin.db` or `County/Dallas/dcad.db`).
2. Run the build script, specifying your input database and the output location:
   ```bash
   python3 build_lite_db.py --input County/Dallas/dcad.db --output webapp/appraisal_lite.db
   ```
   *(Wait a few moments for the script to copy the tables, build the indexes, and vacuum the database).*

## 3. Running the Web App

Once your lightweight database is generated, start the local development server:

```bash
python3 webapp/app.py
```

The server will boot up. Open your web browser and navigate to:
**http://127.0.0.1:5000**

## 4. Using the Tool
- **Search**: Type an address or account number to locate a specific property.
- **Disclosures**: Check off any property issues (like age/condition) to deduct from your market value.
- **Repair Costs**: Input specific dollar amounts from repair estimates.
- **Protest**: Once configured, click the "Draft Protest Document" button to download a formatted HTML sheet you can print to PDF and submit to your local CAD!
