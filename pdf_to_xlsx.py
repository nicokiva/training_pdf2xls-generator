#!/usr/bin/env python3
"""
pdf_to_xlsx.py — Script entry point.

Reads a training routine PDF and writes the data to Google Sheets.

Usage:
    python3 pdf_to_xlsx.py <pdf.pdf> --sheets-id XXXX --credentials creds.json [--force] [--no-xlsx]

Project structure:
    pdf_to_xlsx.py       ← this file (CLI only)
    helpers/
        pdf_parser.py    ← data extraction from PDF
        exercise.py      ← exercise utilities (name, layout, tab name)
        sheets.py        ← writing and formatting in Google Sheets
        xlsx.py          ← writing to local .xlsx file
"""

import subprocess
import sys
from pathlib import Path

import openpyxl

from helpers.pdf_parser import parse_pdf
from helpers.exercise   import make_tab_name, exercise_display_name
from helpers.sheets     import get_sheets_service, write_to_google_sheets
from helpers.xlsx       import write_xlsx_tab


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Parse a training PDF and write it to Google Sheets."
    )
    parser.add_argument("pdf", help="Path to the PDF file")
    parser.add_argument(
        "--xlsx",
        default=None,
        help='Path to the XLSX workbook (default: "Training Routines.xlsx" next to the PDF)',
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

    pdf_path  = args.pdf
    xlsx_path = args.xlsx or str(Path(pdf_path).parent / "Training Routines.xlsx")

    print(f"Parsing PDF: {pdf_path}")
    data = parse_pdf(pdf_path)

    # Display a summary of what was parsed
    print(f"  Validity: {data['vigencia_start']} - {data['vigencia_end']}")
    for day_num, exercises in sorted(data["days"].items()):
        print(f"  Day {day_num}: {len(exercises)} exercises")
        for ex in exercises:
            print(f"    #{ex['number']} {exercise_display_name(ex)} | weeks: {ex.get('week_reps')}")

    tab_name = make_tab_name(data["vigencia_start"], data["vigencia_end"])
    print(f"\nTab name: {tab_name}")

    # Write to local XLSX file (unless --no-xlsx was passed)
    if not args.no_xlsx:
        print(f"\nUpdating XLSX: {xlsx_path}")
        wb = openpyxl.load_workbook(xlsx_path)
        write_xlsx_tab(wb, tab_name, data["days"])
        wb.save(xlsx_path)
        print(f"  Saved: {xlsx_path}")

    # Write to Google Sheets (if --sheets-id was passed)
    if args.sheets_id:
        if not args.credentials:
            print("\nError: --credentials is required when using --sheets-id")
            sys.exit(1)

        analyzer = Path(__file__).parent.parent / "routine-analyzer" / "analyze.py"

        # Pre-upload: analyze existing history before adding the new routine
        if analyzer.exists():
            print("\nRunning pre-upload analysis (global + monthly)...")
            subprocess.run([sys.executable, str(analyzer), "--mode", "global"],  check=False)
            subprocess.run([sys.executable, str(analyzer), "--mode", "monthly"], check=False)

        print(f"\nUpdating Google Sheets: {args.sheets_id}")
        service = get_sheets_service(args.credentials)
        write_to_google_sheets(service, args.sheets_id, tab_name, data["days"], force=args.force)
        print(f"  Done! https://docs.google.com/spreadsheets/d/{args.sheets_id}")

        # Post-upload: analyze the new routine already loaded in the sheet
        if analyzer.exists():
            print("\nRunning post-upload analysis (new-routine)...")
            subprocess.run([sys.executable, str(analyzer), "--mode", "new-routine"], check=False)

    if not args.no_xlsx and not args.sheets_id:
        print("\nTip: use --sheets-id and --credentials to also sync to Google Sheets.")


# This block only runs when you execute the script directly with python3.
# If another file imports this module, this block does NOT run.
if __name__ == "__main__":
    main()
