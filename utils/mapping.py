"""
Column-mapping suggestion logic. Persistence itself lives in utils/db.py;
this module builds the best-guess mapping for a newly uploaded file.
"""
from rapidfuzz import fuzz, process

from utils.db import _normalize, cross_supplier_lookup


def suggest_mapping(
    master_columns: list,
    source_columns: list,
    saved_mapping: dict = None,
    supplier: str = None,
    threshold: int = 60,
) -> dict:
    """
    Build a best-guess mapping of master_column -> source_column.

    Priority:
      1. This supplier's own previously saved mapping (if that source
         column still exists in the uploaded file).
      2. Any OTHER supplier's saved mapping, matched by normalized column
         name (e.g. two suppliers both have a raw "Invoice Date" column) —
         lets mappings learned on one supplier auto-apply to another.
      3. Fuzzy name matching against the master column names.
      4. None (left for manual review).
    """
    saved_mapping = saved_mapping or {}
    source_columns = list(source_columns)
    source_by_norm = {_normalize(c): c for c in source_columns}
    other_supplier_lookup = cross_supplier_lookup(exclude_supplier=supplier)

    # normalized_source -> master_column, from every other supplier
    master_by_norm_source = {}
    for norm_src, master_col in other_supplier_lookup.items():
        master_by_norm_source.setdefault(master_col, norm_src)

    result = {}
    for col in master_columns:
        # 1. This supplier's saved mapping
        saved_src = saved_mapping.get(col)
        if saved_src and saved_src in source_columns:
            result[col] = saved_src
            continue

        # 2. Cross-supplier learned mapping
        norm_src = master_by_norm_source.get(col)
        if norm_src and norm_src in source_by_norm:
            result[col] = source_by_norm[norm_src]
            continue

        # 3. Fuzzy match
        if source_columns:
            match = process.extractOne(col, source_columns, scorer=fuzz.token_sort_ratio)
            if match and match[1] >= threshold:
                result[col] = match[0]
                continue

        # 4. No guess
        result[col] = None

    return result
