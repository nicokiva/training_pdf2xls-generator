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
