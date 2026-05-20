"""
helpers/sheets.py — Integración con Google Sheets.

Responsabilidades:
    - Autenticar con la API de Google usando una Service Account
    - Crear/borrar tabs en la planilla
    - Escribir los datos en la grilla
    - Aplicar todo el formato visual (bordes, colores, columnas, freeze)
"""

from helpers.exercise import exercise_display_name, day_exercise_layout


# Permisos que pedimos a Google (leer y escribir planillas)
SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_sheets_service(credentials_path):
    """
    Crea y retorna el cliente autenticado de la API de Google Sheets.
    Usa una Service Account (archivo JSON de credenciales).
    """
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        credentials_path, scopes=SHEETS_SCOPES
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def sheets_tab_exists(service, spreadsheet_id, tab_name):
    """Retorna True si ya existe un tab con ese nombre en la planilla."""
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    # any() retorna True si al menos un elemento de la secuencia es verdadero
    return any(s["properties"]["title"] == tab_name for s in meta["sheets"])


def get_sheet_id(service, spreadsheet_id, tab_name):
    """Retorna el sheetId numérico interno de un tab (necesario para aplicar formato)."""
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == tab_name:
            return s["properties"]["sheetId"]
    raise ValueError(f"Tab '{tab_name}' not found")


def apply_sheet_formatting(service, spreadsheet_id, sheet_id, days_data, n_weeks=4, n_series=3):
    """
    Aplica todo el formato visual al tab: bordes, colores de fondo, celdas combinadas,
    ancho de columnas y columna fija.

    La API de Google Sheets funciona con "requests" (solicitudes de cambio) que se
    acumulan en una lista y se envían todas juntas en un solo llamado a batchUpdate.
    Esto es más eficiente que hacer un llamado por cada cambio.
    """
    # ── Estilos de borde ──────────────────────────────────────────────────────
    THICK     = {"style": "SOLID_THICK", "colorStyle": {"rgbColor": {}}}   # borde grueso negro
    THIN      = {"style": "SOLID",       "colorStyle": {"rgbColor": {}}}   # borde fino negro
    NO_BORDER = {"style": "NONE"}

    # ── Colores de fondo (RGB de 0.0 a 1.0, no de 0 a 255) ───────────────────
    GREEN_BG = {"red": 0.851, "green": 0.918, "blue": 0.827}   # fila de números de serie
    GRAY_BG  = {"red": 0.941, "green": 0.941, "blue": 0.941}   # fila Rep./Peso
    PEACH_BG = {"red": 1.0,   "green": 0.949, "blue": 0.8}     # nombre de ejercicio combinado
    WHITE_BG = {"red": 1.0,   "green": 1.0,   "blue": 1.0}     # nombre de ejercicio solo

    # Colores muy suaves por semana para las celdas de datos
    WEEK_COLORS = [
        {"red": 0.94, "green": 0.99, "blue": 0.94},  # semana 1: verde muy suave
        {"red": 0.93, "green": 0.96, "blue": 1.0},   # semana 2: azul muy suave
        {"red": 0.97, "green": 0.94, "blue": 1.0},   # semana 3: lavanda muy suave
        {"red": 1.0,  "green": 0.94, "blue": 0.93},  # semana 4: salmón muy suave
    ]

    # Total de columnas: 1 (nombre) + 4 semanas × 3 series × 2 (Rep+Peso) = 25
    n_data_cols = n_weeks * n_series * 2
    total_cols  = 1 + n_data_cols

    def rng(r0, r1, c0, c1):
        """Shortcut para construir un rango de celdas (filas r0..r1, columnas c0..c1)."""
        return {"sheetId": sheet_id, "startRowIndex": r0, "endRowIndex": r1,
                "startColumnIndex": c0, "endColumnIndex": c1}

    def peso_right(w, s):
        """Borde derecho de la celda Peso: grueso al final de cada semana, fino entre series."""
        return THICK if s == n_series - 1 else THIN

    # ── Lista de requests de formato ──────────────────────────────────────────
    # Empezamos con los cambios globales del sheet (columnas, freeze)
    requests = [
        # Fijar ancho de columna A (nombres de ejercicios) en 180px
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                      "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 180},
            "fields": "pixelSize",
        }},
        # Congelar columna A: queda visible al scrollear horizontalmente
        {"updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": {"frozenColumnCount": 1}},
            "fields": "gridProperties.frozenColumnCount",
        }},
        # Fijar ancho de columnas de datos (B en adelante) en 45px
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                      "startIndex": 1, "endIndex": 25},
            "properties": {"pixelSize": 45},
            "fields": "pixelSize",
        }},
    ]
    current_row = 0   # fila actual (índice base 0, como usa la API de Google)

    for day_num in days_data.keys():
        exercises = days_data[day_num]
        if not exercises:
            continue

        # Índices de las filas de este día
        dia_row    = current_row       # fila "Dia N"
        series_row = current_row + 1  # fila de números de serie
        label_row  = current_row + 2  # fila Rep./Peso
        ex_start   = current_row + 3  # primera fila de ejercicios

        # ── Fila "Dia N" ──────────────────────────────────────────────────────
        # Celda A: negrita + bordes gruesos
        requests.append({"repeatCell": {
            "range": rng(dia_row, dia_row+1, 0, 1),
            "cell": {"userEnteredFormat": {
                "textFormat": {"bold": True},
                "borders": {"top": THICK, "bottom": THICK, "left": THICK, "right": NO_BORDER},
            }},
            "fields": "userEnteredFormat(textFormat,borders)",
        }})
        # Celdas B:Y combinadas + bordes gruesos
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

        # ── Fila de números de serie ──────────────────────────────────────────
        # Celda A combinada con la fila de etiquetas (ocupa 2 filas de alto)
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
                # Combinar celda Rep+Peso para mostrar el número de serie centrado
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

        # ── Fila de etiquetas Rep./Peso ───────────────────────────────────────
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

        # ── Filas de ejercicios ───────────────────────────────────────────────
        layout = day_exercise_layout(exercises)

        # Encontrar el índice del ÚLTIMO ejercicio real (para ponerle borde grueso abajo)
        last_ex_layout_idx = max(i for i, (rt, _) in enumerate(layout) if rt != "blank")

        for layout_idx, (row_type, ex) in enumerate(layout):
            cur = ex_start + layout_idx
            if row_type == "blank":
                continue

            is_comb = (row_type == "comb")
            # Fondo de la columna A: amarillo para combos, blanco para solos
            bg      = PEACH_BG if is_comb else WHITE_BG
            is_last = (layout_idx == last_ex_layout_idx)

            # Determinar si es el primer ejercicio de su tipo (para el borde superior)
            prev_non_blank = next(
                (layout[j] for j in range(layout_idx - 1, -1, -1) if layout[j][0] != "blank"),
                None,
            )
            is_first_in_group = (prev_non_blank is None) or (prev_non_blank[0] != row_type)

            # Borde de la celda de nombre (col A)
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

            # Formato de celda A: color de fondo + bordes + wrap de texto
            requests.append({"repeatCell": {
                "range": rng(cur, cur+1, 0, 1),
                "cell": {"userEnteredFormat": {
                    "backgroundColor": bg,
                    "borders": name_borders,
                    "wrapStrategy": "WRAP",   # texto largo baja a la siguiente línea
                }},
                "fields": "userEnteredFormat(backgroundColor,borders,wrapStrategy)",
            }})

            # ── Celdas de datos (Rep + Peso por cada serie de cada semana) ──
            col = 1
            for w in range(n_weeks):
                week_bg = WEEK_COLORS[w]   # color suave de la semana (igual para solos y combos)
                for s in range(n_series):
                    rb = peso_right(w, s)

                    rep_borders  = {}
                    peso_borders = {"right": rb}

                    # Borde superior: en el primer ejercicio del grupo (comb o solo)
                    if is_comb and is_first_in_group:
                        rep_borders["top"]  = THIN
                        peso_borders["top"] = THIN
                    elif not is_comb:
                        rep_borders["top"]  = THIN
                        peso_borders["top"] = THIN

                    # Borde inferior grueso en el último ejercicio del día
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

        # Avanzar current_row: 3 filas de encabezado + filas de ejercicios + 2 en blanco
        current_row += 3 + len(layout) + 2

    # Enviar todos los requests de formato en un solo llamado a la API
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests},
    ).execute()
    print(f"  Formatting applied ({len(requests)} requests)")


