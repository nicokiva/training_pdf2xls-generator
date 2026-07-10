#!/usr/bin/env python3
"""
pdf_to_xlsx.py — Script entry point.

Reads a training routine PDF and writes the data to Google Sheets and a local
.xlsx file.

Usage:
    python3 pdf_to_xlsx.py <pdf.pdf> --sheets-id XXXX --credentials creds.json [--force]

Project structure:
    pdf_to_xlsx.py       ← this file (CLI only)
    helpers/
        pdf_parser.py    ← data extraction from PDF
        exercise.py      ← exercise utilities (name, layout, tab name)
        sheets.py        ← writing and formatting in Google Sheets
"""

import sys
from pathlib import Path

from helpers.pdf_parser import parse_pdf
from helpers.exercise   import make_tab_name, exercise_display_name
from helpers.sheets     import get_sheets_service, write_to_google_sheets
from helpers.xlsx       import write_xlsx_tab
from helpers.events     import publish_event
from training_shared.events import EventType
from helpers.exercise_normalizer import normalize_exercises


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Parse a training PDF and write it to Google Sheets."
    )
    parser.add_argument("pdf", help="Path to the PDF file")
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
        "--force",
        action="store_true",
        help="Delete and recreate the tab if it already exists",
    )
    parser.add_argument(
        "--no-xlsx",
        action="store_true",
        help="Skip writing the local .xlsx file",
    )
    args = parser.parse_args()

    print(f"Parsing PDF: {args.pdf}")
    data = parse_pdf(args.pdf)

    # Normalize exercise names using the shared mapping
    for exercises in data["days"].values():
        normalize_exercises(exercises)

    # Display a summary of what was parsed
    print(f"  Validity: {data['vigencia_start']} - {data['vigencia_end']}")
    for day_num, exercises in sorted(data["days"].items()):
        print(f"  Day {day_num}: {len(exercises)} exercises")
        for ex in exercises:
            print(f"    #{ex['number']} {exercise_display_name(ex)} | weeks: {ex.get('week_reps')}")

    tab_name = make_tab_name(data["vigencia_start"], data["vigencia_end"])
    print(f"\nTab name: {tab_name}")

    if not args.no_xlsx:
        import openpyxl

        out_path = Path(args.pdf).with_suffix(".xlsx")
        wb = openpyxl.Workbook()
        write_xlsx_tab(wb, tab_name, data["days"])
        wb.save(out_path)
        print(f"\nSaved local .xlsx file: {out_path}")

    if not args.sheets_id:
        print("\nTip: use --sheets-id and --credentials to sync to Google Sheets.")
        return

    if not args.credentials:
        print("\nError: --credentials is required when using --sheets-id")
        sys.exit(1)

    service = get_sheets_service(args.credentials)

    # Upload the new routine as NextMonday-...
    # The old active tab is NOT closed here — routine-analyzer handles that
    # daily via try_close_completed_periods() once it detects two open tabs.
    # force=True because processing a new PDF always means creating a fresh tab.
    print(f"\nUpdating Google Sheets: {args.sheets_id}")
    write_to_google_sheets(service, args.sheets_id, tab_name, data["days"], force=True)
    print(f"  Done! https://docs.google.com/spreadsheets/d/{args.sheets_id}")

    print("\nPublishing routine:uploaded event...")
    publish_event(EventType.ROUTINE_UPLOADED)


# This block only runs when you execute the script directly with python3.
# If another file imports this module, this block does NOT run.
if __name__ == "__main__":
    main()
