"""
Handles per-supplier column mapping:
- loading / saving a mapping profile (master_column -> source_column) to disk
- suggesting a mapping automatically by fuzzy-matching column names
"""
import json
from pathlib import Path

from rapidfuzz import fuzz, process

MAPPINGS_DIR = Path(__file__).resolve().parent.parent / "mappings"
MAPPINGS_DIR.mkdir(exist_ok=True)


def _safe_filename(supplier: str) -> str:
    return supplier.strip().replace(" ", "_").replace("/", "-")


def mapping_path(supplier: str) -> Path:
    return MAPPINGS_DIR / f"{_safe_filename(supplier)}.json"


def load_mapping(supplier: str) -> dict:
    """Return the previously saved mapping for a supplier, or {} if none exists."""
    p = mapping_path(supplier)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_mapping(supplier: str, mapping: dict) -> Path:
    """Persist a mapping (master_column -> source_column or None) to disk."""
    p = mapping_path(supplier)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)
    return p


def suggest_mapping(
    master_columns: list,
    source_columns: list,
    saved_mapping: dict = None,
    threshold: int = 60,
) -> dict:
    """
    Build a best-guess mapping of master_column -> source_column.

    Priority:
      1. A previously saved mapping for this supplier (if the source column
         still exists in the uploaded file).
      2. Fuzzy name matching (token_sort_ratio) against the uploaded file's
         columns, only accepted above `threshold`.
      3. None (left for the user to set manually).
    """
    saved_mapping = saved_mapping or {}
    result = {}
    source_columns = list(source_columns)

    for col in master_columns:
        saved_src = saved_mapping.get(col)
        if saved_src and saved_src in source_columns:
            result[col] = saved_src
            continue

        if not source_columns:
            result[col] = None
            continue

        match = process.extractOne(col, source_columns, scorer=fuzz.token_sort_ratio)
        if match and match[1] >= threshold:
            result[col] = match[0]
        else:
            result[col] = None

    return result


def list_saved_suppliers() -> list:
    """Suppliers that already have a saved mapping profile on disk."""
    return sorted(p.stem for p in MAPPINGS_DIR.glob("*.json"))
