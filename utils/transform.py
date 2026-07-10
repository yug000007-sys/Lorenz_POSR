"""
Transforms a cleaned (headered + row-filtered) sheet DataFrame into the
standard-header shape, and formats/export the final merged result.
Export is purely in-memory (io.BytesIO/StringIO) — nothing is written to
disk or cached.
"""
import datetime as dt
import io

import pandas as pd

DATE_COLUMN_KEYWORDS = ["date"]
MONEY_COLUMN_KEYWORDS = [
    "cost", "price", "amt", "amount", "commission", "sales", "bill",
    "resale", "value", "split", "percentage", "rate",
]


def apply_mapping(
    df: pd.DataFrame,
    mapping: dict,
    standard_headers: list,
    supplier_name: str,
    invoice_date_override: "dt.date | None" = None,
    pay_date_override: "dt.date | None" = None,
) -> pd.DataFrame:
    """
    Reshape `df` into the fixed standard_headers order using `mapping`
    (source_column -> standard_column, "" or missing = ignored).

    - Supplier_name is auto-filled from `supplier_name` if left unmapped/blank.
    - If PartNumberSubmitted is mapped but PartNumberActual isn't, the
      PartNumberSubmitted values are mirrored into PartNumberActual too.
    - invoice_date_override / pay_date_override, if given, are applied to
      every row (overriding whatever the mapping produced), and
      Pay_Month/Pay_Year are derived from pay_date_override.
    """
    out = pd.DataFrame(index=df.index, columns=standard_headers)

    part_submitted_source = None
    part_actual_mapped = False
    for src_col, target_col in mapping.items():
        if not target_col or target_col not in standard_headers or src_col not in df.columns:
            continue
        out[target_col] = df[src_col].values
        if target_col == "PartNumberSubmitted":
            part_submitted_source = src_col
        if target_col == "PartNumberActual":
            part_actual_mapped = True

    if "Supplier_name" in standard_headers:
        empty = out["Supplier_name"].isna() | (out["Supplier_name"].astype(str).str.strip() == "")
        out.loc[empty, "Supplier_name"] = supplier_name

    if "PartNumberActual" in standard_headers and part_submitted_source and not part_actual_mapped:
        out["PartNumberActual"] = df[part_submitted_source].values

    if invoice_date_override and "InvoiceDate" in standard_headers:
        out["InvoiceDate"] = invoice_date_override.isoformat()

    if pay_date_override and "Pay_Date" in standard_headers:
        out["Pay_Date"] = pay_date_override.isoformat()
        if "Pay_Month" in standard_headers:
            out["Pay_Month"] = pay_date_override.month
        if "Pay_Year" in standard_headers:
            out["Pay_Year"] = pay_date_override.year

    return out


def _clean_date_value(value):
    if value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == "":
        return value
    try:
        return pd.to_datetime(value).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return value


def _clean_money_value(value):
    if value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == "":
        return value
    try:
        return round(float(str(value).replace(",", "")), 2)
    except (ValueError, TypeError):
        return value


def format_output_df(df: pd.DataFrame, standard_headers: list) -> pd.DataFrame:
    """
    Strips time-of-day from date-like columns (YYYY-MM-DD) and rounds
    money/rate-like columns to 2 decimals, based on the standard column's
    name (e.g. 'InvoiceDate' -> date rule, 'Commissions' -> money rule).
    """
    df = df.copy()
    for col in standard_headers:
        if col not in df.columns:
            continue
        name_lower = col.lower()
        if any(k in name_lower for k in DATE_COLUMN_KEYWORDS):
            df[col] = df[col].apply(_clean_date_value)
        elif any(k in name_lower for k in MONEY_COLUMN_KEYWORDS):
            df[col] = df[col].apply(_clean_money_value)
    return df


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Serialize a DataFrame to an in-memory .xlsx file (nothing touches disk)."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Merged")
    return buffer.getvalue()


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Serialize a DataFrame to in-memory csv bytes (nothing touches disk)."""
    return df.to_csv(index=False).encode("utf-8")
