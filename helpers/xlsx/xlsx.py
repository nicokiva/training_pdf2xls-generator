"""
helpers/xlsx.py — Writing data to the local .xlsx file.

Responsibilities:
    - Create or replace a tab in the workbook with the training data
"""

import openpyxl
from helpers.exercise import exercise_display_name, day_exercise_layout


def write_xlsx_tab(wb, tab_name, days_data):
    """
    Creates or replaces a tab in the .xlsx workbook with the training data.
    Structure: day header → set row → Rep./Peso row → exercise rows.

    Parameters:
        wb        — openpyxl workbook (the open .xlsx file)
        tab_name  — name of the tab to create (e.g. "25-05-26-...")
        days_data — dict {day: [exercises]} as returned by parse_pdf
    """
    # Sheet names in XLSX cannot contain "/"
    xlsx_tab_name = tab_name.replace("/", "-")
    if xlsx_tab_name in wb.sheetnames:
        del wb[xlsx_tab_name]   # delete if already exists
    ws = wb.create_sheet(xlsx_tab_name, 0)   # 0 = insert at the front

    row = 1
    for pos, day_num in enumerate(days_data.keys(), start=1):
        exercises = days_data[day_num]
        if not exercises:
            continue

        # "Dia N" row — use position (pos) not the PDF number
        ws.cell(row=row, column=1, value=f"Dia {pos}")
        row += 1

        # Set numbers row: [None, 1, None, 2, None, 3, None, ...] (4 weeks × 3 sets)
        series_row = [None]
        for _week in range(4):
            for s in range(1, 4):
                series_row.extend([s, None])   # s = set number, None = empty Peso col
        for col_idx, val in enumerate(series_row, start=1):
            ws.cell(row=row, column=col_idx, value=val)
        row += 1

        # Rep./Peso labels row
        label_row = [None]
        for _week in range(4):
            for _s in range(3):
                label_row.extend(["Rep.", "Peso"])
        for col_idx, val in enumerate(label_row, start=1):
            ws.cell(row=row, column=col_idx, value=val)
        row += 1

        # One row per exercise
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
                    ex_row.append(None)   # Peso column (filled in manually)
            for col_idx, val in enumerate(ex_row, start=1):
                ws.cell(row=row, column=col_idx, value=val)
            row += 1

        row += 2   # two blank rows between days

    return ws
