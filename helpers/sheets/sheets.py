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


def find_active_tab(service, spreadsheet_id):
    """
    Returns the name of the currently active tab — the one whose name matches
    DD/MM/YY-... (end date not set, routine still running).

    Tabs prefixed with 'ORIG' are intentionally excluded: they are preserved
    copies of a routine that should never be renamed or closed automatically.

    Returns None if no active tab is found.
    """
    import re
    # Matches e.g. "18/05/26-..." but NOT "ORIG18/05/26-..."
    pattern = re.compile(r"^\d{2}/\d{2}/\d{2}-\.\.\.$")
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for s in meta["sheets"]:
        title = s["properties"]["title"]
        if pattern.match(title):
            return title
    return None


def rename_tab(service, spreadsheet_id, old_name, new_name):
    """
    Renames a tab via the batchUpdate API.
    Used to close the active tab by replacing '-...' with '-NextFriday'.

    Args:
        old_name: Current tab title, e.g. '18/05/26-...'
        new_name: New tab title, e.g. '18/05/26-23/05/26'
    """
    sheet_id = get_sheet_id(service, spreadsheet_id, old_name)
    # updateSheetProperties lets us change any tab property, including its title.
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{
            "updateSheetProperties": {
                "properties": {"sheetId": sheet_id, "title": new_name},
                "fields": "title",
            }
        }]}
    ).execute()
    print(f"  Renamed tab: '{old_name}' → '{new_name}'")


