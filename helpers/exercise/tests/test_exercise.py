"""
Tests for helpers/exercise/exercise.py — pure functions, no I/O.
"""
import pytest
import re
from datetime import date, timedelta
from helpers.exercise import make_tab_name, exercise_display_name, day_exercise_layout


class TestMakeTabName:
    def test_returns_string(self):
        result = make_tab_name()
        assert isinstance(result, str)

    def test_format_is_dd_mm_yy_dash(self):
        result = make_tab_name()
        # Should start with DD/MM/YY-...
        assert re.match(r"^\d{2}/\d{2}/\d{2}-\.\.\.$", result), f"Unexpected format: {result}"

    def test_is_always_a_monday(self):
        result = make_tab_name()
        day_str = result[:8]  # "DD/MM/YY"
        d = date(int("20" + day_str[6:8]), int(day_str[3:5]), int(day_str[0:2]))
        assert d.weekday() == 0, f"Expected Monday (0), got {d.weekday()} for {d}"

    def test_is_in_the_future(self):
        result = make_tab_name()
        day_str = result[:8]
        d = date(int("20" + day_str[6:8]), int(day_str[3:5]), int(day_str[0:2]))
        assert d > date.today(), f"Expected future date, got {d}"

    def test_if_today_is_monday_returns_next_monday(self, monkeypatch):
        # Force today to be a Monday (weekday=0)
        monday = date(2026, 5, 18)  # a known Monday
        monkeypatch.setattr(
            "helpers.exercise.exercise.date",
            type("FakeDate", (), {
                "today": staticmethod(lambda: monday),
                "weekday": lambda self: date.weekday(self),
                "__add__": lambda self, other: date.__add__(self, other),
            })
        )
        # Re-import to pick up monkeypatch — call directly from module
        from helpers.exercise.exercise import make_tab_name as _make_tab_name
        result = _make_tab_name()
        day_str = result[:8]
        d = date(int("20" + day_str[6:8]), int(day_str[3:5]), int(day_str[0:2]))
        assert d == monday + timedelta(days=7), f"Expected next Monday, got {d}"


class TestExerciseDisplayName:
    def test_name_without_comment(self):
        ex = {"name": "Sentadilla"}
        assert exercise_display_name(ex) == "Sentadilla"

    def test_name_with_comment_is_lowercase_in_parens(self):
        ex = {"name": "Abdominal recto largo", "comment": "MANOS ATRAS DE LA NUCA"}
        result = exercise_display_name(ex)
        assert result == "Abdominal recto largo (manos atras de la nuca)"

    def test_empty_comment_treated_as_no_comment(self):
        ex = {"name": "Press inclinado", "comment": ""}
        assert exercise_display_name(ex) == "Press inclinado"

    def test_whitespace_only_comment_treated_as_no_comment(self):
        ex = {"name": "Press inclinado", "comment": "   "}
        assert exercise_display_name(ex) == "Press inclinado"

    def test_comment_key_missing(self):
        ex = {"name": "Curl de biceps"}
        assert exercise_display_name(ex) == "Curl de biceps"


class TestDayExerciseLayout:
    def test_comb_exercise_returns_comb_type(self):
        exercises = [{"name": "A", "is_comb": True}]
        layout = day_exercise_layout(exercises)
        assert layout[0][0] == "comb"

    def test_non_comb_returns_solo_type(self):
        exercises = [{"name": "B", "is_comb": False}]
        layout = day_exercise_layout(exercises)
        assert layout[0][0] == "solo"

    def test_missing_is_comb_defaults_to_solo(self):
        exercises = [{"name": "C"}]
        layout = day_exercise_layout(exercises)
        assert layout[0][0] == "solo"

    def test_exercise_is_preserved_in_tuple(self):
        ex = {"name": "Sentadilla", "is_comb": False}
        layout = day_exercise_layout([ex])
        assert layout[0][1] is ex

    def test_mixed_exercises(self):
        exercises = [
            {"name": "A", "is_comb": True},
            {"name": "B", "is_comb": True},
            {"name": "C", "is_comb": False},
        ]
        layout = day_exercise_layout(exercises)
        assert layout[0][0] == "comb"
        assert layout[1][0] == "comb"
        assert layout[2][0] == "solo"

    def test_empty_exercises_returns_empty(self):
        assert day_exercise_layout([]) == []


def _make_exercises(*names):
    """Helper: build a minimal exercise list with warmup + given main exercises."""
    warmup = [
        {"name": "Abdominal recto largo", "is_comb": False},
        {"name": "Rotaciones de pie con disco", "is_comb": False},
        {"name": "Extensión de cadera en banco", "is_comb": False},
    ]
    main = [{"name": n, "is_comb": False} for n in names]
    return warmup + main


class TestClassifyDay:
    from helpers.exercise import classify_day

    def test_pecho(self):
        from helpers.exercise import classify_day
        exs = _make_exercises("Empuje de pecho con barra en banco plano", "Peck Deck (pecho)", "Triceps con polea")
        assert classify_day(exs) == "pecho"

    def test_hombros(self):
        from helpers.exercise import classify_day
        exs = _make_exercises("Empuje de hombros con barra (sentado)", "Vuelos laterales con mancuernas", "Remo al mentón")
        assert classify_day(exs) == "hombros"

    def test_piernas(self):
        from helpers.exercise import classify_day
        exs = _make_exercises("Sentadilla clásica", "Peso muerto", "Prensa Hammer 45°", "Extensión de rodillas en máquina")
        assert classify_day(exs) == "piernas"

    def test_espalda(self):
        from helpers.exercise import classify_day
        exs = _make_exercises("Dominada estricta", "Tirón dorsal en polea", "Depresores en polea", "Biceps con polea")
        assert classify_day(exs) == "espalda"


class TestReorderDays:
    def test_reorders_to_preferred_order(self):
        from helpers.exercise import reorder_days
        days = {
            1: _make_exercises("Empuje de hombros con barra (sentado)", "Vuelos laterales con mancuernas"),
            2: _make_exercises("Empuje de pecho con barra en banco plano", "Peck Deck (pecho)"),
            3: _make_exercises("Sentadilla clásica", "Peso muerto"),
            4: _make_exercises("Dominada estricta", "Tirón dorsal en polea"),
        }
        reordered = reorder_days(days)
        # Keys stay 1..4; values should be pecho, hombros, piernas, espalda
        from helpers.exercise import classify_day
        assert classify_day(reordered[1]) == "pecho"
        assert classify_day(reordered[2]) == "hombros"
        assert classify_day(reordered[3]) == "piernas"
        assert classify_day(reordered[4]) == "espalda"

    def test_already_correct_order_unchanged(self):
        from helpers.exercise import reorder_days, classify_day
        days = {
            1: _make_exercises("Empuje de pecho con barra en banco plano", "Peck Deck (pecho)"),
            2: _make_exercises("Empuje de hombros con barra (sentado)", "Vuelos laterales con mancuernas"),
            3: _make_exercises("Sentadilla clásica", "Peso muerto"),
            4: _make_exercises("Dominada estricta", "Tirón dorsal en polea"),
        }
        reordered = reorder_days(days)
        assert classify_day(reordered[1]) == "pecho"
        assert classify_day(reordered[2]) == "hombros"
        assert classify_day(reordered[3]) == "piernas"
        assert classify_day(reordered[4]) == "espalda"
