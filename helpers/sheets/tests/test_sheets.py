"""
Tests for helpers/sheets/sheets.py — mocks Google API to avoid real I/O.
"""
import pytest
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# sheets_tab_exists
# ---------------------------------------------------------------------------

class TestSheetsTabExists:
    def _make_service(self, tab_names):
        service = MagicMock()
        service.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": t}} for t in tab_names]
        }
        return service

    def test_returns_true_when_tab_exists(self):
        from helpers.sheets import sheets_tab_exists
        service = self._make_service(["Rutina1", "Rutina2"])
        assert sheets_tab_exists(service, "fake-id", "Rutina1") is True

    def test_returns_false_when_tab_does_not_exist(self):
        from helpers.sheets import sheets_tab_exists
        service = self._make_service(["Rutina1"])
        assert sheets_tab_exists(service, "fake-id", "Rutina2") is False

    def test_empty_spreadsheet_returns_false(self):
        from helpers.sheets import sheets_tab_exists
        service = self._make_service([])
        assert sheets_tab_exists(service, "fake-id", "Any") is False


# ---------------------------------------------------------------------------
# get_sheet_id
# ---------------------------------------------------------------------------

class TestGetSheetId:
    def _make_service(self, sheets):
        service = MagicMock()
        service.spreadsheets().get().execute.return_value = {"sheets": sheets}
        return service

    def test_returns_correct_sheet_id(self):
        from helpers.sheets import get_sheet_id
        service = self._make_service([
            {"properties": {"title": "TabA", "sheetId": 111}},
            {"properties": {"title": "TabB", "sheetId": 222}},
        ])
        assert get_sheet_id(service, "fake-id", "TabB") == 222

    def test_raises_when_tab_not_found(self):
        from helpers.sheets import get_sheet_id
        service = self._make_service([
            {"properties": {"title": "TabA", "sheetId": 111}},
        ])
        with pytest.raises(ValueError, match="TabX"):
            get_sheet_id(service, "fake-id", "TabX")


# ---------------------------------------------------------------------------
# build_sheet_values
# ---------------------------------------------------------------------------

class TestBuildSheetValues:
    def _make_days_data(self):
        return {
            1: [
                {"name": "Sentadilla", "is_comb": False, "week_reps": [[10, 10, 8], [9, 9, 8], None, None]},
            ]
        }

    def test_returns_list(self):
        from helpers.sheets import build_sheet_values
        result = build_sheet_values(self._make_days_data())
        assert isinstance(result, list)

    def test_first_row_is_day_header(self):
        from helpers.sheets import build_sheet_values
        result = build_sheet_values(self._make_days_data())
        assert result[0][0] == "Dia 1"

    def test_contains_exercise_name(self):
        from helpers.sheets import build_sheet_values
        result = build_sheet_values(self._make_days_data())
        all_values = [cell for row in result for cell in row]
        assert "Sentadilla" in all_values

    def test_leaves_unprogrammed_set_cells_empty(self):
        from helpers.sheets import build_sheet_values
        result = build_sheet_values(self._make_days_data())
        ex_row = result[3]  # Dia row, series row, labels row, then first exercise
        assert ex_row[1] == 10  # W1 S1 reps
        assert ex_row[7] == ""  # W1 S4 reps (not programmed in [10,10,8])
        assert ex_row[8] == ""  # W1 S4 peso


# ---------------------------------------------------------------------------
# build_sheet_values — comb exercises
# ---------------------------------------------------------------------------

class TestBuildSheetValuesComb:
    """
    Verifies that combined exercises are prefixed with '[C] ' in column A,
    and that the prefix is applied correctly for adjacent comb groups
    with different comb_group IDs.
    """

    _WEEK_REPS = [[10, 10, 10], [9, 9, 9], [8, 8, 8], [7, 7, 7]]

    def _make_ex(self, name, is_comb, comb_group=None):
        ex = {"name": name, "is_comb": is_comb, "week_reps": self._WEEK_REPS}
        if comb_group is not None:
            ex["comb_group"] = comb_group
        return ex

    def test_comb_exercise_has_C_prefix(self):
        from helpers.sheets import build_sheet_values
        days = {1: [self._make_ex("Abdominal", is_comb=True, comb_group=0)]}
        result = build_sheet_values(days)
        all_values = [cell for row in result for cell in row]
        assert "[C] Abdominal" in all_values

    def test_solo_exercise_has_no_C_prefix(self):
        from helpers.sheets import build_sheet_values
        days = {1: [self._make_ex("Sentadilla", is_comb=False)]}
        result = build_sheet_values(days)
        all_values = [cell for row in result for cell in row]
        assert "Sentadilla" in all_values
        assert not any("[C]" in str(v) for v in all_values)

    def test_adjacent_comb_groups_both_have_C_prefix(self):
        """Two consecutive comb groups (different comb_group IDs) must both show [C]."""
        from helpers.sheets import build_sheet_values
        days = {
            1: [
                self._make_ex("Abdominal",  is_comb=True, comb_group=0),
                self._make_ex("Twist ruso", is_comb=True, comb_group=0),
                self._make_ex("Apertura",   is_comb=True, comb_group=1),
                self._make_ex("Press incl", is_comb=True, comb_group=1),
            ]
        }
        result = build_sheet_values(days)
        all_values = [cell for row in result for cell in row]
        assert "[C] Abdominal"  in all_values
        assert "[C] Twist ruso" in all_values
        assert "[C] Apertura"   in all_values
        assert "[C] Press incl" in all_values

    def test_mixed_comb_and_solo(self):
        from helpers.sheets import build_sheet_values
        days = {
            1: [
                self._make_ex("CombA", is_comb=True,  comb_group=0),
                self._make_ex("Solo",  is_comb=False),
                self._make_ex("CombB", is_comb=True,  comb_group=1),
            ]
        }
        result = build_sheet_values(days)
        all_values = [cell for row in result for cell in row]
        assert "[C] CombA" in all_values
        assert "Solo"      in all_values
        assert not any(v == "[C] Solo" for v in all_values)
        assert "[C] CombB" in all_values
