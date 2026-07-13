"""
Lorenz Merge & Dashboard App (v2)
===================================
Architecture mirrors the reference "POS Header Mapper" app:
  - Column mappings are learned GLOBALLY by normalized header name (map
    "Comm Amt" -> Commissions once, it auto-applies to every future
    supplier/sheet that has a column called "Comm Amt" too).
  - Each (supplier, sheet name) is set up once — header row, and an
    "anchor" column that's always filled on a real data row (used to
    auto-drop subtotal/pivot/blank rows) — and remembered from then on.
  - Sheets with multiple stacked mini-tables (a one-cell marker row
    followed by its own header row) are auto-split into separate
    sub-tables.
  - Upload one or many files at once; everything included merges into one
    output table, downloadable as .csv or .xlsx.
  - The sidebar lets you review/forget individual remembered mappings and
    sheet setups, edit the standard header list, and back up/restore all
    of the above as one JSON file.

Nothing from your raw or merged/downloaded files is ever written to disk
or cached — only the small JSON memory files in data/ are persisted.
"""
import datetime as dt
import json

import pandas as pd
import streamlit as st

from master_header import MASTER_COLUMNS, SUPPLIERS
from utils import store
from utils.readers import (
    UnsupportedFileError,
    apply_header_row,
    detect_header_row,
    detect_subtables,
    extract_valid_rows,
    guess_anchor,
    read_raw_sheets,
)
from utils.gridview import show_excel_grid
from utils.transform import apply_mapping, format_output_df, to_csv_bytes, to_excel_bytes

st.set_page_config(page_title="Lorenz Merge & Dashboard", layout="wide")

IGNORE_LABEL = "-- Ignore --"
ANCHOR_TYPES = ["date", "number", "text"]

# ----------------------------------------------------------------------------
# Session state
# ----------------------------------------------------------------------------
if "std_headers" not in st.session_state:
    st.session_state.std_headers = store.load_standard_headers(MASTER_COLUMNS)
if "mappings" not in st.session_state:
    st.session_state.mappings = store.load_mappings()
if "sheet_profiles" not in st.session_state:
    st.session_state.sheet_profiles = store.load_sheet_profiles()
if "merged_df" not in st.session_state:
    st.session_state.merged_df = pd.DataFrame(columns=st.session_state.std_headers)
if "upload_log" not in st.session_state:
    st.session_state.upload_log = []
if "current_file_sheets" not in st.session_state:
    st.session_state.current_file_sheets = None
if "current_supplier" not in st.session_state:
    st.session_state.current_supplier = None
if "uploader_version" not in st.session_state:
    st.session_state.uploader_version = 0

