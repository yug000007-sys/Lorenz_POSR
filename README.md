# Lorenz Merge & Dashboard App

A Streamlit app for the **Lorenz** account that merges every supplier's raw
POS/Proj files into one standard 79-column table, remembering your setup
so you barely touch it after the first month.

Suppliers covered: ATP, Bravotek, Coilcraft, Comchip, Conec, CVI Lux, DEI,
Epson, Grayhill, Heatron, Hongfa, Kyocera, Leadertech, LEM, Macronix,
Nisshinbo, Shinelink, SiTime, Soracom, SunLed, Tecate, Wall, Winchester.

## How it works

1. **Pick a supplier, upload one or many files** — csv, xlsx, xls, xlsm,
   pdf, or Outlook .msg, all in one go.
2. **New sheet types get a one-time setup** — include or skip, header row
   (some sheets have title rows above it), and an **anchor column**: a
   column that's always filled on a real data row, used to automatically
   drop subtotal rows, blank separators, and stray pivot tables sitting
   below the real data. The app guesses a sensible anchor (preferring a
   date column) and header row; override if it's wrong. Sheets with
   several mini-tables stacked in one physical sheet (a title row followed
   by its own header row) are auto-split and handled individually.
3. **New columns get mapped once** — 🟢 pre-filled from memory or an exact
   name match, 🟡 new, pick once. Mapping is remembered **globally by
   header name** — map `"Comm Amt"` → `Commissions` for ATP, and any other
   supplier's file that also has a column called "Comm Amt" auto-maps too.
4. Click **Save mapping & add to merged data** — the sheet setup and every
   column mapping is written to disk and reused automatically next time a
   file with the same sheet names/headers comes in. Everything you've
   added, from every file/sheet, lives in one merged table.
5. Download the result as `.csv` or `.xlsx` — dates are cleaned to
   `YYYY-MM-DD` and money/rate-looking columns are rounded to 2 decimals,
   based on the standard column's name.

The **sidebar** lets you review/forget individual remembered sheet setups
and column mappings, edit the standard column list directly, and back up
or restore everything as one JSON file.

## Project structure

```
lorenz-merge-app/
├── app.py                 # Streamlit app: Merge Files / Dashboard tabs + sidebar
├── master_header.py        # Default 79-column schema + the 23-supplier list
├── utils/
│   ├── store.py              # JSON persistence: mappings, sheet profiles, standard headers
│   ├── readers.py             # Multi-format reading, header-row detection, anchor-column
│   │                             row filtering, stacked sub-table detection
│   └── transform.py            # Apply mapping, PartNumberActual mirror, date overrides,
│                                   date/money output formatting, csv/xlsx export
├── data/                   # Created automatically — mappings.json, sheet_profiles.json,
│                              standard_headers.json (no raw/merged data ever stored here)
├── requirements.txt
└── README.md
```

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Feature notes

### Global column-mapping memory
Every mapping is keyed by the **normalized source header name**, not by
supplier — teach the app a header once and it's recognized for every
supplier/sheet that reuses it. If a header genuinely means something
different for a specific supplier, just pick a different target in that
sheet's mapping step; the new choice becomes the remembered one going
forward (last save wins).

### Sheet setup memory
Each (supplier, sheet name) combination — e.g. `ATP → POS` vs `ATP →
Detail` — remembers its own header row, anchor column, and anchor type,
so you only do that setup once per sheet type, ever.

### PartNumberSubmitted → PartNumberActual
If you map a source column to `PartNumberSubmitted` but leave
`PartNumberActual` unmapped, its values are automatically copied into
`PartNumberActual` too.

### Invoice Date / Pay Date overrides
Optionally set a single Invoice Date and/or Pay Date to apply to every row
of everything you're about to add — handy when a supplier's raw file
doesn't include those columns itself.

### Supported file formats
- **csv / xlsx / xls / xlsm** — read directly, every sheet.
- **pdf** — the largest table found in the PDF is extracted. Works well
  for PDFs with real table structure (gridlines/borders); PDFs that are
  just loosely formatted text may not extract cleanly — export to
  CSV/Excel from the source system if so, or send a sample and a
  pattern-based parser (like the one used for certain commission
  statements) can be built for that specific layout.
- **msg** (Outlook email) — the first supported attachment (csv/xlsx/pdf)
  found in the email is extracted and read.

### Nothing raw is stored or cached
Uploaded files and the merged/downloaded file exist only in server memory
for your session — never written to disk, never passed through
`st.cache_data`/`st.cache_resource`. The only exception is a technical
necessity: parsing `.pdf`/`.msg` files requires the underlying libraries to
read from an actual file, so the app writes a temporary file to the OS
temp folder and deletes it immediately after reading. Use **Clear uploaded
files** to drop the current raw files from memory, and **Clear merged /
downloaded data & start over** to drop everything merged so far.

## Deploy with GitHub + Streamlit Community Cloud

1. Push this folder to a GitHub repo:
   ```bash
   git init
   git add .
   git commit -m "Initial Lorenz merge & dashboard app"
   git branch -M main
   git remote add origin https://github.com/<your-username>/lorenz-merge-app.git
   git push -u origin main
   ```
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in with
   GitHub, **New app** → pick this repo/branch → set main file to `app.py`
   → **Deploy**.

### A note on persistence

Mappings/sheet setups live in `data/*.json` in the app's own folder. This
persists perfectly for local use and a long-running Streamlit Cloud
instance (survives refreshes, logouts, other users' sessions). If the
Cloud instance sleeps/restarts or gets redeployed, the filesystem resets
to whatever's in the GitHub repo — so changes made *after* the last push
won't survive that.

To keep changes across restarts on Streamlit Cloud without a manual
`git push` every time:
- Use the sidebar's **⬇️ Download backup** occasionally and re-commit
  `data/*.json` to the repo, or
- Swap the storage backend for something external (a small database, a
  GitHub Gist, S3) by replacing the `load_json`/`save_json` functions in
  `utils/store.py` — the rest of the app doesn't need to change.

For self-hosted deployments (your own server, Docker, etc.) the local
`data/` folder persists normally and this isn't a concern.
