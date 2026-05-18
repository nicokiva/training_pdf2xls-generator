#!/usr/bin/env python3
"""
pdf_to_xlsx.py - Parse a training PDF and create/update a tab in the XLSX workbook.

Usage:
    python3 pdf_to_xlsx.py <pdf_path> [xlsx_path]

If xlsx_path is omitted, defaults to "Rutinas entrenamiento.xlsx" in the same directory as the PDF.
"""

import sys
import re
import os
from pathlib import Path

import pdfplumber
import openpyxl


# X-coordinate threshold separating left and right exercise columns
COL_SPLIT_X = 290

# X positions where exercise numbers appear (left and right columns)
LEFT_EX_NUM_X_RANGE = (55, 80)
RIGHT_EX_NUM_X_RANGE = (345, 370)

# Minimum y-position to skip the header block
HEADER_BOTTOM_Y = 230


def group_lines(words, y_tolerance=4):
    """Group words into lines based on proximity of their top y-coordinate."""
    if not words:
        return []
    words = sorted(words, key=lambda w: (round(w["top"] / y_tolerance) * y_tolerance, w["x0"]))
    lines = []
    current_line = [words[0]]
    for word in words[1:]:
        if abs(word["top"] - current_line[0]["top"]) <= y_tolerance:
            current_line.append(word)
        else:
            lines.append(sorted(current_line, key=lambda w: w["x0"]))
            current_line = [word]
    lines.append(sorted(current_line, key=lambda w: w["x0"]))
    return lines


def line_text(line):
    return " ".join(w["text"] for w in line)


def parse_reps(text):
    """Extract the first integer rep count from a line like '2da 6' or '3ra 4 con mas peso'."""
    m = re.search(r"\d+", text)
    return int(m.group()) if m else None


def is_exercise_number(word, col):
    """Return True if word looks like an exercise number in the given column ('left'/'right')."""
    if not word["text"].isdigit():
        return False
    num = int(word["text"])
    if not (1 <= num <= 20):
        return False
    x0 = word["x0"]
    if col == "left":
        return LEFT_EX_NUM_X_RANGE[0] <= x0 <= LEFT_EX_NUM_X_RANGE[1]
    else:
        return RIGHT_EX_NUM_X_RANGE[0] <= x0 <= RIGHT_EX_NUM_X_RANGE[1]


