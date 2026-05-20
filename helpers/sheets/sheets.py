"""
helpers/sheets.py — Google Sheets integration.

Responsibilities:
    - Authenticate with the Google API using a Service Account
    - Create/delete tabs in the spreadsheet
    - Write data to the grid
    - Apply all visual formatting (borders, colors, columns, freeze)
"""

from helpers.exercise import exercise_display_name, day_exercise_layout


# Permissions requested from Google (read and write spreadsheets)
SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_sheets_service(credentials_path):
    """
    Creates and returns the authenticated Google Sheets API client.
    Uses a Service Account (JSON credentials file).
    """
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        credentials_path, scopes=SHEETS_SCOPES
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def sheets_tab_exists(service, spreadsheet_id, tab_name):
    """Returns True if a tab with that name already exists in the spreadsheet."""
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    return any(s["properties"]["title"] == tab_name for s in meta["sheets"])


def get_sheet_id(service, spreadsheet_id, tab_name):
    """Returns the internal numeric sheetId of a tab (needed to apply formatting)."""
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == tab_name:
            return s["properties"]["sheetId"]
    raise ValueError(f"Tab '{tab_name}' not found")


def apply_sheet_formatting(service, spreadsheet_id, sheet_id, days_data, n_weeks=4, n_series=3):
    """
    Applies all visual formatting to the tab: borders, background colors, merged cells,
    column widths and frozen column.

    The Google Sheets API works with "requests" (change requests) that are
    accumulated in a list and sent all at once in a single batchUpdate call.
    This is more efficient than making one call per change.
    """
    # ── Border styles ─────────────────────────────────────────────────────────
    THICK     = {"style": "SOLID_THICK", "colorStyle": {"rgbColor": {}}}   # thick black border
    THIN      = {"style": "SOLID",       "colorStyle": {"rgbColor": {}}}   # thin black border
    NO_BORDER = {"style": "NONE"}

    # ── Background colors (RGB from 0.0 to 1.0, not 0 to 255) ────────────────
    GREEN_BG = {"red": 0.851, "green": 0.918, "blue": 0.827}   # set number row
    GRAY_BG  = {"red": 0.941, "green": 0.941, "blue": 0.941}   # Rep./Peso row
    PEACH_BG = {"red": 1.0,   "green": 0.949, "blue": 0.8}     # combined exercise name
    WHITE_BG = {"red": 1.0,   "green": 1.0,   "blue": 1.0}     # individual exercise name

    # Soft colors per week for data cells
    WEEK_COLORS = [
        {"red": 0.94, "green": 0.99, "blue": 0.94},  # week 1: very soft green
        {"red": 0.93, "green": 0.96, "blue": 1.0},   # week 2: very soft blue
        {"red": 0.97, "green": 0.94, "blue": 1.0},   # week 3: very soft lavender
        {"red": 1.0,  "green": 0.94, "blue": 0.93},  # week 4: very soft salmon
    ]

    # Total columns: 1 (name) + 4 weeks × 3 sets × 2 (Rep+Peso) = 25
    n_data_cols = n_weeks * n_series * 2
    total_cols  = 1 + n_data_cols

    def rng(r0, r1, c0, c1):
        """Shortcut to build a cell range (rows r0..r1, columns c0..c1)."""
        return {"sheetId": sheet_id, "startRowIndex": r0, "endRowIndex": r1,
                "startColumnIndex": c0, "endColumnIndex": c1}

    def peso_right(w, s):
        """Right border of the Peso cell: thick at end of each week, thin between sets."""
        return THICK if s == n_series - 1 else THIN

    # ── List of formatting requests ───────────────────────────────────────────
    # Start with global sheet changes (columns, freeze)
    requests = [
        # Fix width of column A (exercise names) to 180px
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                      "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 180},
            "fields": "pixelSize",
        }},
        # Freeze column A: stays visible when scrolling horizontally
        {"updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": {"frozenColumnCount": 1}},
            "fields": "gridProperties.frozenColumnCount",
        }},
        # Fix width of data columns (B onwards) to 45px
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                      "startIndex": 1, "endIndex": 25},
            "properties": {"pixelSize": 45},
            "fields": "pixelSize",
        }},
    ]
    current_row = 0   # current row (0-based index, as used by the Google API)

    for day_num in days_data.keys():
        exercises = days_data[day_num]
        if not exercises:
            continue

        # Row indices for this day
        dia_row    = current_row       # "Dia N" row
        series_row = current_row + 1  # set numbers row
        label_row  = current_row + 2  # Rep./Peso row
        ex_start   = current_row + 3  # first exercise row

        # ── "Dia N" row ───────────────────────────────────────────────────────
        # Cell A: bold + thick borders
        requests.append({"repeatCell": {
            "range": rng(dia_row, dia_row+1, 0, 1),
            "cell": {"userEnteredFormat": {
                "textFormat": {"bold": True},
                "borders": {"top": THICK, "bottom": THICK, "left": THICK, "right": NO_BORDER},
            }},
            "fields": "userEnteredFormat(textFormat,borders)",
        }})
        # Cells B:Y merged + thick borders
        requests.append({"mergeCells": {
            "range": rng(dia_row, dia_row+1, 1, total_cols), "mergeType": "MERGE_ALL"
        }})
        requests.append({"repeatCell": {
            "range": rng(dia_row, dia_row+1, 1, total_cols),
            "cell": {"userEnteredFormat": {
                "borders": {"top": THICK, "bottom": THICK, "right": THICK, "left": NO_BORDER},
            }},
            "fields": "userEnteredFormat(borders)",
        }})

        # ── Set numbers row ───────────────────────────────────────────────────
        # Cell A merged with label row (occupies 2 rows tall)
        requests.append({"mergeCells": {
            "range": rng(series_row, label_row+1, 0, 1), "mergeType": "MERGE_ALL"
        }})
        requests.append({"repeatCell": {
            "range": rng(series_row, series_row+1, 0, 1),
            "cell": {"userEnteredFormat": {
                "borders": {"left": THICK, "right": THIN},
            }},
            "fields": "userEnteredFormat(borders)",
        }})
        col = 1
        for w in range(n_weeks):
            for s in range(n_series):
                rb = peso_right(w, s)
                # Merge Rep+Peso cell to show set number centered
                requests.append({"mergeCells": {
                    "range": rng(series_row, series_row+1, col, col+2), "mergeType": "MERGE_ALL"
                }})
                requests.append({"repeatCell": {
                    "range": rng(series_row, series_row+1, col, col+2),
                    "cell": {"userEnteredFormat": {
                        "backgroundColor": GREEN_BG,
                        "horizontalAlignment": "CENTER",
                        "borders": {"left": THIN, "right": rb},
                    }},
                    "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,borders)",
                }})
                col += 2

        # ── Rep./Peso label row ───────────────────────────────────────────────
        col = 1
        for w in range(n_weeks):
            for s in range(n_series):
                rb = peso_right(w, s)
                requests.append({"repeatCell": {
                    "range": rng(label_row, label_row+1, col, col+1),
                    "cell": {"userEnteredFormat": {
                        "backgroundColor": GRAY_BG,
                        "textFormat": {"bold": True},
                        "borders": {"left": THIN},
                    }},
                    "fields": "userEnteredFormat(backgroundColor,textFormat,borders)",
                }})
                requests.append({"repeatCell": {
                    "range": rng(label_row, label_row+1, col+1, col+2),
                    "cell": {"userEnteredFormat": {
                        "backgroundColor": GRAY_BG,
                        "textFormat": {"bold": True},
                        "borders": {"right": rb},
                    }},
                    "fields": "userEnteredFormat(backgroundColor,textFormat,borders)",
                }})
                col += 2

        # ── Exercise rows ─────────────────────────────────────────────────────
        layout = day_exercise_layout(exercises)

        # Find the index of the LAST real exercise (to put thick border at bottom)
        last_ex_layout_idx = max(i for i, (rt, _) in enumerate(layout) if rt != "blank")

        for layout_idx, (row_type, ex) in enumerate(layout):
            cur = ex_start + layout_idx
            if row_type == "blank":
                continue

            is_comb = (row_type == "comb")
            # Background for column A: yellow for combos, white for solos
            bg      = PEACH_BG if is_comb else WHITE_BG
            is_last = (layout_idx == last_ex_layout_idx)

            # Determine if this is the first exercise in its group (for top border)
            prev_non_blank = next(
                (layout[j] for j in range(layout_idx - 1, -1, -1) if layout[j][0] != "blank"),
                None,
            )
            is_first_in_group = (prev_non_blank is None) or (prev_non_blank[0] != row_type)

            # Border for the name cell (col A)
            name_borders = {"left": THICK, "right": THIN}
            if is_comb:
                if is_first_in_group:
                    name_borders["top"] = THIN
                if is_last:
                    name_borders["bottom"] = THICK
            else:
                name_borders["top"] = THIN
                if is_last:
                    name_borders["bottom"] = THICK

            # Format for cell A: background color + borders + text wrap
            requests.append({"repeatCell": {
                "range": rng(cur, cur+1, 0, 1),
                "cell": {"userEnteredFormat": {
                    "backgroundColor": bg,
                    "borders": name_borders,
                    "wrapStrategy": "WRAP",   # long text wraps to the next line
                }},
                "fields": "userEnteredFormat(backgroundColor,borders,wrapStrategy)",
            }})

            # ── Data cells (Rep + Peso for each set of each week) ──
            col = 1
            for w in range(n_weeks):
                week_bg = WEEK_COLORS[w]   # soft week color (same for solos and combos)
                for s in range(n_series):
                    rb = peso_right(w, s)

                    rep_borders  = {}
                    peso_borders = {"right": rb}

                    # Top border: on the first exercise in the group (comb or solo)
                    if is_comb and is_first_in_group:
                        rep_borders["top"]  = THIN
                        peso_borders["top"] = THIN
                    elif not is_comb:
                        rep_borders["top"]  = THIN
                        peso_borders["top"] = THIN

                    # Thick bottom border on the last exercise of the day
                    if is_last:
                        rep_borders["bottom"]  = THICK
                        peso_borders["bottom"] = THICK

                    requests.append({"repeatCell": {
                        "range": rng(cur, cur+1, col, col+1),
                        "cell": {"userEnteredFormat": {
                            "backgroundColor": week_bg, "borders": rep_borders,
                        }},
                        "fields": "userEnteredFormat(backgroundColor,borders)",
                    }})
                    requests.append({"repeatCell": {
                        "range": rng(cur, cur+1, col+1, col+2),
                        "cell": {"userEnteredFormat": {
                            "backgroundColor": week_bg, "borders": peso_borders,
                        }},
                        "fields": "userEnteredFormat(backgroundColor,borders)",
                    }})
                    col += 2

        # Advance current_row: 3 header rows + exercise rows + 2 blank rows
        current_row += 3 + len(layout) + 2

    # Send all formatting requests in a single API call
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests},
    ).execute()
    print(f"  Formatting applied ({len(requests)} requests)")