# ==============================================================================
# SIDEBAR — memory management, standard headers, backup/restore
# ==============================================================================
with st.sidebar:
    st.header("⚙️ Setup & memory")

    with st.expander("💾 Storage status", expanded=False):
        st.caption(f"Data folder: `{store.DATA_DIR}`")
        if store.is_writable():
            st.markdown("✅ Writable — mappings/sheet setups should persist across refreshes/logouts.")
        else:
            st.markdown("🔴 **Not writable** in this environment — nothing will be remembered between runs.")
        st.caption(f"`mappings.json`: {len(st.session_state.mappings)} entries")
        st.caption(f"`sheet_profiles.json`: {len(st.session_state.sheet_profiles)} entries")

    with st.expander(f"🗂️ Remembered sheet setups ({len(st.session_state.sheet_profiles)})", expanded=False):
        for key, prof in sorted(st.session_state.sheet_profiles.items()):
            c1, c2 = st.columns([5, 1])
            status = "included" if prof.get("include") else "skipped"
            detail = ""
            if prof.get("include"):
                detail = f", header row {prof.get('header_row_idx0', 0) + 1}, anchor `{prof.get('anchor_column')}` ({prof.get('anchor_type')})"
            c1.markdown(f"`{prof.get('display_supplier', '?')} → {prof.get('display_sheet', '?')}` — **{status}**{detail}")
            if c2.button("✕", key=f"delprof_{key}", help="Forget this sheet setup"):
                del st.session_state.sheet_profiles[key]
                store.save_sheet_profiles(st.session_state.sheet_profiles)
                st.rerun()
        if not st.session_state.sheet_profiles:
            st.caption("Nothing remembered yet.")

    with st.expander(f"🔤 Remembered column mappings ({len(st.session_state.mappings)})", expanded=False):
        if st.session_state.mappings:
            for norm_src in sorted(st.session_state.mappings.keys()):
                target = st.session_state.mappings[norm_src]
                c1, c2 = st.columns([5, 1])
                c1.markdown(f"`{norm_src}` → **{target or '_(ignored)_'}**")
                if c2.button("✕", key=f"delmap_{norm_src}", help="Forget this mapping"):
                    del st.session_state.mappings[norm_src]
                    store.save_mappings(st.session_state.mappings)
                    st.rerun()
        else:
            st.caption("Nothing remembered yet.")
        if st.button("Clear ALL remembered mappings & sheet setups"):
            st.session_state.mappings = {}
            st.session_state.sheet_profiles = {}
            store.save_mappings({})
            store.save_sheet_profiles({})
            st.rerun()

    st.divider()
    st.header("Standard columns")
    st.caption("Your target (Lorenz master) schema. One column name per line.")
    std_text = st.text_area(
        "Standard columns", value="\n".join(st.session_state.std_headers), height=200, label_visibility="collapsed"
    )
    if st.button("Save standard columns"):
        new_list = [line.strip() for line in std_text.split("\n") if line.strip()]
        if new_list:
            st.session_state.std_headers = new_list
            store.save_standard_headers(new_list)
            st.success("Saved.")
            st.rerun()
        else:
            st.error("Enter at least one column name.")

    st.divider()
    st.header("💾 Backup / restore")
    st.caption("Bundles your mappings, sheet setups, and standard columns into one file — keep it safe.")
    backup_payload = store.build_backup(st.session_state.mappings, st.session_state.sheet_profiles, st.session_state.std_headers)
    st.download_button(
        "⬇️ Download backup",
        backup_payload.encode("utf-8"),
        file_name=f"lorenz_backup_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.json",
        mime="application/json",
    )
    restore_file = st.file_uploader("Restore from a backup file", type=["json"], key="restore_uploader")
    if restore_file is not None:
        try:
            backup_data = json.load(restore_file)
            st.warning(
                f"This backup has {len(backup_data.get('mappings', {}))} mapping(s), "
                f"{len(backup_data.get('sheet_profiles', {}))} sheet setup(s). Restoring overwrites current data."
            )
            if st.button("Confirm restore"):
                st.session_state.mappings = backup_data.get("mappings", {})
                st.session_state.sheet_profiles = backup_data.get("sheet_profiles", {})
                st.session_state.std_headers = backup_data.get("standard_headers", MASTER_COLUMNS)
                store.save_mappings(st.session_state.mappings)
                store.save_sheet_profiles(st.session_state.sheet_profiles)
                store.save_standard_headers(st.session_state.std_headers)
                st.success("Restored.")
                st.rerun()
        except (json.JSONDecodeError, AttributeError):
            st.error("That doesn't look like a valid backup file.")

st.title("📦 Lorenz — Supplier File Merge & Dashboard")

tab_merge, tab_dashboard = st.tabs(["📥 Merge Files", "📊 Dashboard"])


def _get_sheet_entries(file_sheets: dict) -> list:
    """[(filename, effective_sheet_name, raw_grid, forced_header_idx0, data_end_row, is_subtable)]"""
    entries = []
    for fname, sheets in file_sheets.items():
        for sheet_name, raw_grid in sheets.items():
            subtables = detect_subtables(raw_grid)
            if subtables:
                for sub in subtables:
                    entries.append((fname, sub["label"], raw_grid, sub["header_row_idx0"], sub["data_end_row"], True))
            else:
                entries.append((fname, sheet_name, raw_grid, None, None, False))
    return entries


