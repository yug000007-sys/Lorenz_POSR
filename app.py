"""
Lorenz Merge & Dashboard App
=============================
  - Merge Files: upload a supplier's raw file (csv/xlsx/xls/xlsm/pdf/msg,
    including multi-sheet Excel files), pick the header row and filter out
    subtotal/pivot rows per sheet, auto-map each sheet's columns onto the
    79-column master schema, review/fix, save each sheet's mapping, and
    add any/all sheets to one merged dataset.
  - Mappings: view every supplier's (and sheet's) saved mapping against the
    master header, and delete individual columns or whole mappings.
  - Dashboard: plain data tables — the currently uploaded file's sheets,
    and everything merged so far.

Nothing from your raw or merged/downloaded files is ever written to disk
or cached — only the small {supplier -> column mapping} table is
persisted (in data/mappings.db) so you don't have to redo mapping work.
"""
import datetime as dt

import pandas as pd
import streamlit as st

from master_header import MASTER_COLUMNS, SUPPLIERS
from utils import db
from utils.mapping import suggest_mapping
from utils.readers import (
    UnsupportedFileError,
    apply_header_row,
    filter_required_columns,
    guess_header_row,
    read_raw_sheets,
)
from utils.transform import apply_mapping, to_excel_bytes

st.set_page_config(page_title="Lorenz Merge & Dashboard", layout="wide")

