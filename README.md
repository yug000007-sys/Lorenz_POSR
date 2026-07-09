# Lorenz Merge & Dashboard App

A Streamlit app for the **Lorenz** account that:

1. Lets you upload each supplier's raw POS/Proj file and map its columns onto
   the fixed 79-column Lorenz master template (`master_header.py`,
   taken from `Merge_File_Lorenz.xlsx`).
2. Auto-suggests the mapping by matching column names, and remembers your
   corrections per supplier so next month's file for the same supplier
   maps itself.
3. Shows a dashboard (Sales/Qty/Commissions by supplier, top part numbers,
   monthly trend) over everything you've merged so far.
4. Lets you download the combined result as one `.xlsx` file.

Suppliers covered: ATP, Bravotek, Coilcraft, Comchip, Conec, CVI Lux, DEI,
Epson, Grayhill, Heatron, Hongfa, Kyocera, Leadertech, LEM, Macronix,
Nisshinbo, Shinelink, SiTime, Soracom, SunLed, Tecate, Wall, Winchester.

## Project structure

```
lorenz-merge-app/
├── app.py                # Streamlit app (Merge Files tab + Dashboard tab)
├── master_header.py       # The 79-column master schema + supplier list
├── utils/
│   ├── mapping.py          # Save/load per-supplier mappings, fuzzy auto-mapping
│   └── merge.py             # Read supplier files, apply mapping, export xlsx
├── mappings/                # Saved per-supplier column-mapping profiles (JSON)
├── requirements.txt
└── README.md
```

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open the local URL Streamlit prints (usually http://localhost:8501).

## How the mapping works

- The first time you upload a file for a supplier, the app fuzzy-matches its
  column names against the 79 master columns and pre-fills a best guess.
- You review/correct the guesses in an editable table, then click
  **💾 Save mapping for `<supplier>`**. This writes a JSON file to
  `mappings/<supplier>.json`.
- Next time you upload a file for that same supplier, the saved mapping is
  applied automatically (as long as the source file still has the same
  column names) — you'll only need to fix things if the supplier changes
  their file layout.
- Click **➕ Add this file to merged data** to append the transformed rows
  into the in-session merged dataset (used by both the download button and
  the Dashboard tab).

**Important — persistence on Streamlit Community Cloud:** the `mappings/`
folder lives on disk, so it persists across reruns *within the same running
app instance*. It will **not** persist across a redeploy/reboot of a free
Streamlit Cloud app, because that storage is ephemeral. Once you're happy
with a supplier's mapping, download it (or `mappings/*.json` as a whole) and
commit it into the GitHub repo so it ships with the next deploy. For a
sturdier setup later, the mapping store could be swapped for a small
database or Google Sheet — ask if you'd like that added.

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
4. Whenever you save new/updated supplier mappings you want to keep, pull
   them from the running app (or re-save locally) and push an update to the
   `mappings/` folder in the repo so future deploys start with them already
   in place.

## Notes / next steps you might want

- The merged dataset currently lives only in the browser session
  (`st.session_state`) — refreshing the page clears it. If you need it to
  persist between sessions/users, this can be wired up to a database or a
  shared file.
- Numeric columns (`Qty`, `UnitCost`, `UnitResale`, `Sales`, `Commissions`,
  `Billings`) are coerced to numbers for the dashboard; anything that fails
  to parse shows as blank in charts rather than breaking the app.
