"""
Tests for helpers/pdf_parser/pdf_parser.py — pure functions only (no PDF I/O).

parse_column is tested with synthetic word lists that simulate pdfplumber output.
parse_pdf requires a real PDF and is exercised through integration, not unit tests.
"""
import pytest
from helpers.pdf_parser import group_lines, line_text, is_exercise_number
from helpers.pdf_parser.pdf_parser import parse_column, parse_pdf


def _word(text, x0, top):
    """Helper to create a word dict like pdfplumber returns."""
    return {"text": text, "x0": x0, "top": top}


# ---------------------------------------------------------------------------
# Synthetic word-list helpers for parse_column
# ---------------------------------------------------------------------------

def _ex_words(number, name, top, x0=60, reps=(10, 9, 8, 7)):
    """
    Build the minimal set of words needed for ONE left-column exercise entry.

    Produces: number word, name word, 'repeticiones' + 4 rep values,
    and 2da/3ra/4ta progression lines.
    The x0 defaults (60 for number, 100 for name) fall inside
    LEFT_EX_NUM_X_RANGE (55-80).
    """
    return [
        {"text": str(number), "x0": x0,      "top": top},
        {"text": name,        "x0": x0 + 40, "top": top},
        # Week 1 repetitions
        {"text": "repeticiones", "x0": x0,       "top": top + 20},
        {"text": str(reps[0]),   "x0": x0 + 70,  "top": top + 20},
        {"text": str(reps[0]),   "x0": x0 + 90,  "top": top + 20},
        {"text": str(reps[0]),   "x0": x0 + 110, "top": top + 20},
        {"text": str(reps[0]),   "x0": x0 + 130, "top": top + 20},
        # Week 2-4 progressions
        {"text": "2da", "x0": x0,      "top": top + 40},
        {"text": str(reps[1]), "x0": x0 + 40, "top": top + 40},
        {"text": "3ra", "x0": x0,      "top": top + 60},
        {"text": str(reps[2]), "x0": x0 + 40, "top": top + 60},
        {"text": "4ta", "x0": x0,      "top": top + 80},
        {"text": str(reps[3]), "x0": x0 + 40, "top": top + 80},
    ]


def _comb_header(count, x0=60, top=240):
    """Words for a 'Comb xN' marker line."""
    return [
        {"text": "Comb",       "x0": x0,      "top": top},
        {"text": f"x{count}",  "x0": x0 + 40, "top": top},
    ]


# ---------------------------------------------------------------------------
# group_lines
# ---------------------------------------------------------------------------

class TestGroupLines:
    def test_empty_input_returns_empty(self):
        assert group_lines([]) == []

    def test_single_word_returns_one_line(self):
        words = [_word("Hello", 10, 100)]
        lines = group_lines(words)
        assert len(lines) == 1
        assert lines[0][0]["text"] == "Hello"

    def test_words_same_y_grouped_in_one_line(self):
        words = [_word("A", 10, 100), _word("B", 50, 100), _word("C", 90, 100)]
        lines = group_lines(words)
        assert len(lines) == 1
        assert len(lines[0]) == 3

    def test_words_different_y_split_into_multiple_lines(self):
        words = [_word("A", 10, 100), _word("B", 10, 200)]
        lines = group_lines(words)
        assert len(lines) == 2

    def test_words_within_tolerance_grouped_together(self):
        # y_tolerance=4 means words at y=100 and y=103 are same line
        words = [_word("A", 10, 100), _word("B", 50, 103)]
        lines = group_lines(words, y_tolerance=4)
        assert len(lines) == 1

    def test_words_outside_tolerance_on_separate_lines(self):
        # y diff = 10 > tolerance 4
        words = [_word("A", 10, 100), _word("B", 50, 110)]
        lines = group_lines(words, y_tolerance=4)
        assert len(lines) == 2

    def test_words_within_line_sorted_by_x(self):
        # Words out of order by X
        words = [_word("Z", 90, 100), _word("A", 10, 100), _word("M", 50, 100)]
        lines = group_lines(words)
        line = lines[0]
        assert line[0]["text"] == "A"
        assert line[1]["text"] == "M"
        assert line[2]["text"] == "Z"

    def test_three_distinct_lines(self):
        words = [
            _word("Line1Word1", 10, 100), _word("Line1Word2", 50, 101),
            _word("Line2Word1", 10, 200), _word("Line2Word2", 50, 200),
            _word("Line3Word1", 10, 300),
        ]
        lines = group_lines(words)
        assert len(lines) == 3

    def test_custom_tolerance(self):
        words = [_word("A", 10, 100), _word("B", 50, 108)]
        # With tolerance=10, should be grouped
        assert len(group_lines(words, y_tolerance=10)) == 1
        # With tolerance=4, should be separate
        assert len(group_lines(words, y_tolerance=4)) == 2