def parse_column(all_words, x_min, x_max, col_side, header_bottom_y=HEADER_BOTTOM_Y):
    """
    Parse exercises from one horizontal column of a PDF page.
    Returns a list of dicts: {number, name, is_comb, week_reps}
    week_reps[0] = week 1 series [s1, s2, s3], etc.
    """
    words = [w for w in all_words if x_min <= w["x0"] < x_max and w["top"] > header_bottom_y]
    if not words:
        return [], []

    lines = group_lines(words)

    exercises = []
    current_ex = None
    pending_name_parts = []  # name text seen before the exercise number
    week_reps = [None, None, None, None]  # 4 weeks
    comb_count = 0        # how many exercises belong to the current Comb group
    comb_assigned = 0     # how many have been assigned so far
    comb_groups = []      # [(first_ex_number, count), ...] — for cross-column re-application
    current_comb_start = None  # exercise number of first exercise in current comb group

    def save_exercise():
        nonlocal current_ex, pending_name_parts, week_reps
        if current_ex is not None:
            current_ex["week_reps"] = week_reps
            exercises.append(current_ex)
        current_ex = None
        pending_name_parts = []
        week_reps = [None, None, None, None]

    for line in lines:
        txt = line_text(line)

        # Skip "Series 1 2 3", "kg ..."
        if re.match(r"^Series\s+\d", txt) or re.match(r"^kg\b", txt):
            continue

        # Detect "Comb xN" — record how many exercises are combined
        m_comb = re.match(r"^Comb\s+x(\d+)", txt, re.IGNORECASE)
        if m_comb:
            comb_count = int(m_comb.group(1))
            comb_assigned = 0
            current_comb_start = None
            continue

        # Detect "repeticiones X X X" → week 1 reps
        m = re.match(r"^repeticiones\s+(\d+)\s+(\d+)\s+(\d+)", txt)
        if m and current_ex is not None:
            week_reps[0] = [int(m.group(1)), int(m.group(2)), int(m.group(3))]
            continue

        # Detect weekly progression: "2da X", "3ra X", "4ta X"
        # Use re.search to handle lines like "MANOS ATRAS DE LA NUCA 2da 6"
        # or "2da 8 CADA PIERNA" where a comment is mixed into the progression line.
        m2 = re.search(r"(2da|3ra|4ta)\s+(\d+)", txt)
        if m2 and current_ex is not None:
            week_idx = {"2da": 1, "3ra": 2, "4ta": 3}[m2.group(1)]
            rep = int(m2.group(2))
            if week_reps[0] is not None:
                week_reps[week_idx] = [rep, rep, rep]
            # Extract any comment text before or after the progression token
            before = txt[:m2.start()].strip()
            after  = txt[m2.end():].strip()
            # Ignore weight-only hints like "con mas peso"
            after = re.sub(r"con\s+mas\s+peso.*", "", after, flags=re.IGNORECASE).strip()
            comment = (before or after).strip()
            if comment and not re.match(r"^[\d\s]+$", comment):
                current_ex.setdefault("comment", comment)
            continue

        # Check if this line has an exercise number
        ex_num_word = next((w for w in line if is_exercise_number(w, col_side)), None)

        if ex_num_word is not None:
            # Capture pending name BEFORE saving (save_exercise clears it)
            name_from_above = " ".join(pending_name_parts).strip()

            # Save previous exercise if any
            save_exercise()

            num = int(ex_num_word["text"])
            # Name = words on same line after the number, plus any pending_name_parts
            name_words = [w["text"] for w in line if w["x0"] > ex_num_word["x0"]]
            name_inline = " ".join(name_words).strip()

            # Combine: prefer inline name, fall back to above, or combine both
            if name_inline and name_from_above:
                name = name_from_above + " " + name_inline
            elif name_inline:
                name = name_inline
            else:
                name = name_from_above

            current_ex = {"number": num, "name": name.strip(), "is_comb": False}
            if comb_count > 0 and comb_assigned < comb_count:
                current_ex["is_comb"] = True
                if current_comb_start is None:
                    # Record the start of this comb group for cross-column re-application
                    current_comb_start = num
                    comb_groups.append([num, comb_count])
                comb_assigned += 1
                if comb_assigned >= comb_count:
                    comb_count = 0
                    comb_assigned = 0
                    current_comb_start = None
            pending_name_parts = []
            week_reps = [None, None, None, None]
            continue

        # If no exercise number on this line, check if it might be a name fragment
        # (a) Name appearing BEFORE the exercise number (like exercises 4,5)
        # (b) Name continuation AFTER the exercise number but before "repeticiones"
        if txt and not re.match(r"^[\d\s]+$", txt):
            skip_patterns = r"^(repeticiones|Series|kg|2da|3ra|4ta|\d+(\.\d+)?[\s\|]*)+$"
            if not re.match(skip_patterns, txt):
                all_weeks_done = all(week_reps[i] is not None for i in range(4))
                if current_ex is None or all_weeks_done:
                    # Buffer as potential name for the NEXT exercise
                    pending_name_parts.append(txt)
                elif week_reps[0] is None:
                    # Name continuation before we've seen "repeticiones"
                    current_ex["name"] = (current_ex["name"] + " " + txt).strip()
                else:
                    # Text appearing after "repeticiones" but not a week progression → comment
                    current_ex.setdefault("comment", txt)

    # Save last exercise
    save_exercise()
    return exercises, comb_groups


