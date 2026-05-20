"""
Tests for helpers/pdf_parser/pdf_parser.py — pure functions only (no PDF I/O).
"""
import pytest
from helpers.pdf_parser import group_lines, line_text, is_exercise_number


def _word(text, x0, top):
    """Helper to create a word dict like pdfplumber returns."""
    return {"text": text, "x0": x0, "top": top}


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