# ---------------------------------------------------------------------------
# line_text
# ---------------------------------------------------------------------------

class TestLineText:
    def test_joins_words_with_spaces(self):
        line = [_word("Hello", 0, 0), _word("World", 50, 0)]
        assert line_text(line) == "Hello World"

    def test_single_word(self):
        line = [_word("Solo", 0, 0)]
        assert line_text(line) == "Solo"

    def test_empty_line(self):
        assert line_text([]) == ""


# ---------------------------------------------------------------------------
# is_exercise_number
# ---------------------------------------------------------------------------

class TestIsExerciseNumber:
    def test_valid_left_column_number(self):
        word = _word("5", 60, 300)  # x0=60, in LEFT_EX_NUM_X_RANGE (55-80)
        assert is_exercise_number(word, "left") is True

    def test_valid_right_column_number(self):
        word = _word("3", 355, 300)  # x0=355, in RIGHT_EX_NUM_X_RANGE (345-370)
        assert is_exercise_number(word, "right") is True

    def test_non_digit_returns_false(self):
        word = _word("kg", 60, 300)
        assert is_exercise_number(word, "left") is False

    def test_number_out_of_range_returns_false(self):
        word = _word("25", 60, 300)  # > 20
        assert is_exercise_number(word, "left") is False

    def test_zero_returns_false(self):
        word = _word("0", 60, 300)
        assert is_exercise_number(word, "left") is False

    def test_valid_number_wrong_column_returns_false(self):
        # x0=60 is in left range, but we ask for right
        word = _word("5", 60, 300)
        assert is_exercise_number(word, "right") is False

    def test_boundary_values(self):
        word_min = _word("1", 55, 300)   # LEFT min boundary
        word_max = _word("20", 80, 300)  # LEFT max boundary
        assert is_exercise_number(word_min, "left") is True
        assert is_exercise_number(word_max, "left") is True


# ---------------------------------------------------------------------------
# parse_column
# ---------------------------------------------------------------------------

