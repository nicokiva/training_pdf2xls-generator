"""
helpers/exercise_normalizer.py — Exercise name normalization.

Loads exercise_mapping.json and maps raw PDF exercise names to their
canonical forms. For names not in the mapping, applies automatic formatting
rules: agarre/posición qualifiers are moved to parentheses at the end.

The mapping file is loaded lazily and cached in the module-level _mapping
variable. This keeps repeated normalizations cheap while avoiding file I/O
at import time.
"""

import json
import re
from pathlib import Path

_MAPPING_PATH = Path(__file__).parent / "exercise_mapping.json"
# Lazy in-memory cache populated by _load_mapping() on first use.
_mapping = None


def _load_mapping() -> dict:
    """Loads exercise_mapping.json once and reuses it for later calls."""
    global _mapping
    if _mapping is None:
        with open(_MAPPING_PATH, encoding="utf-8") as f:
            _mapping = json.load(f)
    return _mapping


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

    Exact matches from exercise_mapping.json take priority. When no explicit
    mapping exists, a conservative automatic formatter is applied instead.
    """
    mapping = _load_mapping()
    if name in mapping:
        return mapping[name]
    return _auto_format(name)


def normalize_exercises(exercises: list) -> list:
    """
    Normalizes the ``name`` field of each exercise dict in place.

    Returns the same list so callers can use the function fluently while still
    benefiting from in-place updates.
    """
    for ex in exercises:
        ex["name"] = normalize_exercise_name(ex["name"])
    return exercises
