"""
helpers/exercise_normalizer.py — Exercise name normalization.

Loads exercise_mapping.json and maps raw PDF exercise names to their
canonical forms. For names not in the mapping, applies automatic formatting
rules: agarre/posición qualifiers are moved to parentheses at the end.

When an exercise is NOT found in the mapping, the auto-formatted name is used
AND the new entry is automatically written back to exercise_mapping.json so
the user can review and adjust it without having to add it manually.

The mapping file is loaded lazily and cached in the module-level _mapping
variable. This keeps repeated normalizations cheap while avoiding file I/O
at import time.
"""

import json
import re
import sys
from pathlib import Path

_MAPPING_PATH = Path(__file__).parent / "exercise_mapping.json"
# Lazy in-memory cache populated by _load_mapping() on first use.
_mapping = None

# exercise_catalog.json lives in the shared/ sibling project.
_CATALOG_PATH = Path(__file__).parent.parent.parent / "shared" / "training_shared" / "exercise_catalog.json"
# Lazy set of canonical exercise names from the catalog.
_catalog_names = None


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