def apply_sheet_formatting(service, spreadsheet_id, sheet_id, days_data, n_weeks=4, n_series=4):
    """
    Applies all visual formatting to the tab: borders, background colors, merged cells,
    column widths and frozen column.

    The Google Sheets API works with "requests" (change requests) that are
    accumulated in a list and sent all at once in a single batchUpdate call.
    This is more efficient than making one call per change.

    Combined exercises need special handling: adjacent "comb" rows may still
    belong to different Comb groups, so borders and merged pause cells must
    respect the ``comb_group`` IDs assigned by the PDF parser.
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

    # Total columns: 1 (name) + 4 weeks × 4 sets × 2 (Rep+Peso) = 33
    # Pausa is the trailing rest-time column after the data block.
    n_data_cols = n_weeks * n_series * 2
    total_cols  = 1 + n_data_cols   # = 33, used as the start index of Pausa
    pausa_col   = total_cols        # = 33 (0-based)

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
                      "startIndex": 1, "endIndex": 33},
            "properties": {"pixelSize": 45},
            "fields": "pixelSize",
        }},
        # Pausa: wider to fit rest-time text
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                      "startIndex": pausa_col, "endIndex": pausa_col + 1},
            "properties": {"pixelSize": 70},
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
        # Cells B:Pausa merged + thick borders (includes pausa column)
        requests.append({"mergeCells": {
            "range": rng(dia_row, dia_row+1, 1, pausa_col+1), "mergeType": "MERGE_ALL"
        }})
        requests.append({"repeatCell": {
            "range": rng(dia_row, dia_row+1, 1, pausa_col+1),
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
                        "backgroundColorStyle": {"rgbColor": GREEN_BG},
                        "horizontalAlignment": "CENTER",
                        "borders": {"left": THIN, "right": rb},
                    }},
                    "fields": "userEnteredFormat(backgroundColorStyle,horizontalAlignment,borders)",
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
                        "backgroundColorStyle": {"rgbColor": GRAY_BG},
                        "textFormat": {"bold": True},
                        "borders": {"left": THIN},
                    }},
                    "fields": "userEnteredFormat(backgroundColorStyle,textFormat,borders)",
                }})
                requests.append({"repeatCell": {
                    "range": rng(label_row, label_row+1, col+1, col+2),
                    "cell": {"userEnteredFormat": {
                        "backgroundColorStyle": {"rgbColor": GRAY_BG},
                        "textFormat": {"bold": True},
                        "borders": {"right": rb},
                    }},
                    "fields": "userEnteredFormat(backgroundColorStyle,textFormat,borders)",
                }})
                col += 2

        # ── Pausa header (spans series+label rows, same height as col A) ──
        requests.append({"mergeCells": {
            "range": rng(series_row, label_row+1, pausa_col, pausa_col+1),
            "mergeType": "MERGE_ALL",
        }})
        requests.append({"repeatCell": {
            "range": rng(series_row, label_row+1, pausa_col, pausa_col+1),
            "cell": {"userEnteredFormat": {
                "backgroundColorStyle": {"rgbColor": GREEN_BG},
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE",
                "textFormat": {"bold": True},
                "borders": {"left": THICK, "right": THICK, "top": THIN, "bottom": THIN},
            }},
            "fields": "userEnteredFormat(backgroundColorStyle,horizontalAlignment,verticalAlignment,textFormat,borders)",
        }})

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

            # Determine whether this row starts a new visual block.
            # For solos, a row starts a block whenever the previous non-blank row
            # is absent or has a different row type. For combined exercises, the
            # same rule is not enough: two adjacent comb rows may belong to two
            # distinct Comb groups, so a comb_group boundary must restart borders.
            prev_non_blank = next(
                (layout[j] for j in range(layout_idx - 1, -1, -1) if layout[j][0] != "blank"),
                None,
            )
            is_first_in_group = (prev_non_blank is None) or (prev_non_blank[0] != row_type)
            if not is_first_in_group and is_comb and prev_non_blank is not None:
                # Adjacent combs from different parser groups must not visually
                # collapse into one larger block.
                if prev_non_blank[1].get("comb_group") != ex.get("comb_group"):
                    is_first_in_group = True

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
                    "backgroundColorStyle": {"rgbColor": bg},
                    "borders": name_borders,
                    "wrapStrategy": "WRAP",   # long text wraps to the next line
                }},
                "fields": "userEnteredFormat(backgroundColorStyle,borders,wrapStrategy)",
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
                            "backgroundColorStyle": {"rgbColor": week_bg}, "borders": rep_borders,
                        }},
                        "fields": "userEnteredFormat(backgroundColorStyle,borders)",
                    }})
                    requests.append({"repeatCell": {
                        "range": rng(cur, cur+1, col+1, col+2),
                        "cell": {"userEnteredFormat": {
                            "backgroundColorStyle": {"rgbColor": week_bg}, "borders": peso_borders,
                        }},
                        "fields": "userEnteredFormat(backgroundColorStyle,borders)",
                    }})
                    col += 2

        # ── Pausa cells ──────────────────────────────────────────────────────
        # Individual exercises: one cell per row.
        # Combined groups: merge all Z cells in the same comb_group into one,
        # because the suggested rest applies after the full combined block, not
        # between exercises inside that block.
        z_idx = 0
        while z_idx < len(layout):
            row_type, _ = layout[z_idx]
            if row_type == "comb":
                # Collect only the current consecutive comb_group. This extra
                # boundary check prevents back-to-back Comb groups from sharing
                # one merged Z cell just because both rows are typed as "comb".
                group_start      = z_idx
                first_comb_group = layout[z_idx][1].get("comb_group")
                while (z_idx < len(layout)
                       and layout[z_idx][0] == "comb"
                       and layout[z_idx][1].get("comb_group") == first_comb_group):
                    z_idx += 1
                group_end    = z_idx - 1
                abs_start    = ex_start + group_start
                abs_end      = ex_start + group_end
                is_last_item = (group_end == last_ex_layout_idx)

                requests.append({"mergeCells": {
                    "range": rng(abs_start, abs_end+1, pausa_col, pausa_col+1),
                    "mergeType": "MERGE_ALL",
                }})
                z_borders = {"left": THICK, "right": THICK, "top": THIN}
                if is_last_item:
                    z_borders["bottom"] = THICK
                requests.append({"repeatCell": {
                    "range": rng(abs_start, abs_end+1, pausa_col, pausa_col+1),
                    "cell": {"userEnteredFormat": {
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "borders": z_borders,
                    }},
                    "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment,borders)",
                }})
            else:
                abs_row      = ex_start + z_idx
                is_last_item = (z_idx == last_ex_layout_idx)
                z_borders    = {"left": THICK, "right": THICK, "top": THIN}
                if is_last_item:
                    z_borders["bottom"] = THICK
                requests.append({"repeatCell": {
                    "range": rng(abs_row, abs_row+1, pausa_col, pausa_col+1),
                    "cell": {"userEnteredFormat": {
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "borders": z_borders,
                    }},
                    "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment,borders)",
                }})
                z_idx += 1

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

    The row order mirrors day_exercise_layout() so the values grid and the
    formatting pass operate on the same row structure.
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
            for s in range(1, 5):
                series_row.extend([s, ""])
        series_row.append("Pausa")
        all_rows.append(series_row)

        # Labels row
        label_row = [""]
        for _week in range(4):
            for _s in range(4):
                label_row.extend(["Rep.", "Peso"])
        label_row.append("")
        all_rows.append(label_row)

        # Exercise rows
        for row_type, ex in day_exercise_layout(exercises):
            if row_type == "blank":
                all_rows.append([])
                continue
            ex_row = [("[C] " if row_type == "comb" else "") + exercise_display_name(ex)]
            week_reps = ex.get("week_reps", [None, None, None, None])
            for week_idx in range(4):
                reps = week_reps[week_idx] if week_reps[week_idx] is not None else [None, None, None, None]
                for s in range(4):
                    ex_row.append(reps[s] if s < len(reps) else "")
                    ex_row.append("")   # Peso column (filled in manually)
            ex_row.append("")            # Pausa (filled by writer with suggested rest)
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

    Recreating the tab is simpler than trying to diff old formatting, merged
    cells and values against the new routine structure.
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
