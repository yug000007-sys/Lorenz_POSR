"""
A spreadsheet-style grid (via streamlit-aggrid) for displaying data —
sortable/filterable/resizable columns, cell borders, row numbers — much
closer to an Excel look than the default st.dataframe table.
"""
from st_aggrid import AgGrid, ColumnsAutoSizeMode, GridOptionsBuilder


def excel_col_letter(n: int) -> str:
    """0-indexed column position -> Excel-style letter (0->A, 25->Z, 26->AA, ...)."""
    n += 1
    letters = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def show_excel_grid(df, key: str, height: int = 420, excel_style: bool = False):
    """
    Render `df` as an Excel-style grid. Read-only (view only, no edits saved).

    excel_style=True relabels columns A, B, C... and adds a pinned '#' row
    number column matching the row's position in the original file — use
    this for raw/unmapped sheets so they look exactly like the source
    spreadsheet. Leave False for already-headered data (real column names).
    """
    import streamlit as st

    if df is None or df.empty:
        st.caption("(no rows to display)")
        return

    display_df = df
    if excel_style:
        display_df = df.copy()
        display_df.columns = [excel_col_letter(i) for i in range(display_df.shape[1])]
        display_df.insert(0, "#", range(1, len(display_df) + 1))

    gb = GridOptionsBuilder.from_dataframe(display_df)
    gb.configure_default_column(resizable=True, sortable=True, filter=True, editable=False)
    if excel_style:
        gb.configure_column("#", pinned="left", width=56, sortable=False, filter=False)
    gb.configure_pagination(enabled=True, paginationAutoPageSize=False, paginationPageSize=50)
    gb.configure_grid_options(domLayout="normal", rowSelection="none", suppressRowClickSelection=True)
    grid_options = gb.build()

    AgGrid(
        display_df,
        gridOptions=grid_options,
        height=height,
        theme="alpine",
        columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS,
        allow_unsafe_jscode=False,
        update_on=[],
        key=key,
    )
