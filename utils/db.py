"""
Persistent, queryable storage for supplier column mappings.

Uses a single SQLite file (data/mappings.db) instead of one JSON file per
supplier so that:
  - mappings survive session restarts / logouts (as long as the host's disk
    isn't wiped by a redeploy — see README for hosting notes),
  - the Mappings tab can list / delete individual entries easily,
  - one supplier's confirmed mapping can help auto-suggest another
    supplier's mapping when their raw files share column names.

No raw uploaded data or merged/downloaded files ever touch this database —
it only ever stores {supplier, master_column, source_column} triples.
"""
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "mappings.db"
DB_PATH.parent.mkdir(exist_ok=True)


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mappings (
            supplier TEXT NOT NULL,
            master_column TEXT NOT NULL,
            source_column TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (supplier, master_column)
        )
        """
    )
    return conn


def _normalize(col: str) -> str:
    """Loose key for cross-file / cross-supplier header matching."""
    return re.sub(r"[^a-z0-9]", "", str(col).lower())


def save_mapping(supplier: str, mapping: dict) -> None:
    """Upsert a supplier's mapping. Entries with no source column are skipped/removed."""
    now = datetime.now(timezone.utc).isoformat()
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM mappings WHERE supplier = ?", (supplier,))
        rows = [
            (supplier, master_col, source_col, now)
            for master_col, source_col in mapping.items()
            if source_col
        ]
        conn.executemany(
            "INSERT INTO mappings (supplier, master_column, source_column, updated_at) VALUES (?, ?, ?, ?)",
            rows,
        )


def load_mapping(supplier: str) -> dict:
    """Return {master_column: source_column} for a supplier (empty dict if none saved)."""
    with closing(_connect()) as conn:
        cur = conn.execute(
            "SELECT master_column, source_column FROM mappings WHERE supplier = ?", (supplier,)
        )
        return dict(cur.fetchall())


def delete_mapping(supplier: str, master_columns: list = None) -> int:
    """
    Delete a supplier's mapping. If master_columns is given, only those rows
    are removed (partial delete); otherwise the whole supplier mapping is
    cleared. Returns number of rows deleted.
    """
    with closing(_connect()) as conn, conn:
        if master_columns:
            placeholders = ",".join("?" for _ in master_columns)
            cur = conn.execute(
                f"DELETE FROM mappings WHERE supplier = ? AND master_column IN ({placeholders})",
                (supplier, *master_columns),
            )
        else:
            cur = conn.execute("DELETE FROM mappings WHERE supplier = ?", (supplier,))
        return cur.rowcount


def list_summary() -> list:
    """One row per supplier that has a saved mapping: supplier, #columns mapped, last updated."""
    with closing(_connect()) as conn:
        cur = conn.execute(
            """
            SELECT supplier, COUNT(*) AS mapped_columns, MAX(updated_at) AS updated_at
            FROM mappings GROUP BY supplier ORDER BY supplier
            """
        )
        return [dict(zip(["Supplier", "Columns mapped", "Last updated"], row)) for row in cur.fetchall()]


def get_all_mappings() -> dict:
    """{supplier: {master_column: source_column}} for every supplier with a saved mapping."""
    with closing(_connect()) as conn:
        cur = conn.execute("SELECT supplier, master_column, source_column FROM mappings")
        out = {}
        for supplier, master_col, source_col in cur.fetchall():
            out.setdefault(supplier, {})[master_col] = source_col
        return out


def cross_supplier_lookup(exclude_supplier: str = None) -> dict:
    """
    Build normalized_source_column -> master_column from every OTHER
    supplier's saved mapping, so a header seen once (e.g. "Invoice Date")
    is recognized automatically for any supplier's file that reuses it.
    Most-recently-saved mapping wins on conflicts.
    """
    with closing(_connect()) as conn:
        query = "SELECT master_column, source_column, updated_at FROM mappings"
        params = ()
        if exclude_supplier:
            query += " WHERE supplier != ?"
            params = (exclude_supplier,)
        query += " ORDER BY updated_at ASC"
        cur = conn.execute(query, params)
        lookup = {}
        for master_col, source_col, _updated in cur.fetchall():
            lookup[_normalize(source_col)] = master_col
        return lookup
