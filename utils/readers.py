"""
Reads a raw supplier file — csv, xlsx/xls/xlsm, pdf, or Outlook .msg — into
one or more "raw sheets": headerless grids (integer column labels) so the
app can let the user pick the correct header row and filter out title/
subtotal/pivot rows before mapping, per sheet.

Nothing here is ever cached (no st.cache_*) or written to a persistent
location. PDF/MSG parsing needs a real file on disk for the underlying
libraries, so a temp file is created in the OS temp dir and deleted again
in a `finally` block before this function returns.
"""
import io
import os
import re
import tempfile

import pandas as pd


class UnsupportedFileError(ValueError):
    pass


def read_raw_sheets(uploaded_file) -> tuple[dict, str | None]:
    """
    Returns ({sheet_name: raw_grid_df}, note).
    Every raw_grid_df has NO assumed header — row 0 is just the first row
    of the file, columns are 0..n-1 — so the caller picks the header row.
    `note` is an optional human-readable string (e.g. which PDF page or
    email attachment the data came from), or None.
    """
    name = uploaded_file.name.lower()
    uploaded_file.seek(0)
    raw_bytes = uploaded_file.read()

    if name.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(raw_bytes), header=None, dtype=str, keep_default_na=True)
        return {"Data": df.reset_index(drop=True)}, None

    if name.endswith((".xlsx", ".xlsm", ".xls")):
        sheets = pd.read_excel(io.BytesIO(raw_bytes), sheet_name=None, header=None, dtype=str)
        return {sn: df.reset_index(drop=True) for sn, df in sheets.items()}, None

    if name.endswith(".pdf"):
        df, note = _read_pdf(raw_bytes)
        return {"PDF Table": _headered_to_raw(df)}, note

    if name.endswith(".msg"):
        df, note = _read_msg(raw_bytes)
        return {"Email Attachment": _headered_to_raw(df)}, note

    raise UnsupportedFileError(
        f"Unsupported file type: {uploaded_file.name}. Supported: csv, xlsx, xls, xlsm, pdf, msg."
    )


def guess_header_row(raw_df: pd.DataFrame, max_scan: int = 15) -> int:
    """Best-guess row index (0-based) most likely to be the real header row."""
    best_row, best_score = 0, -1
    for r in range(min(max_scan, len(raw_df))):
        row = raw_df.iloc[r]
        score = row.notna().sum()
        if score > best_score:
            best_score, best_row = score, r
    return best_row


def apply_header_row(raw_df: pd.DataFrame, header_row_idx: int) -> pd.DataFrame:
    """Turn a raw grid into a proper DataFrame using row `header_row_idx` as the header."""
    header = raw_df.iloc[header_row_idx].fillna("").astype(str).str.strip().tolist()
    header = [h if h else f"Column_{i + 1}" for i, h in enumerate(header)]
    body = raw_df.iloc[header_row_idx + 1:].reset_index(drop=True)
    body.columns = header
    return body


def filter_required_columns(df: pd.DataFrame, required_columns: list) -> pd.DataFrame:
    """Keep only rows where every column in `required_columns` is non-blank (drops subtotal/pivot/blank rows)."""
    if not required_columns:
        return df
    mask = pd.Series(True, index=df.index)
    for col in required_columns:
        if col in df.columns:
            mask &= df[col].notna() & (df[col].astype(str).str.strip() != "")
    return df[mask].reset_index(drop=True)


def _headered_to_raw(df: pd.DataFrame) -> pd.DataFrame:
    """Wrap an already-headered DataFrame (from pdf/msg extraction) back into raw-grid form."""
    header_row = pd.DataFrame([list(df.columns)], columns=range(df.shape[1]))
    body = df.copy()
    body.columns = range(df.shape[1])
    return pd.concat([header_row, body], ignore_index=True)


def _read_pdf(raw_bytes: bytes) -> tuple[pd.DataFrame, str]:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
        best_table = None
        best_page = None
        for page_num, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables():
                if not table or len(table) < 2:
                    continue
                if best_table is None or len(table[0]) > len(best_table[0]):
                    best_table = table
                    best_page = page_num

    if not best_table:
        raise UnsupportedFileError(
            "Couldn't find a table in this PDF. Try exporting/saving it as CSV or Excel instead."
        )

    header, *rows = best_table
    header = [h if h else f"Column_{i}" for i, h in enumerate(header, start=1)]
    df = pd.DataFrame(rows, columns=header).astype(str)
    return df, f"Extracted table from PDF page {best_page}."


def _read_msg(raw_bytes: bytes) -> tuple[pd.DataFrame, str]:
    import extract_msg

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".msg", delete=False) as tmp:
            tmp.write(raw_bytes)
            tmp_path = tmp.name

        msg = extract_msg.Message(tmp_path)
        supported_ext = (".csv", ".xlsx", ".xlsm", ".xls", ".pdf")
        for attachment in msg.attachments:
            att_name = (getattr(attachment, "longFilename", None) or getattr(attachment, "shortFilename", "") or "").lower()
            if att_name.endswith(supported_ext):
                att_bytes = attachment.data
                if att_name.endswith(".csv"):
                    df = pd.read_csv(io.BytesIO(att_bytes), dtype=str, keep_default_na=True)
                elif att_name.endswith(".pdf"):
                    df, _ = _read_pdf(att_bytes)
                else:
                    df = pd.read_excel(io.BytesIO(att_bytes), dtype=str)
                return df, f"Extracted attachment '{att_name}' from the Outlook message."

        raise UnsupportedFileError(
            "No csv/xlsx/pdf attachment found in this .msg file. "
            "Please forward/save the attachment itself instead."
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
