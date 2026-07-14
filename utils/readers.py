"""
Reads a raw supplier file — csv, xlsx/xls/xlsm, pdf, or Outlook .msg — into
one or more "raw sheets" (headerless grids), then helps turn each into
clean data rows:
  - detect_header_row / apply_header_row: find and apply the real header
    row (title rows above it are ignored, blank-named columns dropped).
  - guess_anchor / extract_valid_rows: pick a column that's always filled
    on a genuine data row (preferring a date column) and use it to drop
    subtotal, pivot-table, and blank-separator rows automatically.
  - detect_subtables: recognizes multiple labeled mini-tables stacked in
    one sheet (a one-cell "marker" row immediately followed by a header
    row), so each is treated as its own sheet.

Nothing here is ever cached (no st.cache_*) or written to a persistent
location. PDF/MSG parsing needs a real file on disk for the underlying
libraries, so a temp file is created in the OS temp dir and deleted again
in a `finally` block before this function returns.
"""
import io
import os
import re
import tempfile
from datetime import datetime

import pandas as pd


class UnsupportedFileError(ValueError):
    pass


DATE_PATTERN_RE = re.compile(r"^\d{1,4}[/-]\d{1,2}[/-]\d{1,4}([ T]\d{1,2}:\d{2}(:\d{2})?)?$")


def is_blank(v) -> bool:
    if v is None:
        return True
    try:
        if pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    return str(v).strip() == ""


def looks_like_date(v) -> bool:
    if is_blank(v):
        return False
    if isinstance(v, datetime):
        return True
    s = str(v).strip()
    if not DATE_PATTERN_RE.match(s):
        return False
    try:
        pd.to_datetime(s)
        return True
    except (ValueError, TypeError):
        return False


def _looks_numeric(v) -> bool:
    try:
        float(str(v).replace(",", ""))
        return True
    except (ValueError, TypeError):
        return False


# ----------------------------------------------------------------------------
# Reading raw sheets
# ----------------------------------------------------------------------------
def read_raw_sheets(uploaded_file) -> tuple[dict, "str | None"]:
    """
    Returns ({sheet_name: raw_grid_df}, note). Every raw_grid_df has NO
    assumed header (integer column labels) so the caller picks the header
    row. `note` is an optional human-readable string, or None.
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


def detect_header_row(raw_df: pd.DataFrame, max_scan: int = 15) -> int:
    """0-indexed best-guess header row: first row (within max_scan) with >= 3 filled cells."""
    for i in range(min(max_scan, len(raw_df))):
        if sum(1 for v in raw_df.iloc[i] if not is_blank(v)) >= 3:
            return i
    return 0


def apply_header_row(raw_df: pd.DataFrame, header_row_idx: int, data_end_row: int = None) -> pd.DataFrame:
    """
    Turn a raw grid into a proper DataFrame using row `header_row_idx` as
    the header. Blank-named columns are dropped. `data_end_row` (0-indexed,
    exclusive), if given, bounds the body — used for stacked sub-tables
    sharing one sheet.
    """
    header_vals = raw_df.iloc[header_row_idx].tolist()
    keep_idx = [i for i, h in enumerate(header_vals) if not is_blank(h)]
    headers = [str(header_vals[i]).strip() for i in keep_idx]
    # de-duplicate repeated header names
    seen = {}
    unique_headers = []
    for h in headers:
        seen[h] = seen.get(h, 0) + 1
        unique_headers.append(h if seen[h] == 1 else f"{h}_{seen[h]}")

    end = data_end_row if data_end_row is not None else len(raw_df)
    body = raw_df.iloc[header_row_idx + 1: end, keep_idx].reset_index(drop=True)
    body.columns = unique_headers
    return body


# ----------------------------------------------------------------------------
# Anchor-column row filtering (drops subtotal / pivot / blank rows)
# ----------------------------------------------------------------------------
def guess_anchor(headered_df: pd.DataFrame, sample: int = 20) -> tuple:
    """Best-guess (column, type) to identify real data rows: prefer a date column,
    otherwise the column with the most non-empty values."""
    if headered_df.shape[1] == 0:
        return None, "text"
    sample_df = headered_df.head(sample)

    date_scores = {col: sum(1 for v in sample_df[col] if looks_like_date(v)) for col in sample_df.columns}
    if date_scores and max(date_scores.values()) >= max(3, len(sample_df) // 4):
        best = max(date_scores, key=date_scores.get)
        return best, "date"

    best_col, best_type, best_score = list(headered_df.columns)[0], "text", -1
    for col in headered_df.columns:
        vals = sample_df[col]
        non_empty = sum(1 for v in vals if not is_blank(v))
        if non_empty > best_score:
            best_score, best_col = non_empty, col
            numeric_ok = sum(1 for v in vals if not is_blank(v) and _looks_numeric(v))
            best_type = "number" if numeric_ok >= max(1, non_empty * 0.8) else "text"
    return best_col, best_type


def row_is_valid(value, anchor_type: str) -> bool:
    if is_blank(value):
        return False
    if anchor_type == "date":
        return looks_like_date(value)
    if anchor_type == "number":
        return _looks_numeric(value)
    return True  # text: any non-empty value counts


def extract_valid_rows(headered_df: pd.DataFrame, anchor_col: str, anchor_type: str) -> pd.DataFrame:
    """Keep only rows where the anchor column passes row_is_valid — drops subtotal/pivot/blank rows."""
    if not anchor_col or anchor_col not in headered_df.columns:
        return headered_df.reset_index(drop=True)
    mask = headered_df[anchor_col].apply(lambda v: row_is_valid(v, anchor_type))
    return headered_df[mask].reset_index(drop=True)


# ----------------------------------------------------------------------------
# Stacked sub-table detection (e.g. an "OEM" section followed by a "POS"
# section, each with its own header row, inside one physical sheet)
# ----------------------------------------------------------------------------
def detect_subtables(raw_df: pd.DataFrame) -> list:
    """
    Returns [] for an ordinary single-table sheet. Otherwise returns
    [{"label", "header_row_idx0", "data_end_row"}] for each detected
    section. A "marker" row is one with exactly one non-blank cell,
    immediately followed (within a few rows) by a header-like row.
    """
    n = len(raw_df)
    markers = []
    for i in range(n):
        non_blank = [(j, v) for j, v in enumerate(raw_df.iloc[i]) if not is_blank(v)]
        if len(non_blank) == 1:
            label_value = non_blank[0][1]
            if _looks_numeric(label_value) or looks_like_date(label_value):
                continue  # a lone number/date (e.g. a subtotal) is not a section label
            for k in range(i + 1, min(i + 4, n)):
                nxt_non_blank = sum(1 for v in raw_df.iloc[k] if not is_blank(v))
                if nxt_non_blank == 0:
                    continue
                if nxt_non_blank >= 3:
                    markers.append({"label": str(label_value).strip(), "marker_row": i, "header_row0": k})
                break
    if len(markers) < 2:
        return []
    subtables = []
    for idx, m in enumerate(markers):
        end = markers[idx + 1]["marker_row"] if idx + 1 < len(markers) else n
        subtables.append({"label": m["label"], "header_row_idx0": m["header_row0"], "data_end_row": end})
    return subtables


# ----------------------------------------------------------------------------
# PDF / MSG extraction
# ----------------------------------------------------------------------------
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
