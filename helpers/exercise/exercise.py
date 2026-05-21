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


def day_exercise_layout(exercises):
    """
    Converts the list of exercises for a day into (type, exercise) pairs.
    Types:
        'comb' — combined exercise (yellow background, no separator between them)
        'solo' — individual exercise (white background, with its own border)

    Returns a list of tuples: [('comb', ex), ('solo', ex), ...]
    """
    return [("comb" if ex.get("is_comb") else "solo", ex) for ex in exercises]
