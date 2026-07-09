"""
Transforms a raw supplier DataFrame into the fixed master-schema shape.
Export is purely in-memory (io.BytesIO) — the merged/downloaded file is
never written to disk or cached.
"""
import datetime as dt
import io

import pandas as pd


def apply_mapping(
    df: pd.DataFrame,
    mapping: dict,
    master_columns: list,
    supplier_name: str,
    invoice_date_override: "dt.date | None" = None,
    pay_date_override: "dt.date | None" = None,
) -> pd.DataFrame:
    """
    Reshape `df` into the fixed master_columns order using `mapping`
    (master_column -> source_column or None).

    - Supplier_name is auto-filled from `supplier_name` if left unmapped/blank.
    - If PartNumberSubmitted is mapped but PartNumberActual isn't, the
      PartNumberSubmitted values are mirrored into PartNumberActual too.
    - invoice_date_override / pay_date_override, if given, are applied to
      every row in this file (overriding whatever the mapping produced),
      and Pay_Month/Pay_Year are derived from pay_date_override.
    """
    out = pd.DataFrame(index=df.index)

    for col in master_columns:
        src = mapping.get(col)
        if src and src in df.columns:
            out[col] = df[src]
        else:
            out[col] = None

    if "Supplier_name" in master_columns:
        empty = out["Supplier_name"].isna() | (out["Supplier_name"].astype(str).str.strip() == "")
        out.loc[empty, "Supplier_name"] = supplier_name

    if "PartNumberActual" in master_columns and "PartNumberSubmitted" in master_columns:
        if not mapping.get("PartNumberActual"):
            out["PartNumberActual"] = out["PartNumberSubmitted"]

    if invoice_date_override and "InvoiceDate" in master_columns:
        out["InvoiceDate"] = invoice_date_override.isoformat()

    if pay_date_override and "Pay_Date" in master_columns:
        out["Pay_Date"] = pay_date_override.isoformat()
        if "Pay_Month" in master_columns:
            out["Pay_Month"] = pay_date_override.month
        if "Pay_Year" in master_columns:
            out["Pay_Year"] = pay_date_override.year

    return out[master_columns]


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Serialize a DataFrame to an in-memory .xlsx file, returning raw bytes (nothing touches disk)."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Merged")
    return buffer.getvalue()