class TestParseColumn:
    """
    Tests for parse_column using synthetic word lists.

    The LEFT_EX_NUM_X_RANGE is (55, 80), so exercise numbers use x0=60.
    We call parse_column with header_bottom_y=0 so no words are filtered out
    by the header.  All words must fall inside x_min=0, x_max=290.
    """

    def _single_exercise(self, number=1, name="Sentadilla", top=250):
        """Minimal words for one left-column exercise."""
        return _ex_words(number, name, top)

    def _two_exercise_comb(self):
        """Words for a 'Comb x2' block with two consecutive exercises."""
        return (
            _comb_header(2, top=240)
            + _ex_words(1, "PrimerEjercicio",   top=260)
            + _ex_words(2, "SegundoEjercicio",  top=360)
        )

    # ── Position fields ──────────────────────────────────────────────────

    def test_exercise_stores_top(self):
        exs, _ = parse_column(self._single_exercise(top=250), 0, 290, "left", 0)
        assert exs[0]["top"] == 250

    def test_exercise_stores_x0(self):
        exs, _ = parse_column(self._single_exercise(), 0, 290, "left", 0)
        assert exs[0]["x0"] == 60   # default x0 for left-col number

    def test_exercise_top_reflects_number_word_position(self):
        # Two exercises at different Y — each should record its own top
        words = _ex_words(1, "Primero", top=300) + _ex_words(2, "Segundo", top=500)
        exs, _ = parse_column(words, 0, 290, "left", 0)
        assert exs[0]["top"] == 300
        assert exs[1]["top"] == 500

    # ── Comb group format ────────────────────────────────────────────────

    def test_solo_exercise_has_empty_comb_groups(self):
        _, combs = parse_column(self._single_exercise(), 0, 290, "left", 0)
        assert combs == []

    def test_comb_block_produces_one_group(self):
        _, combs = parse_column(self._two_exercise_comb(), 0, 290, "left", 0)
        assert len(combs) == 1

    def test_comb_block_of_three_produces_one_group(self):
        words = (
            _comb_header(3, top=240)
            + _ex_words(1, "A", top=260)
            + _ex_words(2, "B", top=360)
            + _ex_words(3, "C", top=460)
        )
        exs, combs = parse_column(words, 0, 290, "left", 0)
        assert len(combs) == 1
        assert combs[0][1] == 3
        assert exs[0]["is_comb"] is True
        assert exs[1]["is_comb"] is True
        assert exs[2]["is_comb"] is True

    def test_comb_groups_entry_is_object_reference_not_number(self):
        """comb_groups must store a reference to the exercise dict, not its number."""
        exs, combs = parse_column(self._two_exercise_comb(), 0, 290, "left", 0)
        start_ref, count = combs[0]
        assert start_ref is exs[0], "comb_groups[0][0] must be the same object as exercises[0]"

    def test_comb_groups_count_matches_comb_header(self):
        _, combs = parse_column(self._two_exercise_comb(), 0, 290, "left", 0)
        assert combs[0][1] == 2

    def test_comb_exercises_marked_is_comb_true(self):
        exs, _ = parse_column(self._two_exercise_comb(), 0, 290, "left", 0)
        assert exs[0]["is_comb"] is True
        assert exs[1]["is_comb"] is True

    def test_solo_exercise_is_comb_false(self):
        exs, _ = parse_column(self._single_exercise(), 0, 290, "left", 0)
        assert exs[0]["is_comb"] is False

    def test_two_comb_groups_stored_separately(self):
        """Two 'Comb x2' blocks must produce two separate entries in comb_groups."""
        words = (
            _comb_header(2, top=240)
            + _ex_words(1, "A", top=260)
            + _ex_words(2, "B", top=360)
            + _comb_header(2, top=470)
            + _ex_words(3, "C", top=490)
            + _ex_words(4, "D", top=590)
        )
        exs, combs = parse_column(words, 0, 290, "left", 0)
        assert len(combs) == 2
        assert combs[0][0] is exs[0]   # first group starts at exercise 0
        assert combs[1][0] is exs[2]   # second group starts at exercise 2
        assert combs[0][1] == 2
        assert combs[1][1] == 2

    def test_exercise_after_comb_block_is_not_comb(self):
        """An exercise that follows a completed Comb block must not be marked as comb."""
        words = (
            _comb_header(2, top=240)
            + _ex_words(1, "CombA", top=260)
            + _ex_words(2, "CombB", top=360)
            + _ex_words(3, "Solo",  top=470)
        )
        exs, _ = parse_column(words, 0, 290, "left", 0)
        assert exs[0]["is_comb"] is True
        assert exs[1]["is_comb"] is True
        assert exs[2]["is_comb"] is False

    def test_progression_remainder_is_not_saved_as_comment(self):
        words = [
            {"text": "1", "x0": 60, "top": 250},
            {"text": "Press de pecho", "x0": 100, "top": 250},
            {"text": "repeticiones", "x0": 60, "top": 270},
            {"text": "6", "x0": 130, "top": 270},
            {"text": "6", "x0": 150, "top": 270},
            {"text": "6", "x0": 170, "top": 270},
            {"text": "2da", "x0": 60, "top": 290},
            {"text": "6", "x0": 100, "top": 290},
            {"text": "/6/8/10", "x0": 140, "top": 290},
        ]
        exs, _ = parse_column(words, 0, 290, "left", 0)
        assert exs[0]["name"] == "Press de pecho"
        assert "comment" not in exs[0]

    def test_progression_igual_and_slash_scheme(self):
        words = [
            {"text": "1", "x0": 60, "top": 250},
            {"text": "Press de pecho", "x0": 100, "top": 250},
            {"text": "repeticiones", "x0": 60, "top": 270},
            {"text": "6", "x0": 130, "top": 270},
            {"text": "8", "x0": 150, "top": 270},
            {"text": "10", "x0": 170, "top": 270},
            {"text": "12", "x0": 190, "top": 270},
            {"text": "2da", "x0": 60, "top": 290},
            {"text": "igual", "x0": 100, "top": 290},
            {"text": "3ra", "x0": 60, "top": 310},
            {"text": "4/6/8/10", "x0": 100, "top": 310},
            {"text": "con", "x0": 180, "top": 310},
            {"text": "mas", "x0": 210, "top": 310},
            {"text": "peso", "x0": 235, "top": 310},
            {"text": "4ta", "x0": 60, "top": 330},
            {"text": "igual", "x0": 100, "top": 330},
        ]
        exs, _ = parse_column(words, 0, 290, "left", 0)
        ex = exs[0]
        assert ex["week_reps"][0] == [6, 8, 10, 12]
        assert ex["week_reps"][1] == [6, 8, 10, 12]
        assert ex["week_reps"][2] == [4, 6, 8, 10]
        assert ex["week_reps"][3] == [4, 6, 8, 10]
        assert "comment" not in ex

    # ── Header filtering ─────────────────────────────────────────────────

    def test_words_above_header_are_ignored(self):
        """Words with top <= header_bottom_y should be skipped."""
        # Exercise at top=100, header at 200 → exercise should be excluded
        words = _ex_words(1, "Escondido", top=100)
        exs, _ = parse_column(words, 0, 290, "left", header_bottom_y=200)
        assert exs == []

    def test_words_below_header_are_included(self):
        words = _ex_words(1, "Visible", top=250)
        exs, _ = parse_column(words, 0, 290, "left", header_bottom_y=200)
        assert len(exs) == 1