def build_sheet_values(days_data):
    """
    Construye la grilla de datos (lista de listas) para escribir en Google Sheets.
    Cada lista interna representa una fila; cada elemento, una celda.
    """
    all_rows = []

    for pos, day_num in enumerate(days_data.keys(), start=1):
        exercises = days_data[day_num]
        if not exercises:
            continue

        # Fila "Dia N"
        all_rows.append([f"Dia {pos}"])

        # Fila de números de serie
        series_row = [""]
        for _week in range(4):
            for s in range(1, 4):
                series_row.extend([s, ""])
        all_rows.append(series_row)

        # Fila de etiquetas
        label_row = [""]
        for _week in range(4):
            for _s in range(3):
                label_row.extend(["Rep.", "Peso"])
        all_rows.append(label_row)

        # Filas de ejercicios
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
                    ex_row.append("")   # columna Peso (vacía, se llena a mano)
            all_rows.append(ex_row)

        # Dos filas vacías entre días
        all_rows.append([])
        all_rows.append([])

    # Reemplazar None por "" (la API de Sheets no acepta None)
    return [[("" if v is None else v) for v in row] for row in all_rows]


def write_to_google_sheets(service, spreadsheet_id, tab_name, days_data, force=False):
    """
    Crea el tab en Google Sheets y escribe los datos con formato.

    Si el tab ya existe:
        - Con force=False: no hace nada (evita sobreescribir accidentalmente)
        - Con force=True:  borra el tab existente y lo recrea desde cero
    """
    sheets = service.spreadsheets()

    if sheets_tab_exists(service, spreadsheet_id, tab_name):
        if not force:
            print(f"  Tab '{tab_name}' ya existe — no se hace nada.")
            return
        # Borrar tab existente
        existing_id = get_sheet_id(service, spreadsheet_id, tab_name)
        sheets.batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"deleteSheet": {"sheetId": existing_id}}]},
        ).execute()
        print(f"  Deleted existing tab '{tab_name}'")

    # Crear nuevo tab al frente (index 0)
    resp = sheets.batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": tab_name, "index": 0}}}]},
    ).execute()
    sheet_id = resp["replies"][0]["addSheet"]["properties"]["sheetId"]
    print(f"  Created new tab '{tab_name}' at position 0")

    # Escribir los valores en la grilla
    values = build_sheet_values(days_data)
    sheets.values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{tab_name}'!A1",
        valueInputOption="RAW",
        body={"values": values},
    ).execute()
    print(f"  Written {len(values)} rows to '{tab_name}'")

    # Aplicar formato visual
    apply_sheet_formatting(service, spreadsheet_id, sheet_id, days_data)
