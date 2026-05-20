"""
helpers/exercise.py — Utilities for individual exercises.

Responsibilities:
    - Format an exercise name for display in the spreadsheet
    - Calculate the tab name (next Monday)
    - Convert the exercise list into a row layout for the table
"""

from datetime import date, timedelta


def make_tab_name(_vigencia_start=None, _vigencia_end=None):
    """
    Generates the Google Sheets tab name using next Monday.
    Format: "19/05/26-..."
    If today is Monday, goes to next Monday (not today).
    """
    today = date.today()
    # weekday() returns 0=Monday ... 6=Sunday
    # This formula calculates how many days until next Monday
    days_until_monday = (7 - today.weekday()) % 7 or 7
    next_monday = today + timedelta(days=days_until_monday)
    return next_monday.strftime("%d/%m/%y") + "-..."


def exercise_display_name(ex):
    """
    Returns the exercise name for display in the spreadsheet.
    If the exercise has a comment (e.g. "HANDS BEHIND THE NECK"),
    appends it in lowercase in parentheses: "Long straight abdominal (hands behind the neck)"
    """
    name    = ex["name"]
    comment = ex.get("comment", "").strip()
    return f"{name} ({comment.lower()})" if comment else name


def day_exercise_layout(exercises):
    """
    Converts the list of exercises for a day into (type, exercise) pairs.
    Types:
        'comb' — combined exercise (yellow background, no separator between them)
        'solo' — individual exercise (white background, with its own border)

    Returns a list of tuples: [('comb', ex), ('solo', ex), ...]
    """
    return [("comb" if ex.get("is_comb") else "solo", ex) for ex in exercises]