class TestParsePdfCombAcrossColumns:
    def test_comb_header_marks_both_columns(self, monkeypatch, tmp_path):
        class FakePage:
            def __init__(self, words, text):
                self._words = words
                self._text = text
            def extract_words(self):
                return list(self._words)
            def extract_text(self):
                return self._text

        class FakePdf:
            def __init__(self, pages):
                self.pages = pages
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False

        words = [
            {"text": "1", "x0": 294, "top": 218},
            {"text": "Comb", "x0": 8, "top": 241},
            {"text": "x2", "x0": 45, "top": 241},
            {"text": "1", "x0": 63.9, "top": 260.5},
            {"text": "Press", "x0": 101, "top": 260.5},
            {"text": "de", "x0": 140, "top": 260.5},
            {"text": "pecho", "x0": 155, "top": 260.5},
            {"text": "2", "x0": 355.4, "top": 260.5},
            {"text": "Biceps", "x0": 373, "top": 260.5},
            {"text": "con", "x0": 420, "top": 260.5},
            {"text": "mancuernas", "x0": 450, "top": 260.5},
            {"text": "Series", "x0": 60.7, "top": 277.5},
            {"text": "1", "x0": 207.7, "top": 277.5},
            {"text": "2", "x0": 241.5, "top": 277.5},
            {"text": "3", "x0": 275.3, "top": 277.5},
            {"text": "Series", "x0": 352.2, "top": 277.5},
            {"text": "1", "x0": 499.2, "top": 277.5},
            {"text": "2", "x0": 533.0, "top": 277.5},
            {"text": "3", "x0": 566.8, "top": 277.5},
            {"text": "repeticiones", "x0": 60.7, "top": 294.5},
            {"text": "6", "x0": 204.4, "top": 294.5},
            {"text": "6", "x0": 238.3, "top": 294.5},
            {"text": "6", "x0": 272.1, "top": 294.5},
            {"text": "repeticiones", "x0": 352.2, "top": 294.5},
            {"text": "6", "x0": 495.9, "top": 294.5},
            {"text": "6", "x0": 529.8, "top": 294.5},
            {"text": "6", "x0": 563.6, "top": 294.5},
            {"text": "2da", "x0": 10, "top": 324.5},
            {"text": "igual", "x0": 40, "top": 324.5},
            {"text": "2da", "x0": 301.5, "top": 324.5},
            {"text": "igual", "x0": 331.5, "top": 324.5},
        ]

        fake_pdf = FakePdf([FakePage(words, "Vigencia: 01/01/2026 - 01/02/2026")])
        monkeypatch.setattr("helpers.pdf_parser.pdf_parser.pdfplumber.open", lambda _: fake_pdf)

        result = parse_pdf("fake.pdf")
        day = result["days"][1]
        assert day[0]["is_comb"] is True
        assert day[1]["is_comb"] is True
        assert day[0]["comb_group"] == day[1]["comb_group"]
