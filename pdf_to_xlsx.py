#!/usr/bin/env python3
"""
pdf_to_xlsx.py — Punto de entrada del script.

Lee un PDF de rutinas de entrenamiento y escribe los datos en Google Sheets.

Uso:
    python3 pdf_to_xlsx.py <pdf.pdf> --sheets-id XXXX --credentials creds.json [--force] [--no-xlsx]

Estructura del proyecto:
    pdf_to_xlsx.py       ← este archivo (solo el CLI)
    helpers/
        pdf_parser.py    ← extracción de datos del PDF
        exercise.py      ← utilidades de ejercicios (nombre, layout, tab name)
        sheets.py        ← escritura y formato en Google Sheets
        xlsx.py          ← escritura en archivo .xlsx local
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

    # argparse maneja los argumentos de línea de comandos automáticamente
    parser = argparse.ArgumentParser(
        description="Parse a training PDF and write it to Google Sheets."
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
        action="store_true",   # si está presente, args.no_xlsx = True
        help="Skip writing to the local XLSX file",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete and recreate the tab if it already exists",
    )
    args = parser.parse_args()

    pdf_path  = args.pdf
    xlsx_path = args.xlsx or str(Path(pdf_path).parent / "Rutinas entrenamiento.xlsx")

    print(f"Parsing PDF: {pdf_path}")
    data = parse_pdf(pdf_path)

    # Mostrar resumen de lo que se parseó
    print(f"  Vigencia: {data['vigencia_start']} - {data['vigencia_end']}")
    for day_num, exercises in sorted(data["days"].items()):
        print(f"  Dia {day_num}: {len(exercises)} ejercicios")
        for ex in exercises:
            print(f"    #{ex['number']} {exercise_display_name(ex)} | semanas: {ex.get('week_reps')}")

    tab_name = make_tab_name(data["vigencia_start"], data["vigencia_end"])
    print(f"\nTab name: {tab_name}")

    # Escribir a archivo XLSX local (si no se pasó --no-xlsx)
    if not args.no_xlsx:
        print(f"\nUpdating XLSX: {xlsx_path}")
        wb = openpyxl.load_workbook(xlsx_path)
        write_xlsx_tab(wb, tab_name, data["days"])
        wb.save(xlsx_path)
        print(f"  Saved: {xlsx_path}")

    # Escribir a Google Sheets (si se pasó --sheets-id)
    if args.sheets_id:
        if not args.credentials:
            print("\nError: --credentials is required when using --sheets-id")
            sys.exit(1)
        print(f"\nUpdating Google Sheets: {args.sheets_id}")
        service = get_sheets_service(args.credentials)
        write_to_google_sheets(service, args.sheets_id, tab_name, data["days"], force=args.force)
        print(f"  Done! https://docs.google.com/spreadsheets/d/{args.sheets_id}")

        # Disparar el análisis de nueva rutina automáticamente
        analyzer = Path(__file__).parent.parent / "routine-analyzer" / "analyze.py"
        if analyzer.exists():
            print("\nRunning new-routine analysis...")
            subprocess.run([sys.executable, str(analyzer), "--mode", "new-routine"], check=False)

    if not args.no_xlsx and not args.sheets_id:
        print("\nTip: use --sheets-id and --credentials to also sync to Google Sheets.")


# Este bloque solo se ejecuta cuando corrés el script directamente con python3.
# Si otro archivo importa este módulo, este bloque NO se ejecuta.
if __name__ == "__main__":
    main()