# ==============================================================================
# TAB 1 — MERGE FILES
# ==============================================================================
with tab_merge:
    st.subheader("1. Choose a supplier and upload file(s)")

    col_a, col_b, col_c = st.columns([1, 3, 1])
    with col_a:
        supplier = st.selectbox("Supplier", SUPPLIERS)
    with col_b:
        uploader_key = f"uploader_{st.session_state.uploader_version}"
        uploaded_files = st.file_uploader(
            f"Upload {supplier}'s file(s) — you can select more than one",
            type=["csv", "xlsx", "xlsm", "xls", "pdf", "msg"],
            accept_multiple_files=True,
            key=uploader_key,
        )
    with col_c:
        st.write("")
        st.write("")
        if st.button("🗑️ Clear uploaded files", use_container_width=True):
            st.session_state.current_file_sheets = None
            st.session_state.uploader_version += 1
            st.rerun()

    if uploaded_files:
        file_sheets = {}
        for f in uploaded_files:
            try:
                sheets, note = read_raw_sheets(f)
                file_sheets[f.name] = sheets
                if note:
                    st.info(f"{f.name}: {note}")
            except UnsupportedFileError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Couldn't read '{f.name}': {e}")

        st.session_state.current_file_sheets = file_sheets
        st.session_state.current_supplier = supplier

        if file_sheets:
            entries = _get_sheet_entries(file_sheets)
            effective_names, seen = [], set()
            for _, ename, *_rest in entries:
                if ename not in seen:
                    seen.add(ename)
                    effective_names.append(ename)

            unresolved = [en for en in effective_names if store.sheet_profile_key(supplier, en) not in st.session_state.sheet_profiles]

            if unresolved:
                st.subheader("2. Set up new sheet type(s)")
                st.caption(
                    "These sheets haven't been configured for this supplier yet. For each: whether it "
                    "holds row-level data you want, its header row, and an anchor column (a column "
                    "that's always filled on a real data row — used to automatically drop subtotal, "
                    "pivot-table, and blank rows). This is remembered from now on."
                )
                widget_state = {}
                for ename in unresolved:
                    rep = next(e for e in entries if e[1] == ename)
                    _, _, raw, forced_hidx, dend, is_sub = rep
                    with st.expander(f"📄 Sheet: {ename}", expanded=True):
                        include = st.checkbox(
                            "Include this sheet's rows in the merge",
                            value=not any(k in store.normalize(ename) for k in ["summary", "pivot", "index", "readme"]),
                            key=f"inc_{ename}",
                        )
                        if include:
                            if is_sub:
                                header_row_idx0 = forced_hidx
                                st.caption(
                                    f"Detected as a labeled section within its sheet — header row "
                                    f"{header_row_idx0 + 1}, auto-bounded so it won't swallow neighboring "
                                    f"sections. Re-detected fresh each upload."
                                )
                            else:
                                default_h = detect_header_row(raw)
                                header_row_1 = st.number_input(
                                    "Header row (1-indexed)",
                                    min_value=1,
                                    max_value=max(1, len(raw)),
                                    value=min(default_h + 1, max(1, len(raw))),
                                    key=f"hr_{ename}",
                                )
                                header_row_idx0 = header_row_1 - 1
                            headered_preview = apply_header_row(raw, header_row_idx0, dend if is_sub else None)
                            if headered_preview.shape[1]:
                                guess_col, guess_type = guess_anchor(headered_preview)
                                cols = list(headered_preview.columns)
                                anchor_col = st.selectbox(
                                    "Anchor column (must be filled on every real data row)",
                                    cols,
                                    index=cols.index(guess_col) if guess_col in cols else 0,
                                    key=f"anchor_{ename}",
                                )
                                anchor_type = st.selectbox(
                                    "Anchor column type",
                                    ANCHOR_TYPES,
                                    index=ANCHOR_TYPES.index(guess_type) if guess_type in ANCHOR_TYPES else 0,
                                    key=f"anchortype_{ename}",
                                )
                                st.caption(f"Detected columns: {', '.join(cols)}")
                            else:
                                st.warning("No columns detected on that header row.")
                        widget_state[ename] = (is_sub, forced_hidx, dend)

                if st.button("💾 Save sheet setup", type="primary"):
                    for ename, (is_sub, forced_hidx, dend) in widget_state.items():
                        key = store.sheet_profile_key(supplier, ename)
                        include = st.session_state.get(f"inc_{ename}", False)
                        if not include:
                            st.session_state.sheet_profiles[key] = {
                                "display_supplier": supplier, "display_sheet": ename,
                                "include": False, "is_subtable": is_sub,
                            }
                        else:
                            header_row_idx0 = forced_hidx if is_sub else (st.session_state.get(f"hr_{ename}", 1) - 1)
                            st.session_state.sheet_profiles[key] = {
                                "display_supplier": supplier, "display_sheet": ename,
                                "include": True, "is_subtable": is_sub,
                                "header_row_idx0": header_row_idx0,
                                "anchor_column": st.session_state.get(f"anchor_{ename}"),
                                "anchor_type": st.session_state.get(f"anchortype_{ename}", "text"),
                            }
                    store.save_sheet_profiles(st.session_state.sheet_profiles)
                    st.rerun()

            else:
                extracted = []
                for fname, ename, raw, forced_hidx, dend, is_sub in entries:
                    key = store.sheet_profile_key(supplier, ename)
                    prof = st.session_state.sheet_profiles.get(key)
                    if not prof or not prof.get("include"):
                        continue
                    if is_sub and prof.get("is_subtable"):
                        header_row_idx0, data_end = forced_hidx, dend
                    else:
                        header_row_idx0, data_end = prof.get("header_row_idx0", 0), None
                    headered = apply_header_row(raw, header_row_idx0, data_end)
                    if headered.shape[1] == 0:
                        continue
                    cols = list(headered.columns)
                    anchor_col = prof.get("anchor_column") or cols[0]
                    if anchor_col not in cols:
                        anchor_col = cols[0]
                    anchor_type = prof.get("anchor_type", "text")
                    cleaned = extract_valid_rows(headered, anchor_col, anchor_type)
                    extracted.append((fname, ename, cleaned))

                total_rows = sum(len(c) for _, _, c in extracted)
                st.subheader("2. Review column mapping")
                st.caption(
                    f"{len(uploaded_files)} file(s), {len(extracted)} included sheet(s), "
                    f"{total_rows} data row(s) detected after filtering out subtotals/blanks."
                )
                with st.expander("Row counts per sheet"):
                    for fname, ename, cleaned in extracted:
                        st.write(f"- **{fname}** / *{ename}*: {len(cleaned)} rows")

                sheets_in_order, seen2 = [], set()
                headers_by_sheet = {}
                for fname, ename, cleaned in extracted:
                    if ename not in seen2:
                        seen2.add(ename)
                        sheets_in_order.append(ename)
                        headers_by_sheet[ename] = list(cleaned.columns)

                std_options = [IGNORE_LABEL] + st.session_state.std_headers
                mapping_choices = {}
                total_header_count = 0
                auto_count = 0

                for ename in sheets_in_order:
                    headers = headers_by_sheet[ename]
                    st.markdown(f"#### 📄 {ename}")
                    st.caption(f"{len(headers)} column(s) found in this sheet")
                    hc1, hc2, hc3 = st.columns([3, 1, 4])
                    hc1.markdown("**Column in this sheet**")
                    hc3.markdown("**Maps to your standard column**")
                    for src in headers:
                        total_header_count += 1
                        n = store.normalize(src)
                        saved = st.session_state.mappings.get(n)
                        if saved is not None:
                            default_val = saved if saved else IGNORE_LABEL
                            auto_count += 1
                        else:
                            exact = next((s for s in st.session_state.std_headers if store.normalize(s) == n), None)
                            default_val = exact if exact else IGNORE_LABEL
                            if exact:
                                auto_count += 1
                        idx = std_options.index(default_val) if default_val in std_options else 0
                        c1, c2, c3 = st.columns([3, 1, 4])
                        dot = "🟢" if idx != 0 else "🟡"
                        c1.markdown(f"{dot} `{src}`")
                        c2.markdown("→")
                        choice = c3.selectbox(
                            f"map_{ename}_{src}", std_options, index=idx,
                            key=f"map_{ename}_{src}", label_visibility="collapsed",
                        )
                        mapping_choices[(ename, src)] = choice
                    st.divider()

                if total_header_count:
                    st.caption(
                        f"🟢 auto-filled from memory or exact name match · 🟡 needs your input "
                        f"({auto_count}/{total_header_count} pre-filled)"
                    )

                st.subheader("3. Optional: set Invoice Date / Pay Date for this whole upload")
                st.caption("Applied to every sheet added below. Useful when the raw file doesn't include these columns itself.")
                d1, d2 = st.columns(2)
                with d1:
                    use_invoice = st.checkbox("Apply one Invoice Date to every row", key="use_inv")
                    invoice_override = st.date_input("Invoice Date", value=dt.date.today(), key="inv_date", disabled=not use_invoice)
                with d2:
                    use_pay = st.checkbox("Apply one Pay Date to every row", key="use_pay")
                    pay_override = st.date_input("Pay Date", value=dt.date.today(), key="pay_date", disabled=not use_pay)

                st.subheader("4. Save mapping & add to merged data")
                col_x, col_y = st.columns(2)
                with col_x:
                    generate_clicked = st.button("💾 Save mapping & add to merged data", type="primary", use_container_width=True)
                with col_y:
                    if st.button("↩️ Reset sheet setup for this supplier (start over)", use_container_width=True):
                        prefix = store.normalize(supplier) + "::"
                        for k in [k for k in st.session_state.sheet_profiles if k.startswith(prefix)]:
                            del st.session_state.sheet_profiles[k]
                        store.save_sheet_profiles(st.session_state.sheet_profiles)
                        st.rerun()

                if generate_clicked:
                    for (ename, src), choice in mapping_choices.items():
                        n = store.normalize(src)
                        st.session_state.mappings[n] = "" if choice == IGNORE_LABEL else choice
                    store.save_mappings(st.session_state.mappings)

                    total_added = 0
                    for fname, ename, cleaned in extracted:
                        flat_mapping = {
                            src: (mapping_choices.get((ename, src)) if mapping_choices.get((ename, src)) != IGNORE_LABEL else "")
                            for src in headers_by_sheet[ename]
                        }
                        transformed = apply_mapping(
                            cleaned, flat_mapping, st.session_state.std_headers, supplier,
                            invoice_date_override=invoice_override if use_invoice else None,
                            pay_date_override=pay_override if use_pay else None,
                        )
                        transformed = format_output_df(transformed, st.session_state.std_headers)
                        st.session_state.merged_df = pd.concat(
                            [st.session_state.merged_df, transformed], ignore_index=True
                        )
                        st.session_state.upload_log.append(
                            {"Supplier": supplier, "File": f"{fname} — {ename}", "Rows added": len(transformed)}
                        )
                        total_added += len(transformed)
                    st.success(f"Added {total_added} row(s) total from {len(extracted)} sheet(s).")

    st.divider()
    st.subheader("Merge log")
    if st.session_state.upload_log:
        st.dataframe(pd.DataFrame(st.session_state.upload_log), use_container_width=True, hide_index=True)
        total_rows = len(st.session_state.merged_df)
        st.write(f"**Total merged rows so far: {total_rows}**")

        dl1, dl2, reset_col = st.columns(3)
        with dl1:
            st.download_button(
                "⬇️ Download merged file (.xlsx)",
                data=to_excel_bytes(st.session_state.merged_df),
                file_name="Lorenz_Merged.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        with dl2:
            st.download_button(
                "⬇️ Download merged file (.csv)",
                data=to_csv_bytes(st.session_state.merged_df),
                file_name="Lorenz_Merged.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with reset_col:
            if st.button("🗑️ Clear merged / downloaded data & start over", use_container_width=True):
                st.session_state.merged_df = pd.DataFrame(columns=st.session_state.std_headers)
                st.session_state.upload_log = []
                st.rerun()
    else:
        st.info("No files merged yet. Upload supplier file(s) above and complete the mapping step.")

# ==============================================================================
# TAB 2 — DASHBOARD
# ==============================================================================
with tab_dashboard:
    if st.session_state.current_file_sheets:
        st.subheader(f"Current upload ({st.session_state.current_supplier})")
        for fname, sheets in st.session_state.current_file_sheets.items():
            for sheet_name, raw_grid in sheets.items():
                st.caption(f"{fname} — sheet: {sheet_name} — {raw_grid.shape[0]} rows, {raw_grid.shape[1]} columns (raw, as uploaded).")
                show_excel_grid(raw_grid, key=f"raw_grid_{fname}_{sheet_name}")
        st.divider()

    df = st.session_state.merged_df
    st.subheader("Merged data")
    if df.empty:
        st.info("Merge at least one supplier file in the **Merge Files** tab to see it here.")
    else:
        st.caption(f"{df.shape[0]} rows, {df.shape[1]} columns.")
        show_excel_grid(df, key="merged_grid")
