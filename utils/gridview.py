"""
A spreadsheet-style grid (via streamlit-aggrid) for displaying data —
sortable/filterable/resizable columns, cell borders, row numbers — much
closer to an Excel look than the default st.dataframe table.
"""
from st_aggrid import AgGrid, ColumnsAutoSizeMode, GridOptionsBuilder


def show_excel_grid(df, key: str, height: int = 420):
    """Render `df` as an Excel-style grid. Read-only (view only, no edits saved)."""
    if df is None or df.empty:
        import streamlit as st
        st.caption("(no rows to display)")
        return

    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(resizable=True, sortable=True, filter=True, editable=False)
    gb.configure_pagination(enabled=True, paginationAutoPageSize=False, paginationPageSize=50)
    gb.configure_grid_options(domLayout="normal", rowSelection="none", suppressRowClickSelection=True)
    grid_options = gb.build()

    AgGrid(
        df,
        gridOptions=grid_options,
        height=height,
        theme="alpine",
        columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS,
        allow_unsafe_jscode=False,
        update_on=[],
        key=key,
    )
