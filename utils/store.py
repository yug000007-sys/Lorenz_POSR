"""
JSON-based persistent storage for the Lorenz app — mirrors the approach in
the reference "Header Mapper" app: simple, human-readable JSON files that
survive restarts/logouts, are easy to back up, and can be committed to the
repo if you want them to survive a full redeploy.

Three stores:
  - standard_headers.json — the master schema (editable in the sidebar)
  - mappings.json          — {normalized_source_header: master_column}
                              GLOBAL: learned once, reused for every
                              supplier/sheet that has a column with that
                              same (normalized) name.
  - sheet_profiles.json    — {"supplier::sheet": {include, header_row,
                              anchor_column, anchor_type, is_subtable, ...}}
                              scoped per supplier so two suppliers both
                              having e.g. a "POS" sheet don't collide.
"""
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

STD_HEADERS_FILE = DATA_DIR / "standard_headers.json"
MAPPINGS_FILE = DATA_DIR / "mappings.json"
SHEET_PROFILES_FILE = DATA_DIR / "sheet_profiles.json"


def load_json(path: Path, default):
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return default
    return default


def save_json(path: Path, data) -> bool:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except OSError:
        return False


def normalize(s: str) -> str:
    s = str(s or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def sheet_profile_key(supplier: str, sheet_name: str) -> str:
    return f"{normalize(supplier)}::{normalize(sheet_name)}"


# ---- standard headers -------------------------------------------------
def load_standard_headers(default_headers: list) -> list:
    headers = load_json(STD_HEADERS_FILE, None)
    if headers is None:
        save_json(STD_HEADERS_FILE, default_headers)
        return list(default_headers)
    return headers


def save_standard_headers(headers: list) -> bool:
    return save_json(STD_HEADERS_FILE, headers)


# ---- column mappings (global, by normalized source header) -----------
def load_mappings() -> dict:
    return load_json(MAPPINGS_FILE, {})


def save_mappings(mappings: dict) -> bool:
    return save_json(MAPPINGS_FILE, mappings)


# ---- sheet profiles (per supplier + sheet name) -----------------------
def load_sheet_profiles() -> dict:
    return load_json(SHEET_PROFILES_FILE, {})


def save_sheet_profiles(profiles: dict) -> bool:
    return save_json(SHEET_PROFILES_FILE, profiles)


# ---- backup / restore ---------------------------------------------------
def build_backup(mappings: dict, sheet_profiles: dict, standard_headers: list) -> str:
    return json.dumps(
        {
            "mappings": mappings,
            "sheet_profiles": sheet_profiles,
            "standard_headers": standard_headers,
        },
        indent=2,
        ensure_ascii=False,
    )


def is_writable() -> bool:
    try:
        probe = DATA_DIR / ".write_test"
        probe.write_text("ok")
        probe.unlink()
        return True
    except OSError:
        return False