def parse_pdf(pdf_path):
    """
    Parse the PDF and return structured data.
    Returns: {
        'vigencia_start': 'DD/MM/YYYY',
        'vigencia_end': 'DD/MM/YYYY',
        'days': {1: [...exercises...], 2: [...], 3: [...], 4: [...]}
    }
    The first Comb group found in PDF page order (the universal ab section) is
    automatically prepended to every day that doesn't already start with it.
    """
    result = {"vigencia_start": None, "vigencia_end": None, "days": {}}
    first_pdf_day = None   # day number of the first page encountered in PDF order

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            text = page.extract_text() or ""

            # Extract vigencia from the first page
            if result["vigencia_start"] is None:
                m = re.search(r"Vigencia:\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})", text)
                if m:
                    result["vigencia_start"] = m.group(1)
                    result["vigencia_end"] = m.group(2)

            # Detect day number: standalone digit centered around x=294, top≈218
            day_num = None
            for w in words:
                if (w["text"].isdigit() and 1 <= int(w["text"]) <= 10
                        and 280 < w["x0"] < 310 and 210 < w["top"] < 235):
                    day_num = int(w["text"])
                    break

            if day_num is None:
                # This is a continuation page (no day header) — attach to the last day
                if result["days"]:
                    last_day = max(result["days"].keys())
                    day_num = last_day
                else:
                    continue
                effective_header_bottom = 50  # continuation pages start near the top
            else:
                effective_header_bottom = HEADER_BOTTOM_Y
                if first_pdf_day is None:
                    first_pdf_day = day_num

            # Parse left and right columns
            left_ex, left_comb_groups = parse_column(words, 0, COL_SPLIT_X, "left", effective_header_bottom)
            right_ex, right_comb_groups = parse_column(words, COL_SPLIT_X, 9999, "right", effective_header_bottom)

            # Merge by exercise number ordering
            all_ex = sorted(left_ex + right_ex, key=lambda e: e["number"])

            # Re-apply combo membership globally to fix cross-column detection.
            # parse_column marks exercises within its own column, so if a Comb group
            # spans both columns (e.g. exercises 1,2,3 with 2 in the right column),
            # the right-column exercises are missed. Re-applying here uses the start
            # number and count from whichever column saw the Comb header, then marks
            # the correct consecutive exercises globally.
            all_comb_groups = left_comb_groups + right_comb_groups
            if all_comb_groups:
                for ex in all_ex:
                    ex["is_comb"] = False
                all_numbers = [ex["number"] for ex in all_ex]
                for start_num, count in all_comb_groups:
                    if start_num not in all_numbers:
                        continue
                    start_idx = all_numbers.index(start_num)
                    for i in range(start_idx, min(start_idx + count, len(all_ex))):
                        all_ex[i]["is_comb"] = True

            if day_num not in result["days"]:
                result["days"][day_num] = []
            # Append (continuation pages add more exercises)
            result["days"][day_num].extend(all_ex)

    # ── Propagate universal ab comb to all days ────────────────────────────
    # The first Comb group found in PDF page order (abs section) goes in every day.
    if first_pdf_day and first_pdf_day in result["days"]:
        universal_comb = [ex for ex in result["days"][first_pdf_day] if ex.get("is_comb")]
        if universal_comb:
            for day_num, exercises in result["days"].items():
                if day_num == first_pdf_day:
                    continue  # already has them
                if not exercises or not exercises[0].get("is_comb"):
                    # Prepend a fresh copy (so each day has independent dicts)
                    prepend = [dict(ex) for ex in universal_comb]
                    result["days"][day_num] = prepend + exercises

    return result


def make_tab_name(_vigencia_start=None, _vigencia_end=None):
    """Generate tab name like '19/05/26-...' using the next Monday from today."""
    from datetime import date, timedelta
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7 or 7  # 0=Mon; if today is Mon, go to next Mon
    next_monday = today + timedelta(days=days_until_monday)
    return next_monday.strftime("%d/%m/%y") + "-..."


def exercise_display_name(ex):
    """Return the exercise name, appending any comment in parentheses."""
    name = ex["name"]
    comment = ex.get("comment", "").strip()
    return f"{name} ({comment.lower()})" if comment else name


def day_exercise_layout(exercises):
    """
    Returns a list of (row_type, exercise) pairs for a day's exercise block:
      ('comb', ex)  — combined exercise (peach background, no separator between comb rows)
      ('solo', ex)  — standalone exercise (white background, bordered box)
    No blank rows are inserted; visual separation comes from borders.
    """
    return [("comb" if ex.get("is_comb") else "solo", ex) for ex in exercises]


