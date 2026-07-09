"""
Lorenz Merge & Dashboard App
=============================
Streamlit app that:
  1. Lets you upload raw POS/Proj files from any of Lorenz's 23 suppliers,
     auto-maps their columns onto the fixed 79-column master schema
     (with manual review/fix + savable per-supplier mapping profiles), and
  2. Gives you a dashboard over the combined, merged data, and
  3. Lets you download the final merged file as .xlsx.
"""
import pandas as pd
import plotly.express as px
import streamlit as st

from master_header import MASTER_COLUMNS, SUPPLIERS
from utils.mapping import load_mapping, save_mapping, suggest_mapping
from utils.merge import apply_mapping, read_supplier_file, to_excel_bytes

st.set_page_config(page_title="Lorenz Merge & Dashboard", layout="wide")

# ----------------------------------------------------------------------------
# Session state
# ----------------------------------------------------------------------------
if "merged_df" not in st.session_state:
    st.session_state.merged_df = pd.DataFrame(columns=MASTER_COLUMNS)
if "upload_log" not in st.session_state:
    st.session_state.upload_log = []  # list of dicts: supplier, filename, rows
if "pending_df" not in st.session_state:
    st.session_state.pending_df = None
if "pending_mapping" not in st.session_state:
    st.session_state.pending_mapping = None

st.title("📦 Lorenz — Supplier File Merge & Dashboard")

tab_merge, tab_dashboard = st.tabs(["📥 Merge Files", "📊 Dashboard"])

# ==============================================================================
# TAB 1 — MERGE FILES
# ==============================================================================
with tab_merge:
    st.subheader("1. Choose a supplier and upload their file")

    col_a, col_b = st.columns([1, 2])
    with col_a:
        supplier = st.selectbox("Supplier", SUPPLIERS)
    with col_b:
        uploaded_file = st.file_uploader(
            f"Upload {supplier}'s raw POS/Proj file",
            type=["csv", "xlsx", "xlsm", "xls"],
            key=f"uploader_{supplier}",
        )

    if uploaded_file is not None:
        try:
            raw_df = read_supplier_file(uploaded_file)
        except Exception as e:
            st.error(f"Couldn't read this file: {e}")
            raw_df = None

        if raw_df is not None:
            st.caption(f"File has {raw_df.shape[0]} rows and {raw_df.shape[1]} columns.")
            with st.expander("Preview raw file (first 10 rows)"):
                st.dataframe(raw_df.head(10), use_container_width=True)

            saved = load_mapping(supplier)
            suggested = suggest_mapping(MASTER_COLUMNS, list(raw_df.columns), saved_mapping=saved)

            st.subheader("2. Review / fix the column mapping")
            st.caption(
                "Each row is a column in the Lorenz master template. Pick which column "
                "from the uploaded file it should come from, or leave it as **-- None --** "
                "to leave that field blank for this supplier."
            )

            none_label = "-- None --"
            source_options = [none_label] + list(raw_df.columns)

            mapping_df = pd.DataFrame(
                {
                    "Master Column": MASTER_COLUMNS,
                    "Source Column": [suggested.get(c) or none_label for c in MASTER_COLUMNS],
                }
            )

            edited = st.data_editor(
                mapping_df,
                use_container_width=True,
                hide_index=True,
                height=420,
                column_config={
                    "Master Column": st.column_config.TextColumn(disabled=True),
                    "Source Column": st.column_config.SelectboxColumn(
                        options=source_options, required=True
                    ),
                },
                key=f"mapping_editor_{supplier}",
            )

            final_mapping = {
                row["Master Column"]: (None if row["Source Column"] == none_label else row["Source Column"])
                for _, row in edited.iterrows()
            }

            st.subheader("3. Save mapping & add to merged data")
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button(f"💾 Save mapping for {supplier}", use_container_width=True):
                    path = save_mapping(supplier, final_mapping)
                    st.success(f"Mapping saved to `{path.relative_to(path.parent.parent)}`.")
            with c2:
                if st.button("➕ Add this file to merged data", type="primary", use_container_width=True):
                    transformed = apply_mapping(raw_df, final_mapping, MASTER_COLUMNS, supplier)
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
            if st.button("🗑️ Clear merged data & start over", use_container_width=True):
                st.session_state.merged_df = pd.DataFrame(columns=MASTER_COLUMNS)
                st.session_state.upload_log = []
                st.rerun()
    else:
        st.info("No files merged yet. Upload a supplier file above and click **Add this file to merged data**.")

# ==============================================================================
# TAB 2 — DASHBOARD
# ==============================================================================
with tab_dashboard:
    df = st.session_state.merged_df

    if df.empty:
        st.info("Merge at least one supplier file in the **Merge Files** tab to see the dashboard.")
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
        st.subheader("Merged data")
        st.dataframe(work, use_container_width=True)
