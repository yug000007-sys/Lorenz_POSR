"""
Lorenz Merge & Dashboard App
=============================
  - Merge Files: upload a supplier's raw file (csv/xlsx/xls/xlsm/pdf/msg),
    auto-map its columns onto the 79-column master schema, review/fix,
    save the mapping, and add it to the merged dataset.
  - Mappings: view every supplier's saved mapping (against the master
    header) and delete individual columns or whole supplier mappings.
  - Dashboard: charts + full-data view over everything merged so far, plus
    a live view of the raw file currently uploaded.

Nothing from your raw or merged/downloaded files is ever written to disk
or cached — only the small {supplier -> column mapping} table is
persisted (in data/mappings.db) so you don't have to redo mapping work.
"""
import datetime as dt

import pandas as pd
import plotly.express as px
import streamlit as st

from master_header import MASTER_COLUMNS, SUPPLIERS
from utils import db
from utils.mapping import suggest_mapping
from utils.readers import UnsupportedFileError, read_supplier_file
from utils.transform import apply_mapping, to_excel_bytes

st.set_page_config(page_title="Lorenz Merge & Dashboard", layout="wide")

# ----------------------------------------------------------------------------
# Session state (in-memory only — cleared on refresh / explicit clear buttons)
# ----------------------------------------------------------------------------
defaults = {
    "merged_df": pd.DataFrame(columns=MASTER_COLUMNS),
    "upload_log": [],
    "current_raw_df": None,
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
            st.session_state.current_raw_df = None
            st.session_state.current_raw_name = None
            st.session_state.uploader_version += 1
            st.rerun()

    raw_df = None
    if uploaded_file is not None:
        try:
            raw_df, note = read_supplier_file(uploaded_file)
            st.session_state.current_raw_df = raw_df
            st.session_state.current_raw_name = uploaded_file.name
            st.session_state.current_supplier = supplier
            if note:
                st.info(note)
        except UnsupportedFileError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"Couldn't read this file: {e}")

    if raw_df is not None:
        st.caption(f"'{uploaded_file.name}' — {raw_df.shape[0]} rows, {raw_df.shape[1]} columns.")
        with st.expander("Preview full raw file (with header)", expanded=True):
            st.dataframe(raw_df, use_container_width=True)

        saved = db.load_mapping(supplier)
        suggested = suggest_mapping(
            MASTER_COLUMNS, list(raw_df.columns), saved_mapping=saved, supplier=supplier
        )

        st.subheader("2. Review / fix the column mapping")
        st.caption(
            "Each row is a column from your master Lorenz header. Pick which column from the "
            "uploaded file should fill it, or leave **-- None --**. Guesses come from this "
            "supplier's saved mapping first, then any other supplier's saved mapping with a "
            "matching header name, then name similarity. "
            "**Note:** if you map `PartNumberSubmitted`, `PartNumberActual` is auto-filled with "
            "the same values unless you map it separately here."
        )

        none_label = "-- None --"
        source_options = [none_label] + list(raw_df.columns)

        mapping_df = pd.DataFrame(
            {
                "Master Column (your given header)": MASTER_COLUMNS,
                "Source Column (from uploaded file)": [suggested.get(c) or none_label for c in MASTER_COLUMNS],
            }
        )

        edited = st.data_editor(
            mapping_df,
            use_container_width=True,
            hide_index=True,
            height=420,
            column_config={
                "Master Column (your given header)": st.column_config.TextColumn(disabled=True),
                "Source Column (from uploaded file)": st.column_config.SelectboxColumn(
                    options=source_options, required=True
                ),
            },
            key=f"mapping_editor_{supplier}",
        )

        final_mapping = {
            row["Master Column (your given header)"]: (
                None if row["Source Column (from uploaded file)"] == none_label
                else row["Source Column (from uploaded file)"]
            )
            for _, row in edited.iterrows()
        }

        st.subheader("3. Optional: set Invoice Date / Pay Date for this whole file")
        st.caption("Useful when the raw file doesn't include these columns itself.")
        d1, d2 = st.columns(2)
        with d1:
            use_invoice = st.checkbox("Apply one Invoice Date to every row in this file", key=f"use_inv_{supplier}")
            invoice_override = st.date_input("Invoice Date", value=dt.date.today(), key=f"inv_date_{supplier}", disabled=not use_invoice)
        with d2:
            use_pay = st.checkbox("Apply one Pay Date to every row in this file", key=f"use_pay_{supplier}")
            pay_override = st.date_input("Pay Date", value=dt.date.today(), key=f"pay_date_{supplier}", disabled=not use_pay)

        st.subheader("4. Save mapping & add to merged data")
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button(f"💾 Save mapping for {supplier}", use_container_width=True):
                db.save_mapping(supplier, final_mapping)
                st.success(f"Mapping saved for {supplier}. It will auto-apply next time and can help other suppliers too.")
        with c2:
            if st.button("➕ Add this file to merged data", type="primary", use_container_width=True):
                transformed = apply_mapping(
                    raw_df,
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
                    {"Supplier": supplier, "File": uploaded_file.name, "Rows added": len(transformed)}
                )
                st.success(f"Added {len(transformed)} rows from {uploaded_file.name} ({supplier}).")
        with c3:
            mapped_count = sum(1 for v in final_mapping.values() if v)
            st.metric("Columns mapped", f"{mapped_count} / {len(MASTER_COLUMNS)}")

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

    st.subheader("Saved supplier mappings")
    summary = db.list_summary()
    if not summary:
        st.info("No mappings saved yet. Save one from the Merge Files tab.")
    else:
        st.dataframe(pd.DataFrame(summary), use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("View / delete a mapping")
        mapped_suppliers = [row["Supplier"] for row in summary]
        pick = st.selectbox("Supplier", mapped_suppliers, key="mapping_view_supplier")

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
        st.subheader("Delete mappings for multiple suppliers at once")
        multi_pick = st.multiselect("Suppliers", mapped_suppliers, key="multi_supplier_delete")
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
    if st.session_state.current_raw_df is not None:
        st.subheader(f"Current raw file: {st.session_state.current_raw_name} ({st.session_state.current_supplier})")
        st.caption(f"{st.session_state.current_raw_df.shape[0]} rows, {st.session_state.current_raw_df.shape[1]} columns — shown in full, with header.")
        st.dataframe(st.session_state.current_raw_df, use_container_width=True)
        st.divider()

    df = st.session_state.merged_df

    if df.empty:
        st.info("Merge at least one supplier file in the **Merge Files** tab to see the merged dashboard.")
    else:
        work = df.copy()
        for numeric_col in ["Qty", "UnitCost", "UnitResale", "Sales", "Commissions", "Billings"]:
            if numeric_col in work.columns:
                work[numeric_col] = pd.to_numeric(work[numeric_col], errors="coerce")

        st.subheader("Filters")
        f1, f2 = st.columns([2, 1])
        with f1:
            suppliers_present = sorted(work["Supplier_name"].dropna().unique().tolist())
            chosen = st.multiselect("Supplier", suppliers_present, default=suppliers_present)
        with f2:
            st.write("")

        if chosen:
            work = work[work["Supplier_name"].isin(chosen)]

        st.subheader("Overview")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Rows", f"{len(work):,}")
        m2.metric("Suppliers", work["Supplier_name"].nunique())
        if "Sales" in work.columns and work["Sales"].notna().any():
            m3.metric("Total Sales", f"{work['Sales'].sum():,.2f}")
        else:
            m3.metric("Total Sales", "—")
        if "Commissions" in work.columns and work["Commissions"].notna().any():
            m4.metric("Total Commissions", f"{work['Commissions'].sum():,.2f}")
        else:
            m4.metric("Total Commissions", "—")

        st.divider()

        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            if "Sales" in work.columns and work["Sales"].notna().any():
                sales_by_supplier = (
                    work.groupby("Supplier_name", dropna=False)["Sales"]
                    .sum()
                    .sort_values(ascending=False)
                    .reset_index()
                )
                fig = px.bar(sales_by_supplier, x="Supplier_name", y="Sales", title="Sales by Supplier")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("No 'Sales' data mapped yet, so this chart is unavailable.")

        with chart_col2:
            if "Qty" in work.columns and work["Qty"].notna().any():
                qty_by_supplier = (
                    work.groupby("Supplier_name", dropna=False)["Qty"]
                    .sum()
                    .sort_values(ascending=False)
                    .reset_index()
                )
                fig = px.bar(qty_by_supplier, x="Supplier_name", y="Qty", title="Quantity by Supplier")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("No 'Qty' data mapped yet, so this chart is unavailable.")

        chart_col3, chart_col4 = st.columns(2)

        with chart_col3:
            if "Commissions" in work.columns and work["Commissions"].notna().any():
                comm_by_supplier = (
                    work.groupby("Supplier_name", dropna=False)["Commissions"]
                    .sum()
                    .sort_values(ascending=False)
                    .reset_index()
                )
                fig = px.bar(
                    comm_by_supplier, x="Supplier_name", y="Commissions", title="Commissions by Supplier"
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("No 'Commissions' data mapped yet, so this chart is unavailable.")

        with chart_col4:
            if "PartNumberSubmitted" in work.columns and "Qty" in work.columns and work["Qty"].notna().any():
                top_parts = (
                    work.groupby("PartNumberSubmitted", dropna=True)["Qty"]
                    .sum()
                    .sort_values(ascending=False)
                    .head(10)
                    .reset_index()
                )
                fig = px.bar(
                    top_parts,
                    x="Qty",
                    y="PartNumberSubmitted",
                    orientation="h",
                    title="Top 10 Part Numbers by Qty",
                )
                fig.update_layout(yaxis={"categoryorder": "total ascending"})
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("No part number / Qty data mapped yet, so this chart is unavailable.")

        if "Pay_Year" in work.columns and "Pay_Month" in work.columns and "Sales" in work.columns:
            trend = work.dropna(subset=["Pay_Year", "Pay_Month"]).copy()
            if not trend.empty and trend["Sales"].notna().any():
                trend["Period"] = trend["Pay_Year"].astype(str) + "-" + trend["Pay_Month"].astype(str).str.zfill(2)
                monthly = trend.groupby("Period", dropna=False)["Sales"].sum().reset_index().sort_values("Period")
                fig = px.line(monthly, x="Period", y="Sales", title="Sales Trend by Pay Month", markers=True)
                st.plotly_chart(fig, use_container_width=True)

        st.divider()
        st.subheader("Merged data (all columns)")
        st.dataframe(work, use_container_width=True)