# ----------------------------------------------------------------------------
# Session state (in-memory only — cleared on refresh / explicit clear buttons)
# ----------------------------------------------------------------------------
defaults = {
    "merged_df": pd.DataFrame(columns=MASTER_COLUMNS),
    "upload_log": [],
    "current_raw_sheets": None,  # {sheet_name: raw_grid_df}
    "current_raw_name": None,
    "current_supplier": None,
    "uploader_version": 0,
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

st.title("📦 Lorenz — Supplier File Merge & Dashboard")

tab_merge, tab_mappings, tab_dashboard = st.tabs(["📥 Merge Files", "🗂️ Mappings", "📊 Dashboard"])

# ==============================================================================
# TAB 1 — MERGE FILES
# ==============================================================================
with tab_merge:
    st.subheader("1. Choose a supplier and upload their file")

    col_a, col_b, col_c = st.columns([1, 2, 1])
    with col_a:
        supplier = st.selectbox("Supplier", SUPPLIERS)
    with col_b:
        uploader_key = f"uploader_{supplier}_{st.session_state.uploader_version}"
        uploaded_file = st.file_uploader(
            f"Upload {supplier}'s raw file",
            type=["csv", "xlsx", "xlsm", "xls", "pdf", "msg"],
            key=uploader_key,
        )
    with col_c:
        st.write("")
        st.write("")
        if st.button("🗑️ Clear uploaded file", use_container_width=True):
            st.session_state.current_raw_sheets = None
            st.session_state.current_raw_name = None
            st.session_state.uploader_version += 1
            st.rerun()

    raw_sheets = None
    if uploaded_file is not None:
        try:
            raw_sheets, note = read_raw_sheets(uploaded_file)
            st.session_state.current_raw_sheets = raw_sheets
            st.session_state.current_raw_name = uploaded_file.name
            st.session_state.current_supplier = supplier
            if note:
                st.info(note)
        except UnsupportedFileError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"Couldn't read this file: {e}")

    if raw_sheets is not None:
        sheet_names = list(raw_sheets.keys())
        st.caption(f"'{uploaded_file.name}' has {len(sheet_names)} sheet(s): {', '.join(sheet_names)}.")

        chosen_sheets = st.multiselect(
            "Which sheet(s) do you want to map and merge?",
            sheet_names,
            default=sheet_names,
            help="Pick every sheet that contains real transaction rows. Skip pure summary/pivot "
            "sheets unless you specifically want their totals merged in too.",
        )

        st.subheader("2. Set up each sheet")
        sheet_results = {}  # sheet_name -> (cleaned_df, final_mapping)

        for sheet_name in chosen_sheets:
            raw_grid = raw_sheets[sheet_name]
            mapping_key = f"{supplier}::{sheet_name}"

            with st.expander(f"📄 Sheet: {sheet_name}", expanded=True):
                default_header = guess_header_row(raw_grid)
                header_row_1indexed = st.number_input(
                    "Header row number",
                    min_value=1,
                    max_value=max(len(raw_grid), 1),
                    value=default_header + 1,
                    key=f"header_row_{mapping_key}",
                    help="The row containing column names (title rows above it are ignored).",
                )
                headered = apply_header_row(raw_grid, header_row_1indexed - 1)

                required_cols = st.multiselect(
                    "Only keep rows where these column(s) are filled in",
                    options=list(headered.columns),
                    key=f"required_cols_{mapping_key}",
                    help="Use this to drop subtotal, blank, or pivot-table rows mixed into the sheet — "
                    "pick a column that's always filled on real data rows (e.g. a date or ID column).",
                )
                cleaned = filter_required_columns(headered, required_cols)
                st.caption(f"{len(headered)} raw rows → {len(cleaned)} kept after filtering.")
                st.dataframe(cleaned, use_container_width=True, height=250)

                saved = db.load_mapping(mapping_key)
                suggested = suggest_mapping(
                    MASTER_COLUMNS, list(cleaned.columns), saved_mapping=saved, supplier=mapping_key
                )

                st.caption(
                    "Pick which column from this sheet fills each master column, or leave **-- None --**. "
                    "**Note:** mapping `PartNumberSubmitted` auto-fills `PartNumberActual` too, unless "
                    "you map it separately."
                )
                none_label = "-- None --"
                source_options = [none_label] + list(cleaned.columns)
                mapping_df = pd.DataFrame(
                    {
                        "Master Column (your given header)": MASTER_COLUMNS,
                        "Source Column": [suggested.get(c) or none_label for c in MASTER_COLUMNS],
                    }
                )
                edited = st.data_editor(
                    mapping_df,
                    use_container_width=True,
                    hide_index=True,
                    height=380,
                    column_config={
                        "Master Column (your given header)": st.column_config.TextColumn(disabled=True),
                        "Source Column": st.column_config.SelectboxColumn(options=source_options, required=True),
                    },
                    key=f"mapping_editor_{mapping_key}",
                )
                final_mapping = {
                    row["Master Column (your given header)"]: (
                        None if row["Source Column"] == none_label else row["Source Column"]
                    )
                    for _, row in edited.iterrows()
                }
                sheet_results[sheet_name] = (cleaned, final_mapping)

                mc1, mc2 = st.columns(2)
                with mc1:
                    if st.button(f"💾 Save mapping for {sheet_name}", key=f"save_{mapping_key}", use_container_width=True):
                        db.save_mapping(mapping_key, final_mapping)
                        st.success(f"Mapping saved for {supplier} → {sheet_name}.")
                with mc2:
                    mapped_count = sum(1 for v in final_mapping.values() if v)
                    st.metric("Columns mapped", f"{mapped_count} / {len(MASTER_COLUMNS)}")

        st.subheader("3. Optional: set Invoice Date / Pay Date for this whole file")
        st.caption("Applied to every sheet you add below. Useful when the raw file doesn't include these columns itself.")
        d1, d2 = st.columns(2)
        with d1:
            use_invoice = st.checkbox("Apply one Invoice Date to every row", key="use_inv")
            invoice_override = st.date_input("Invoice Date", value=dt.date.today(), key="inv_date", disabled=not use_invoice)
        with d2:
            use_pay = st.checkbox("Apply one Pay Date to every row", key="use_pay")
            pay_override = st.date_input("Pay Date", value=dt.date.today(), key="pay_date", disabled=not use_pay)

        st.subheader("4. Add to merged data")
        if st.button("➕ Add all sheets above to merged data", type="primary", disabled=not chosen_sheets):
            total_added = 0
            for sheet_name in chosen_sheets:
                cleaned, final_mapping = sheet_results[sheet_name]
                transformed = apply_mapping(
                    cleaned,
                    final_mapping,
                    MASTER_COLUMNS,
                    supplier,
                    invoice_date_override=invoice_override if use_invoice else None,
                    pay_date_override=pay_override if use_pay else None,
                )
                st.session_state.merged_df = pd.concat(
                    [st.session_state.merged_df, transformed], ignore_index=True
                )
                st.session_state.upload_log.append(
                    {"Supplier": supplier, "File": f"{uploaded_file.name} — {sheet_name}", "Rows added": len(transformed)}
                )
                total_added += len(transformed)
            st.success(f"Added {total_added} rows total from {len(chosen_sheets)} sheet(s) of {uploaded_file.name}.")

    st.divider()
    st.subheader("Merge log")
    if st.session_state.upload_log:
        st.dataframe(pd.DataFrame(st.session_state.upload_log), use_container_width=True, hide_index=True)
        total_rows = len(st.session_state.merged_df)
        st.write(f"**Total merged rows so far: {total_rows}**")

        dl_col, reset_col = st.columns([1, 1])
        with dl_col:
            st.download_button(
                "⬇️ Download merged file (.xlsx)",
                data=to_excel_bytes(st.session_state.merged_df),
                file_name="Lorenz_Merged.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        with reset_col:
            if st.button("🗑️ Clear merged / downloaded data & start over", use_container_width=True):
                st.session_state.merged_df = pd.DataFrame(columns=MASTER_COLUMNS)
                st.session_state.upload_log = []
                st.rerun()
    else:
        st.info("No files merged yet. Upload a supplier file above and click **Add this file to merged data**.")

# ==============================================================================
# TAB 2 — MAPPINGS
# ==============================================================================
with tab_mappings:
    st.subheader("Master header (your given header)")
    with st.expander(f"Show all {len(MASTER_COLUMNS)} master columns"):
        st.dataframe(pd.DataFrame({"Master Column": MASTER_COLUMNS}), use_container_width=True, hide_index=True)

    st.subheader("Saved mappings (per supplier + sheet)")
    summary = db.list_summary()
    if not summary:
        st.info("No mappings saved yet. Save one from the Merge Files tab.")
    else:
        display_summary = pd.DataFrame(summary).rename(columns={"Supplier": "Supplier / Sheet"})
        st.dataframe(display_summary, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("View / delete a mapping")
        mapped_suppliers = [row["Supplier"] for row in summary]
        pick = st.selectbox("Supplier / Sheet", mapped_suppliers, key="mapping_view_supplier")

        current = db.load_mapping(pick)
        view_df = pd.DataFrame(
            {"Master Column (your given header)": list(current.keys()), "Source Column": list(current.values())}
        )
        st.caption(f"{len(current)} column(s) mapped for {pick}.")
        st.dataframe(view_df, use_container_width=True, hide_index=True)

        d1, d2 = st.columns(2)
        with d1:
            to_delete_cols = st.multiselect(
                "Delete specific column mapping(s)", options=list(current.keys()), key="cols_to_delete"
            )
            if st.button("🗑️ Delete selected column(s)", disabled=not to_delete_cols):
                db.delete_mapping(pick, master_columns=to_delete_cols)
                st.success(f"Deleted {len(to_delete_cols)} column mapping(s) for {pick}.")
                st.rerun()
        with d2:
            confirm = st.checkbox(f"Confirm delete ALL mappings for {pick}", key="confirm_delete_all")
            if st.button("🗑️ Delete entire supplier mapping", disabled=not confirm, type="primary"):
                db.delete_mapping(pick)
                st.success(f"Deleted all mappings for {pick}.")
                st.rerun()

        st.divider()
        st.subheader("Delete mappings for multiple supplier/sheet entries at once")
        multi_pick = st.multiselect("Supplier / Sheet", mapped_suppliers, key="multi_supplier_delete")
        confirm_multi = st.checkbox("Confirm delete ALL mappings for the suppliers selected above", key="confirm_multi")
        if st.button("🗑️ Delete all selected suppliers' mappings", disabled=not (multi_pick and confirm_multi)):
            for s in multi_pick:
                db.delete_mapping(s)
            st.success(f"Deleted mappings for: {', '.join(multi_pick)}.")
            st.rerun()

# ==============================================================================
# TAB 3 — DASHBOARD
# ==============================================================================
with tab_dashboard:
    if st.session_state.current_raw_sheets:
        st.subheader(f"Current raw file: {st.session_state.current_raw_name} ({st.session_state.current_supplier})")
        for sheet_name, raw_grid in st.session_state.current_raw_sheets.items():
            st.caption(f"Sheet: {sheet_name} — {raw_grid.shape[0]} rows, {raw_grid.shape[1]} columns (raw, as uploaded).")
            st.dataframe(raw_grid, use_container_width=True)
        st.divider()

    df = st.session_state.merged_df
    st.subheader("Merged data")
    if df.empty:
        st.info("Merge at least one supplier file in the **Merge Files** tab to see it here.")
    else:
        st.caption(f"{df.shape[0]} rows, {df.shape[1]} columns.")
        st.dataframe(df, use_container_width=True)