def build_sheet_values(days_data):
    """
    Builds the data grid (list of lists) to write to Google Sheets.
    Each inner list represents a row; each element, a cell.
    """
    all_rows = []

    for pos, day_num in enumerate(days_data.keys(), start=1):
        exercises = days_data[day_num]
        if not exercises:
            continue

        # "Dia N" row
        all_rows.append([f"Dia {pos}"])

        # Set numbers row
        series_row = [""]
        for _week in range(4):
            for s in range(1, 4):
                series_row.extend([s, ""])
        all_rows.append(series_row)

        # Labels row
        label_row = [""]
        for _week in range(4):
            for _s in range(3):
                label_row.extend(["Rep.", "Peso"])
        all_rows.append(label_row)

        # Exercise rows
        for row_type, ex in day_exercise_layout(exercises):
            if row_type == "blank":
                all_rows.append([])
                continue
            ex_row = [exercise_display_name(ex)]
            week_reps = ex.get("week_reps", [None, None, None, None])
            for week_idx in range(4):
                reps = week_reps[week_idx] if week_reps[week_idx] is not None else [None, None, None]
                for s in range(3):
                    ex_row.append(reps[s] if s < len(reps) else "")
                    ex_row.append("")   # Peso column (filled in manually)
            all_rows.append(ex_row)

        # Two blank rows between days
        all_rows.append([])
        all_rows.append([])

    # Replace None with "" (Sheets API does not accept None)
    return [[("" if v is None else v) for v in row] for row in all_rows]