def write_xlsx_tab(wb, tab_name, days_data):
    """
    Create or overwrite a tab in the workbook with the training data.
    Structure mirrors existing tabs: rows per exercise with Rep/Peso pairs
    for 4 weeks × 3 series = 12 column pairs.
    Comb exercises have no blank rows between them; solo exercises are separated by a blank row.
    """
    # XLSX sheet names can't contain /
    xlsx_tab_name = tab_name.replace("/", "-")
    if xlsx_tab_name in wb.sheetnames:
        del wb[xlsx_tab_name]
    ws = wb.create_sheet(xlsx_tab_name, 0)

    row = 1
    for pos, day_num in enumerate(days_data.keys(), start=1):
        exercises = days_data[day_num]
        if not exercises:
            continue

        ws.cell(row=row, column=1, value=f"Dia {pos}")
        row += 1

        series_row = [None]
        for _week in range(4):
            for s in range(1, 4):
                series_row.extend([s, None])
        for col_idx, val in enumerate(series_row, start=1):
            ws.cell(row=row, column=col_idx, value=val)
        row += 1

        label_row = [None]
        for _week in range(4):
            for _s in range(3):
                label_row.extend(["Rep.", "Peso"])
        for col_idx, val in enumerate(label_row, start=1):
            ws.cell(row=row, column=col_idx, value=val)
        row += 1

        for row_type, ex in day_exercise_layout(exercises):
            if row_type == "blank":
                row += 1
                continue
            ex_row = [exercise_display_name(ex)]
            week_reps = ex.get("week_reps", [None, None, None, None])
            for week_idx in range(4):
                reps = week_reps[week_idx] if week_reps[week_idx] is not None else [None, None, None]
                for s in range(3):
                    ex_row.append(reps[s] if s < len(reps) else None)
                    ex_row.append(None)  # Peso — left blank
            for col_idx, val in enumerate(ex_row, start=1):
                ws.cell(row=row, column=col_idx, value=val)
            row += 1

        row += 2  # two blank rows between days

    return ws


# ---------------------------------------------------------------------------
# Google Sheets integration
# ---------------------------------------------------------------------------

SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_sheets_service(credentials_path):
    """Build and return an authenticated Google Sheets API service."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        credentials_path, scopes=SHEETS_SCOPES
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def sheets_tab_exists(service, spreadsheet_id, tab_name):
    """Return True if a sheet with tab_name already exists in the spreadsheet."""
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    return any(s["properties"]["title"] == tab_name for s in meta["sheets"])


def get_sheet_id(service, spreadsheet_id, tab_name):
    """Return the sheetId (integer) for the given tab name."""
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == tab_name:
            return s["properties"]["sheetId"]
    raise ValueError(f"Tab '{tab_name}' not found")


def apply_sheet_formatting(service, spreadsheet_id, sheet_id, days_data, n_weeks=4, n_series=3):
    """Apply formatting to match existing tabs: borders, colors, merges."""
    THICK   = {"style": "SOLID_THICK", "colorStyle": {"rgbColor": {}}}
    THIN    = {"style": "SOLID",       "colorStyle": {"rgbColor": {}}}
    NO_BORDER = {"style": "NONE"}

    GREEN_BG = {"red": 0.851, "green": 0.918, "blue": 0.827}   # series number row
    GRAY_BG  = {"red": 0.941, "green": 0.941, "blue": 0.941}   # Rep./Peso label row
    PEACH_BG = {"red": 1.0,   "green": 0.949, "blue": 0.8}     # Comb exercises (name col)
    WHITE_BG = {"red": 1.0,   "green": 1.0,   "blue": 1.0}

    # Per-week subtle tints for data cells
    WEEK_COLORS = [
        {"red": 0.94, "green": 0.99, "blue": 0.94},  # semana 1: verde muy suave
        {"red": 0.93, "green": 0.96, "blue": 1.0},   # semana 2: azul muy suave
        {"red": 0.97, "green": 0.94, "blue": 1.0},   # semana 3: lavanda muy suave
        {"red": 1.0,  "green": 0.94, "blue": 0.93},  # semana 4: salmón muy suave
    ]

    def blend(c1, c2, t=0.5):
        """Blend two RGB dicts: t=0 → c1, t=1 → c2."""
        return {k: round(c1[k] * (1 - t) + c2[k] * t, 4) for k in ("red", "green", "blue")}

    n_data_cols = n_weeks * n_series * 2   # 24
    total_cols  = 1 + n_data_cols          # 25  (A … Y)

    def rng(r0, r1, c0, c1):
        return {"sheetId": sheet_id, "startRowIndex": r0, "endRowIndex": r1,
                "startColumnIndex": c0, "endColumnIndex": c1}

    def peso_right(w, s):
        """Right border style for a Peso cell: THICK at week boundary, THIN otherwise."""
        return THICK if s == n_series - 1 else THIN

    requests = [
        # Fix the exercise name column (col A) to 180px
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                      "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 180},
            "fields": "pixelSize",
        }},
        # Freeze column A so it stays visible when scrolling horizontally
        {"updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": {"frozenColumnCount": 1}},
            "fields": "gridProperties.frozenColumnCount",
        }},
        # Set data columns (B onwards) to a compact but readable width
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                      "startIndex": 1, "endIndex": 25},
            "properties": {"pixelSize": 45},
            "fields": "pixelSize",
        }},
    ]
    current_row = 0  # 0-indexed

    for day_num in days_data.keys():
        exercises = days_data[day_num]
        if not exercises:
            continue

        n_ex = len(exercises)
        dia_row    = current_row
        series_row = current_row + 1
        label_row  = current_row + 2
        ex_start   = current_row + 3

        # ── "Dia N" header ────────────────────────────────────────────────
        # A: bold + THICK borders top/bottom/left
        requests.append({"repeatCell": {
            "range": rng(dia_row, dia_row+1, 0, 1),
            "cell": {"userEnteredFormat": {
                "textFormat": {"bold": True},
                "borders": {"top": THICK, "bottom": THICK, "left": THICK, "right": NO_BORDER},
            }},
            "fields": "userEnteredFormat(textFormat,borders)",
        }})
        # B:Y merged + THICK borders top/bottom/right
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

        # ── Series number row ─────────────────────────────────────────────
        # A merged with label row (rows series_row .. label_row+1)
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
                # Merge Rep+Peso for this series number
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

        # ── Rep./Peso label row ───────────────────────────────────────────
        col = 1
        for w in range(n_weeks):
            for s in range(n_series):
                rb = peso_right(w, s)
                # Rep cell
                requests.append({"repeatCell": {
                    "range": rng(label_row, label_row+1, col, col+1),
                    "cell": {"userEnteredFormat": {
                        "backgroundColor": GRAY_BG,
                        "textFormat": {"bold": True},
                        "borders": {"left": THIN},
                    }},
                    "fields": "userEnteredFormat(backgroundColor,textFormat,borders)",
                }})
                # Peso cell
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

        # ── Exercise rows ─────────────────────────────────────────────────
        layout = day_exercise_layout(exercises)
        # Find last actual exercise (not blank) for thick bottom border
        last_ex_layout_idx = max(i for i, (rt, _) in enumerate(layout) if rt != "blank")

        for layout_idx, (row_type, ex) in enumerate(layout):
            cur = ex_start + layout_idx
            if row_type == "blank":
                continue  # blank row — no formatting needed

            is_comb = (row_type == "comb")
            bg      = PEACH_BG if is_comb else WHITE_BG
            is_last = (layout_idx == last_ex_layout_idx)

            # First in its color group = no previous non-blank entry of same type immediately before
            prev_non_blank = next(
                (layout[j] for j in range(layout_idx - 1, -1, -1) if layout[j][0] != "blank"),
                None,
            )
            is_first_in_group = (prev_non_blank is None) or (prev_non_blank[0] != row_type)

            # ── Name cell (col A) ──
            # Comb: top border on first of group, bottom border on last of day.
            # Solo: top+bottom THIN border on every row (forms a clean box per exercise),
            #       last exercise of the day gets THICK bottom.
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

            requests.append({"repeatCell": {
                "range": rng(cur, cur+1, 0, 1),
                "cell": {"userEnteredFormat": {
                    "backgroundColor": bg,
                    "borders": name_borders,
                    "wrapStrategy": "WRAP",
                }},
                "fields": "userEnteredFormat(backgroundColor,borders,wrapStrategy)",
            }})

            # ── Data cells (Rep + Peso pairs) ──
            col = 1
            for w in range(n_weeks):
                week_bg = WEEK_COLORS[w]
                for s in range(n_series):
                    rb = peso_right(w, s)

                    rep_borders  = {}
                    peso_borders = {"right": rb}
                    if is_comb and is_first_in_group:
                        rep_borders["top"]  = THIN
                        peso_borders["top"] = THIN
                    elif not is_comb:
                        rep_borders["top"]  = THIN
                        peso_borders["top"] = THIN
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

        current_row += 3 + len(layout) + 2  # header(3) + layout rows + 2 blank rows

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests},
    ).execute()
    print(f"  Formatting applied ({len(requests)} requests)")


def build_sheet_values(days_data):
    """Build a list-of-lists for the Sheets API. Blank rows separate solo exercises."""
    all_rows = []

    for pos, day_num in enumerate(days_data.keys(), start=1):
        exercises = days_data[day_num]
        if not exercises:
            continue

        all_rows.append([f"Dia {pos}"])

        series_row = [""]
        for _week in range(4):
            for s in range(1, 4):
                series_row.extend([s, ""])
        all_rows.append(series_row)

        label_row = [""]
        for _week in range(4):
            for _s in range(3):
                label_row.extend(["Rep.", "Peso"])
        all_rows.append(label_row)

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
                    ex_row.append("")  # Peso
            all_rows.append(ex_row)

        all_rows.append([])  # day separator
        all_rows.append([])

    return [[("" if v is None else v) for v in row] for row in all_rows]


def write_to_google_sheets(service, spreadsheet_id, tab_name, days_data, force=False):
    """Create a sheet tab in Google Sheets. Skips if the tab already exists (unless force=True)."""
    sheets = service.spreadsheets()

    if sheets_tab_exists(service, spreadsheet_id, tab_name):
        if not force:
            print(f"  Tab '{tab_name}' ya existe — no se hace nada.")
            return
        # Delete existing tab before recreating
        existing_id = get_sheet_id(service, spreadsheet_id, tab_name)
        sheets.batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"deleteSheet": {"sheetId": existing_id}}]},
        ).execute()
        print(f"  Deleted existing tab '{tab_name}'")

    # Add new sheet at position 0 (front)
    resp = sheets.batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": tab_name, "index": 0}}}]},
    ).execute()
    sheet_id = resp["replies"][0]["addSheet"]["properties"]["sheetId"]
    print(f"  Created new tab '{tab_name}' at position 0")

    values = build_sheet_values(days_data)
    sheets.values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{tab_name}'!A1",
        valueInputOption="RAW",
        body={"values": values},
    ).execute()
    print(f"  Written {len(values)} rows to '{tab_name}'")

    apply_sheet_formatting(service, spreadsheet_id, sheet_id, days_data)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Parse a training PDF and write it to an XLSX and/or Google Sheets."
    )
    parser.add_argument("pdf", help="Path to the PDF file")
    parser.add_argument(
        "--xlsx",
        default=None,
        help='Path to the XLSX workbook (default: "Rutinas entrenamiento.xlsx" next to the PDF)',
    )
    parser.add_argument(
        "--sheets-id",
        default=None,
        help="Google Sheets spreadsheet ID (the long ID in the URL)",
    )
    parser.add_argument(
        "--credentials",
        default=None,
        help="Path to Google service account JSON credentials file",
    )
    parser.add_argument(
        "--no-xlsx",
        action="store_true",
        help="Skip writing to the local XLSX file",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete and recreate the tab if it already exists",
    )
    args = parser.parse_args()

    pdf_path = args.pdf
    xlsx_path = args.xlsx or str(Path(pdf_path).parent / "Rutinas entrenamiento.xlsx")

    print(f"Parsing PDF: {pdf_path}")
    data = parse_pdf(pdf_path)

    print(f"  Vigencia: {data['vigencia_start']} - {data['vigencia_end']}")
    for day_num, exercises in sorted(data["days"].items()):
        print(f"  Dia {day_num}: {len(exercises)} ejercicios")
        for ex in exercises:
            print(f"    #{ex['number']} {exercise_display_name(ex)} | semanas: {ex.get('week_reps')}")

    tab_name = make_tab_name(data["vigencia_start"], data["vigencia_end"])
    print(f"\nTab name: {tab_name}")

    # --- Write to local XLSX ---
    if not args.no_xlsx:
        print(f"\nUpdating XLSX: {xlsx_path}")
        wb = openpyxl.load_workbook(xlsx_path)
        write_xlsx_tab(wb, tab_name, data["days"])
        wb.save(xlsx_path)
        print(f"  Saved: {xlsx_path}")

    # --- Write to Google Sheets ---
    if args.sheets_id:
        if not args.credentials:
            print("\nError: --credentials is required when using --sheets-id")
            sys.exit(1)
        print(f"\nUpdating Google Sheets: {args.sheets_id}")
        service = get_sheets_service(args.credentials)
        write_to_google_sheets(service, args.sheets_id, tab_name, data["days"], force=args.force)
        print(f"  Done! https://docs.google.com/spreadsheets/d/{args.sheets_id}")

    if not args.no_xlsx and not args.sheets_id:
        print("\nTip: use --sheets-id and --credentials to also sync to Google Sheets.")


if __name__ == "__main__":
    main()
