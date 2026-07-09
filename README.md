# Lorenz Merge & Dashboard App

A Streamlit app for the **Lorenz** account that:

1. Lets you upload each supplier's raw POS/Proj file (**csv, xlsx, xls, xlsm,
   pdf, or Outlook .msg**) and map its columns onto the fixed 79-column
   Lorenz master template (`master_header.py`, taken from
   `Merge_File_Lorenz.xlsx`).
2. Auto-suggests the mapping using: this supplier's own saved mapping →
   any other supplier's saved mapping that used the same header name →
   fuzzy name matching — and remembers your corrections so future files
   map themselves.
3. Lets you view, and delete (partially or entirely), any supplier's saved
   mapping from a dedicated **Mappings** tab.
4. Shows a dashboard (Sales/Qty/Commissions by supplier, top part numbers,
   monthly trend, plus the full merged table) over everything you've
   merged so far, and a live full view of whatever raw file is currently
   uploaded.
5. Lets you download the combined result as one `.xlsx` file.

Suppliers covered: ATP, Bravotek, Coilcraft, Comchip, Conec, CVI Lux, DEI,
Epson, Grayhill, Heatron, Hongfa, Kyocera, Leadertech, LEM, Macronix,
Nisshinbo, Shinelink, SiTime, Soracom, SunLed, Tecate, Wall, Winchester.

## Project structure

```
lorenz-merge-app/
├── app.py                # Streamlit app: Merge Files / Mappings / Dashboard tabs
├── master_header.py       # The 79-column master schema + supplier list
├── utils/
│   ├── db.py                # SQLite-backed mapping storage (save/load/list/delete)
│   ├── mapping.py            # Auto-mapping suggestion (own → cross-supplier → fuzzy)
│   ├── readers.py            # Multi-format file reading (csv/xlsx/pdf/msg)
│   └── transform.py           # Apply mapping, PartNumberActual mirror, date overrides, xlsx export
├── data/                  # Created automatically — holds only mappings.db (no raw/merged data)
├── requirements.txt
└── README.md
```

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open the local URL Streamlit prints (usually http://localhost:8501).

## Feature notes

### Mapping persistence
Every supplier's mapping is stored in a single SQLite file,
`data/mappings.db` — not in browser/session state — so it survives page
refreshes, logging out, and restarting the app. It only ever stores
`{supplier, master column, source column}` triples, never any of your
actual row data.

> **Hosting caveat:** on free/ephemeral hosts (e.g. Streamlit Community
> Cloud's default tier), the disk is reset on a redeploy or a cold restart
> after inactivity. `data/mappings.db` will survive normal use (refreshes,
> logouts, other users' sessions) but not a full redeploy unless you either
> (a) periodically commit the updated `data/mappings.db` file back into the
> GitHub repo, or (b) host on something with a persistent volume (a small
> VPS, Docker with a mounted volume, etc.). Say the word if you'd like this
> wired up to a proper always-on database instead.

### Cross-supplier auto-mapping
If you've already mapped, say, `"Invoice Date"` → `InvoiceDate` for one
supplier, any other supplier's file that also has a column literally named
"Invoice Date" (case/spacing-insensitive) will auto-map to `InvoiceDate`
too — you only need to teach the app a header once.

### PartNumberSubmitted → PartNumberActual
If you map a source column to `PartNumberSubmitted` but leave
`PartNumberActual` unmapped, its values are automatically copied into
`PartNumberActual` as well. Map `PartNumberActual` explicitly if a
supplier's file has a genuinely different "actual" part number column.

### Invoice Date / Pay Date overrides
Under the mapping table, you can optionally set a single Invoice Date
and/or Pay Date to apply to every row of the file you're about to add —
handy when a supplier's raw file doesn't include those columns itself.
This is per-upload, so each file (even across multiple uploads in the same
session) can carry its own date.

### Supported file formats
- **csv / xlsx / xls / xlsm** — read directly.
- **pdf** — the largest table found in the PDF is extracted. Works well for
  PDFs with real table structure (gridlines/borders); PDFs that are just
  loosely formatted text may not extract cleanly — export to CSV/Excel from
  the source system if so.
- **msg** (Outlook email) — the first supported attachment (csv/xlsx/pdf)
  found in the email is extracted and read.

### Nothing raw is stored or cached
Uploaded files and the merged/downloaded file exist only in server memory
for your session — they are **never** written to disk and **never** passed
through `st.cache_data`/`st.cache_resource`. The only exception is a
technical necessity: parsing `.pdf`/`.msg` files requires the underlying
libraries to read from an actual file, so the app writes a temporary file
to the OS temp folder and deletes it immediately after reading — it's never
persisted or reused. Use the **Clear uploaded file** button to drop the
current raw file from memory, and **Clear merged / downloaded data & start
over** to drop everything merged so far.

## Deploy with GitHub + Streamlit Community Cloud

1. Create a new GitHub repo (e.g. `lorenz-merge-app`) and push this folder:
   ```bash
   git init
   git add .
   git commit -m "Initial Lorenz merge & dashboard app"
   git branch -M main
   git remote add origin https://github.com/<your-username>/lorenz-merge-app.git
   git push -u origin main
   ```
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in with
   GitHub, click **New app**, pick this repo/branch, and set the main file
   to `app.py`.
3. Deploy. Streamlit Cloud installs `requirements.txt` automatically.
4. See the mapping persistence caveat above for keeping mappings across
   redeploys.