def write_to_google_sheets(service, spreadsheet_id, tab_name, days_data, force=False):
    """
    Creates the tab in Google Sheets and writes the data with formatting.

    If the tab already exists:
        - With force=False: does nothing (avoids accidental overwrite)
        - With force=True:  deletes the existing tab and recreates it from scratch
    """
    sheets = service.spreadsheets()

    if sheets_tab_exists(service, spreadsheet_id, tab_name):
        if not force:
            print(f"  Tab '{tab_name}' already exists — doing nothing.")
            return
        # Delete existing tab
        existing_id = get_sheet_id(service, spreadsheet_id, tab_name)
        sheets.batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"deleteSheet": {"sheetId": existing_id}}]},
        ).execute()
        print(f"  Deleted existing tab '{tab_name}'")

    # Create new tab at the front (index 0)
    resp = sheets.batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": tab_name, "index": 0}}}]},
    ).execute()
    sheet_id = resp["replies"][0]["addSheet"]["properties"]["sheetId"]
    print(f"  Created new tab '{tab_name}' at position 0")

    # Write the values to the grid
    values = build_sheet_values(days_data)
    sheets.values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{tab_name}'!A1",
        valueInputOption="RAW",
        body={"values": values},
    ).execute()
    print(f"  Written {len(values)} rows to '{tab_name}'")

    # Apply visual formatting
    apply_sheet_formatting(service, spreadsheet_id, sheet_id, days_data)
