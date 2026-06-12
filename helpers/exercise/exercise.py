"""
helpers/exercise.py — Utilities for individual exercises.

Responsibilities:
    - Format an exercise name for display in the spreadsheet
    - Calculate the tab name (next Monday)
    - Convert the exercise list into a row layout for the table
"""

from datetime import date, timedelta


def _next_weekday(weekday):
    """Return the next occurrence of weekday (0=Mon … 6=Sun) strictly after today."""
    today = date.today()
    days_ahead = weekday - today.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)


def next_monday():
    """Return the date of next Monday (strictly after today)."""
    return _next_weekday(0)


def next_friday():
    """Return the date of next Friday (strictly after today)."""
    return _next_weekday(4)


def format_tab_date(d):
    """Format a date as DD/MM/YY for use in tab names."""
    return d.strftime("%d/%m/%y")


def make_tab_name(_vigencia_start=None, _vigencia_end=None):
    """
    Generates the name for a newly created active tab: "NextMonday-..."
    The vigencia args are accepted but ignored — the tab name is always
    anchored to the upcoming Monday so all tabs follow the same naming convention.
    """
    return f"{format_tab_date(next_monday())}-..."


def make_closing_tab_name(start_str):
    """
    Returns the closed name for the currently active tab.
    Replaces the '...' suffix with next Friday's date.

    Args:
        start_str: The start portion of the current tab name, e.g. '18/05/26'.

    Returns:
        e.g. '18/05/26-23/05/26'
    """
    return f"{start_str}-{format_tab_date(next_friday())}"


def exercise_display_name(ex):
    """
    Returns the exercise name for display in the spreadsheet.
    If the exercise has a comment (e.g. "HANDS BEHIND THE NECK"),
    appends it in lowercase in parentheses: "Long straight abdominal (hands behind the neck)"
    """
    name    = ex["name"]
    comment = ex.get("comment", "").strip()
    return f"{name} ({comment.lower()})" if comment else name


# ── Day reordering ─────────────────────────────────────────────────────────────

# Preferred order of muscle groups in the spreadsheet.
MUSCLE_ORDER = ["pecho", "hombros", "piernas", "espalda"]

# Keywords (lowercase substrings) used to score each day against a muscle group.
# A day is classified as the group with the most keyword hits across its exercises.
MUSCLE_KEYWORDS = {
    "pecho":   ["pecho", "peck deck", "triceps"],
    "hombros": ["hombros", "militar", "vuelos laterales", "mentón", "menton"],
    "piernas": ["sentadilla", "peso muerto", "rodilla", "estocada", "prensa", "pierna"],
    "espalda": ["dominada", "tirón", "tiron", "dorsal", "depresores", "bíceps", "biceps", "remo en polea"],
}

# The first N exercises of every day are always warmup (abs, rotations, hip extension).
# Skip them so they don't pollute the muscle-group score.
WARMUP_COUNT = 3


def classify_day(exercises):
    """
    Returns the muscle group ('pecho', 'hombros', 'piernas', 'espalda') that best
    describes a day based on its exercises, or None if no group scores above 0.

    Only the exercises after the warmup block are considered.
    """
    main = exercises[WARMUP_COUNT:]
    scores = {group: 0 for group in MUSCLE_KEYWORDS}
    for ex in main:
        name_lower = ex["name"].lower()
        for group, keywords in MUSCLE_KEYWORDS.items():
            for kw in keywords:
                if kw in name_lower:
                    scores[group] += 1
    best_group = max(scores, key=scores.get)
    return best_group if scores[best_group] > 0 else None


def reorder_days(days_dict):
    """
    Reorders the days dict so muscle groups follow MUSCLE_ORDER
    (Pecho → Hombros → Piernas → Espalda).

    Args:
        days_dict: {1: [exercises], 2: [...], ...}  (from parse_pdf)

    Returns:
        New dict with the same keys (1..N) but values reordered by muscle group.
        Days whose group can't be detected keep their relative position.
    """
    day_numbers = sorted(days_dict.keys())
    days_list   = [days_dict[d] for d in day_numbers]

    # Classify each day
    classified = [(classify_day(exs), exs) for exs in days_list]

    # Sort by preferred order; unrecognised groups go to the end
    def sort_key(item):
        group = item[0]
        return MUSCLE_ORDER.index(group) if group in MUSCLE_ORDER else len(MUSCLE_ORDER)

    sorted_days = sorted(classified, key=sort_key)

    # Reassign original day numbers (1, 2, 3, …) to the reordered exercises
    return {day_num: exs for day_num, (_, exs) in zip(day_numbers, sorted_days)}


def day_exercise_layout(exercises):
    """
    Converts the list of exercises for a day into (type, exercise) pairs.
    Types:
        'comb' — combined exercise (yellow background, no separator between them)
        'solo' — individual exercise (white background, with its own border)

    Returns a list of tuples: [('comb', ex), ('solo', ex), ...]
    """
    return [("comb" if ex.get("is_comb") else "solo", ex) for ex in exercises]
