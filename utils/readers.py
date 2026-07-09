"""
Reads a raw supplier file — csv, xlsx/xls/xlsm, pdf, or Outlook .msg — into
a pandas DataFrame.

Nothing here is ever cached (no st.cache_*) or written to a persistent
location. PDF/MSG parsing needs a real file on disk for the underlying
libraries, so a temp file is created in the OS temp dir and deleted again
in a `finally` block before this function returns.
"""
import io
import os
import tempfile

import pandas as pd


class UnsupportedFileError(ValueError):
    pass


def read_supplier_file(uploaded_file) -> tuple[pd.DataFrame, str | None]:
    """
    Returns (DataFrame, note). `note` is an optional human-readable string
    explaining how the data was extracted (e.g. which PDF table, or which
    email attachment), or None if nothing noteworthy happened.
    """
    name = uploaded_file.name.lower()
    uploaded_file.seek(0)
    raw_bytes = uploaded_file.read()

    if name.endswith(".csv"):
        return pd.read_csv(io.BytesIO(raw_bytes), dtype=str, keep_default_na=True), None

    if name.endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(io.BytesIO(raw_bytes), dtype=str), None

    if name.endswith(".pdf"):
        return _read_pdf(raw_bytes)

    if name.endswith(".msg"):
        return _read_msg(raw_bytes)

    raise UnsupportedFileError(
        f"Unsupported file type: {uploaded_file.name}. Supported: csv, xlsx, xls, xlsm, pdf, msg."
    )


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
