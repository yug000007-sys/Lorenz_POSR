"""
Reading raw supplier files and transforming them into the master schema.
"""
import io

import pandas as pd


def read_supplier_file(uploaded_file) -> pd.DataFrame:
    """Read an uploaded csv/xlsx/xls file into a DataFrame of strings-safe dtypes."""
    name = uploaded_file.name.lower()
    uploaded_file.seek(0)
    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file, dtype=str, keep_default_na=True)
    elif name.endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(uploaded_file, dtype=str)
    else:
        raise ValueError(f"Unsupported file type: {uploaded_file.name}")


def apply_mapping(
    df: pd.DataFrame,
    mapping: dict,
    master_columns: list,
    supplier_name: str,
) -> pd.DataFrame:
    """
    Reshape `df` into the fixed master_columns order using `mapping`
    (master_column -> source_column or None).

    If Supplier_name isn't mapped from the source file (or comes back empty),
    it's filled in automatically from the selected supplier.
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

    return out[master_columns]


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Serialize a DataFrame to an in-memory .xlsx file, returning raw bytes."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Merged")
    buffer.seek(0)
    return buffer.getvalue()
