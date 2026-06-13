"""
helpers/exercise_normalizer.py — Exercise name normalization.

Responsibilities
----------------
1. Map raw PDF exercise labels to their canonical names using
   exercise_mapping.json (explicit, curated table).
2. For labels not in the mapping, apply conservative auto-formatting rules
   (Empuje→Press, agarre/banco/sentado qualifiers → parentheses) and
   persist the new raw→canonical entry back to exercise_mapping.json so
   the user can review or correct it.
3. After resolving the canonical name, verify that it exists in
   exercise_catalog.json (the semantic catalog used by the routine analyser).
   If it is absent, print a one-time warning to stderr so the user knows to
   add the exercise with its attributes (patron, vector, mecanica, etc.).

Caching strategy
----------------
Both the mapping and the catalog are loaded lazily from disk on the first
call and then kept in module-level variables (_mapping, _catalog_names).
This makes repeated normalizations O(1) after the first call while avoiding
file I/O at import time.

Warning deduplication
---------------------
Catalog warnings are emitted at most once per canonical name per process
run. The _warned_catalog set tracks which names have already been flagged.
Mapping warnings are naturally deduplicated because once a name is written
to the mapping it will be found on subsequent calls and the save path is
never reached again.
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional

# ── File paths ────────────────────────────────────────────────────────────────

# Raw→canonical name table, auto-updated when new exercises are encountered.
_MAPPING_PATH = Path(__file__).parent / "exercise_mapping.json"

# Semantic exercise catalog (patron, vector, mecanica, estabilizacion).
# Lives in the sibling shared/ project; path: training/shared/training_shared/
_CATALOG_PATH = (
    Path(__file__).parent.parent.parent
    / "shared" / "training_shared" / "exercise_catalog.json"
)

# ── Lazy caches ───────────────────────────────────────────────────────────────

# Dict loaded from exercise_mapping.json; None until first use.
_mapping: Optional[dict] = None  # type: ignore[assignment]

# Set of canonical names loaded from exercise_catalog.json;
# None until first use; empty set when the catalog file is not found.
_catalog_names: Optional[set] = None  # type: ignore[assignment]

# Canonical names for which a catalog-missing warning has already been shown
# this process run, to avoid flooding stderr with repeated warnings.
_warned_catalog: set = set()


def _load_mapping() -> dict:
    """Loads exercise_mapping.json once and reuses it for later calls."""
    global _mapping
    if _mapping is None:
        with open(_MAPPING_PATH, encoding="utf-8") as f:
            _mapping = json.load(f)
    return _mapping


def _load_catalog_names() -> set:
    """
    Loads the set of canonical exercise names from exercise_catalog.json once.

    The catalog is a list of dicts with an 'ejercicio' key. If the file does
    not exist (e.g. the shared project is not present), an empty set is
    returned and no error is raised — the catalog check is best-effort.
    """
    global _catalog_names
    if _catalog_names is None:
        if _CATALOG_PATH.exists():
            with open(_CATALOG_PATH, encoding="utf-8") as f:
                catalog = json.load(f)
            _catalog_names = {entry["ejercicio"] for entry in catalog}
        else:
            _catalog_names = set()
    return _catalog_names


def _save_mapping(mapping: dict) -> None:
    """Writes the in-memory mapping back to exercise_mapping.json (sorted by key)."""
    with open(_MAPPING_PATH, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2, sort_keys=True)


def _auto_format(name: str) -> str:
    """
    Applies fallback normalization rules to an unmapped exercise name.

    This keeps the output readable even when a raw PDF label is missing from
    exercise_mapping.json. The rules only reshape common suffix qualifiers;
    they do not attempt to infer a different exercise.

    Rules:
      - "Empuje ..."              → "Press ..."
      - "... con agarre X"        → "... (agarre X)"
      - "... agarre X"            → "... (agarre X)"
      - "... en banco plano"      → "... (banco plano)"
      - "... en banco inclinado"  → "... (banco inclinado)"
      - "... (sentado)" / "... sentado" at end → "... (sentado)"
    """
    # Empuje → Press
    if name.startswith("Empuje "):
        name = "Press " + name[7:]

    # "con agarre X" or "agarre X" → "(agarre X)"
    name = re.sub(r'\s+con agarre\s+(\w+)', r' (agarre \1)', name)
    name = re.sub(r'\s+agarre\s+(\w+)$', r' (agarre \1)', name)

    # "en banco plano/inclinado" → "(banco plano/inclinado)"
    name = re.sub(r'\s+en banco\s+(plano|inclinado)', r' (banco \1)', name, flags=re.IGNORECASE)

    # trailing "sentado" → "(sentado)"
    name = re.sub(r'\s+sentado$', r' (sentado)', name, flags=re.IGNORECASE)

    return name.strip()


def normalize_exercise_name(name: str) -> str:
    """
    Returns the canonical display name for a raw exercise label.

    Lookup order:
      1. exercise_mapping.json — explicit raw→canonical mapping.
      2. Auto-format rules (_auto_format) — applied when no mapping exists.

    Side-effects for unknown/uncatalogued exercises:
      - If the raw name is not in the mapping, the auto-formatted canonical is
        written back to exercise_mapping.json and a warning is printed to stderr.
      - If the resulting canonical is not in exercise_catalog.json, a separate
        warning is printed so the user can add the exercise to the catalog with
        its semantic attributes (pattern, vector, mechanics, etc.).
    """
    mapping = _load_mapping()

    if name in mapping:
        canonical = mapping[name]
    else:
        canonical = _auto_format(name)
        mapping[name] = canonical
        _save_mapping(mapping)
        print(
            f"\n⚠️  UNMAPPED EXERCISE — added to exercise_mapping.json automatically:\n"
            f'   "{name}" → "{canonical}"\n'
            f"   Edit helpers/exercise_mapping.json if the canonical name is wrong.\n",
            file=sys.stderr,
        )

    # Warn if the canonical name is missing from the exercise catalog
    catalog = _load_catalog_names()
    if catalog and canonical not in catalog:
        print(
            f"\n⚠️  EXERCISE NOT IN CATALOG — add it to exercise_catalog.json:\n"
            f'   "{canonical}"\n'
            f"   File: shared/training_shared/exercise_catalog.json\n",
            file=sys.stderr,
        )

    return canonical


def normalize_exercises(exercises: list) -> list:
    """
    Normalizes the ``name`` field of each exercise dict in place.

    Returns the same list so callers can use the function fluently while still
    benefiting from in-place updates.
    """
    for ex in exercises:
        ex["name"] = normalize_exercise_name(ex["name"])
    return exercises
