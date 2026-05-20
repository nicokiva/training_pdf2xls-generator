"""
helpers/pdf_parser.py — Lógica de extracción de datos del PDF.

Responsabilidades:
    - Leer el archivo PDF con pdfplumber
    - Detectar días, ejercicios, repeticiones semanales y comentarios
    - Retornar los datos en una estructura de Python (dicts y listas)
"""

import re
import pdfplumber


# ── Constantes de posición en el PDF ─────────────────────────────────────────
# pdfplumber mide las coordenadas en puntos desde la esquina superior izquierda.

# Coordenada X que divide el PDF en columna izquierda y columna derecha
COL_SPLIT_X = 290

# Rango de coordenadas X donde aparecen los números de ejercicio.
# Son tuplas: (x_mínima, x_máxima)
LEFT_EX_NUM_X_RANGE  = (55, 80)
RIGHT_EX_NUM_X_RANGE = (345, 370)

# Coordenada Y mínima para ignorar el encabezado del PDF (logo, título, etc.)
HEADER_BOTTOM_Y = 230


def group_lines(words, y_tolerance=4):
    """
    Agrupa palabras en líneas según su posición vertical (coordenada Y).

    pdfplumber extrae cada palabra con su posición exacta. Dos palabras en la
    misma línea pueden tener Y levemente diferente (ej: 100.1 vs 100.4), así
    que usamos una tolerancia de 4 puntos para agruparlas.

    Parámetros:
        words       — lista de dicts con claves 'text', 'x0', 'top', etc.
        y_tolerance — cuántos puntos de diferencia en Y se consideran "misma línea"

    Retorna: lista de líneas, donde cada línea es una lista de palabras ordenadas de izq a der.
    """
    if not words:
        return []

    # Ordenamos las palabras: primero por Y redondeado (para agrupar), luego por X
    words = sorted(words, key=lambda w: (round(w["top"] / y_tolerance) * y_tolerance, w["x0"]))

    lines = []
    current_line = [words[0]]

    # Recorremos cada palabra y la sumamos a la línea actual o abrimos una nueva
    for word in words[1:]:
        if abs(word["top"] - current_line[0]["top"]) <= y_tolerance:
            current_line.append(word)
        else:
            # Nueva línea: guardamos la anterior ordenada por X
            lines.append(sorted(current_line, key=lambda w: w["x0"]))
            current_line = [word]

    lines.append(sorted(current_line, key=lambda w: w["x0"]))
    return lines


def line_text(line):
    """Une las palabras de una línea en un string con espacios."""
    # Esto es un "generator expression": itera sobre `line` y toma el texto de cada palabra
    return " ".join(w["text"] for w in line)


def is_exercise_number(word, col):
    """
    Determina si una palabra es el número de un ejercicio.

    Los PDFs tienen números de ejercicio en posiciones X específicas.
    Esta función verifica que:
      1. El texto sea un dígito
      2. Esté en el rango 1-20
      3. Esté en la zona X correcta para la columna ('left' o 'right')
    """
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
    Parsea los ejercicios de UNA columna horizontal del PDF.

    El PDF tiene dos columnas de ejercicios (izquierda y derecha).
    Esta función filtra las palabras que caen dentro de [x_min, x_max]
    y construye una lista de ejercicios con sus repeticiones semanales.

    Retorna una tupla:
        exercises   — lista de dicts: {number, name, is_comb, week_reps}
        comb_groups — lista de [primer_numero, cantidad] para re-aplicar combos cross-column
    """
    # Filtramos solo las palabras que caen en esta columna y por debajo del header
    words = [w for w in all_words if x_min <= w["x0"] < x_max and w["top"] > header_bottom_y]
    if not words:
        return [], []

    lines = group_lines(words)

    exercises          = []
    current_ex         = None     # ejercicio que estamos construyendo ahora mismo
    pending_name_parts = []       # fragmentos de nombre vistos ANTES del número de ejercicio
    week_reps          = [None, None, None, None]   # repeticiones de las 4 semanas
    comb_count         = 0        # cuántos ejercicios tiene el Comb actual
    comb_assigned      = 0        # cuántos del Comb ya marcamos
    comb_groups        = []       # para re-aplicar combos cross-column después
    current_comb_start = None     # número del primer ejercicio del Comb actual

    def save_exercise():
        """
        Guarda el ejercicio actual en la lista y resetea el estado.
        Es una función anidada (closure): puede acceder y modificar las
        variables del scope externo usando 'nonlocal'.
        """
        nonlocal current_ex, pending_name_parts, week_reps
        if current_ex is not None:
            current_ex["week_reps"] = week_reps
            exercises.append(current_ex)
        current_ex = None
        pending_name_parts = []
        week_reps = [None, None, None, None]

    for line in lines:
        txt = line_text(line)

        # Ignorar líneas de encabezado de series y pesos
        if re.match(r"^Series\s+\d", txt) or re.match(r"^kg\b", txt):
            continue

        # Detectar "Comb xN" — indica que los próximos N ejercicios son combinados
        m_comb = re.match(r"^Comb\s+x(\d+)", txt, re.IGNORECASE)
        if m_comb:
            comb_count = int(m_comb.group(1))   # group(1) = lo que capturó el paréntesis (\d+)
            comb_assigned = 0
            current_comb_start = None
            continue

        # Detectar "repeticiones X X X" → repeticiones de la semana 1 (3 series)
        m = re.match(r"^repeticiones\s+(\d+)\s+(\d+)\s+(\d+)", txt)
        if m and current_ex is not None:
            week_reps[0] = [int(m.group(1)), int(m.group(2)), int(m.group(3))]
            continue

        # Detectar progresión semanal: "2da X", "3ra X", "4ta X"
        # Usamos re.search (no re.match) para encontrar el patrón en cualquier parte de la línea,
        # así capturamos también líneas como "MANOS ATRAS DE LA NUCA 2da 6" o "2da 8 CADA PIERNA"
        m2 = re.search(r"(2da|3ra|4ta)\s+(\d+)", txt)
        if m2 and current_ex is not None:
            week_idx = {"2da": 1, "3ra": 2, "4ta": 3}[m2.group(1)]
            rep = int(m2.group(2))
            if week_reps[0] is not None:
                week_reps[week_idx] = [rep, rep, rep]   # mismas reps para las 3 series

            # Extraer comentario: texto antes o después del token "2da X"
            before = txt[:m2.start()].strip()
            after  = txt[m2.end():].strip()
            # Ignorar sugerencias de carga como "con mas peso"
            after = re.sub(r"con\s+mas\s+peso.*", "", after, flags=re.IGNORECASE).strip()
            comment = (before or after).strip()
            if comment and not re.match(r"^[\d\s]+$", comment):
                # setdefault: solo guarda si NO hay ya un comentario (no sobreescribe)
                current_ex.setdefault("comment", comment)
            continue

        # Verificar si alguna palabra de esta línea es un número de ejercicio
        # next(..., None) retorna el primer elemento que cumpla la condición, o None si no hay ninguno
        ex_num_word = next((w for w in line if is_exercise_number(w, col_side)), None)

        if ex_num_word is not None:
            # Capturamos el nombre pendiente ANTES de guardar (save_exercise lo borra)
            name_from_above = " ".join(pending_name_parts).strip()

            save_exercise()   # guardamos el ejercicio anterior si había uno

            num = int(ex_num_word["text"])

            # Nombre del ejercicio = palabras a la derecha del número en la misma línea
            name_words  = [w["text"] for w in line if w["x0"] > ex_num_word["x0"]]
            name_inline = " ".join(name_words).strip()

            # Combinamos nombre de arriba (pending) con el de la línea del número
            if name_inline and name_from_above:
                name = name_from_above + " " + name_inline
            elif name_inline:
                name = name_inline
            else:
                name = name_from_above

            # Creamos el dict del ejercicio
            current_ex = {"number": num, "name": name.strip(), "is_comb": False}

            # Marcar como combinado si estamos dentro de un bloque Comb
            if comb_count > 0 and comb_assigned < comb_count:
                current_ex["is_comb"] = True
                if current_comb_start is None:
                    # Registramos el inicio del grupo para poder re-aplicarlo cross-column
                    current_comb_start = num
                    comb_groups.append([num, comb_count])
                comb_assigned += 1
                if comb_assigned >= comb_count:
                    # Terminó el grupo Comb, reseteamos contadores
                    comb_count = 0
                    comb_assigned = 0
                    current_comb_start = None

            pending_name_parts = []
            week_reps = [None, None, None, None]
            continue

        # Línea sin número de ejercicio: puede ser un fragmento de nombre o un comentario
        if txt and not re.match(r"^[\d\s]+$", txt):
            skip_patterns = r"^(repeticiones|Series|kg|2da|3ra|4ta|\d+(\.\d+)?[\s\|]*)+$"
            if not re.match(skip_patterns, txt):
                all_weeks_done = all(week_reps[i] is not None for i in range(4))
                if current_ex is None or all_weeks_done:
                    # Nombre que aparece ANTES del número del ejercicio siguiente
                    pending_name_parts.append(txt)
                elif week_reps[0] is None:
                    # Continuación del nombre, antes de "repeticiones"
                    current_ex["name"] = (current_ex["name"] + " " + txt).strip()
                else:
                    # Texto después de "repeticiones" que no es progresión → es un comentario
                    # (ej: "MANOS ATRAS DE LA NUCA" en una línea separada)
                    current_ex.setdefault("comment", txt)

    save_exercise()   # guardamos el último ejercicio de la columna
    return exercises, comb_groups


def parse_pdf(pdf_path):
    """
    Lee el PDF completo y retorna los datos estructurados de todos los días.

    Retorna un dict con:
        'vigencia_start' — fecha inicio (str "DD/MM/YYYY")
        'vigencia_end'   — fecha fin
        'days'           — dict {número_día: [lista de ejercicios]}

    Nota: el primer grupo Comb del PDF (ejercicios universales como abdominales)
    se propaga automáticamente a TODOS los días.
    """
    result = {"vigencia_start": None, "vigencia_end": None, "days": {}}
    first_pdf_day = None   # día de la primera página del PDF (para saber cuál es el Comb universal)

    # Abrimos el PDF con pdfplumber (el 'with' garantiza que se cierre al terminar)
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()         # lista de dicts con cada palabra y su posición
            text  = page.extract_text() or ""    # texto plano de la página

            # Extraer "Vigencia: DD/MM/YYYY - DD/MM/YYYY" de la primera página
            if result["vigencia_start"] is None:
                m = re.search(r"Vigencia:\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})", text)
                if m:
                    result["vigencia_start"] = m.group(1)
                    result["vigencia_end"]   = m.group(2)

            # Detectar el número de día: dígito centrado en X≈294, Y≈218
            day_num = None
            for w in words:
                if (w["text"].isdigit() and 1 <= int(w["text"]) <= 10
                        and 280 < w["x0"] < 310 and 210 < w["top"] < 235):
                    day_num = int(w["text"])
                    break

            if day_num is None:
                # Página de continuación (sin encabezado de día) → la sumamos al último día
                if result["days"]:
                    last_day = max(result["days"].keys())
                    day_num = last_day
                else:
                    continue
                effective_header_bottom = 50   # las páginas de continuación no tienen header grande
            else:
                effective_header_bottom = HEADER_BOTTOM_Y
                if first_pdf_day is None:
                    first_pdf_day = day_num

            # Parsear columna izquierda y derecha por separado
            left_ex,  left_comb_groups  = parse_column(words, 0, COL_SPLIT_X, "left",  effective_header_bottom)
            right_ex, right_comb_groups = parse_column(words, COL_SPLIT_X, 9999, "right", effective_header_bottom)

            # Unimos ambas columnas ordenando por número de ejercicio
            all_ex = sorted(left_ex + right_ex, key=lambda e: e["number"])

            # Re-aplicar membresía de Comb globalmente.
            # Problema: parse_column marca combos dentro de su propia columna.
            # Si un Comb tiene ejercicios en ambas columnas (ej: 1 izq, 2 der, 3 izq),
            # la columna derecha no sabe que el ejercicio 2 es parte del Comb.
            # Solución: usamos los comb_groups (inicio + cantidad) para marcar
            # los ejercicios correctos en la lista combinada de ambas columnas.
            all_comb_groups = left_comb_groups + right_comb_groups
            if all_comb_groups:
                for ex in all_ex:
                    ex["is_comb"] = False   # reseteamos primero
                all_numbers = [ex["number"] for ex in all_ex]
                for start_num, count in all_comb_groups:
                    if start_num not in all_numbers:
                        continue
                    start_idx = all_numbers.index(start_num)
                    # Marcamos 'count' ejercicios consecutivos a partir del inicio
                    for i in range(start_idx, min(start_idx + count, len(all_ex))):
                        all_ex[i]["is_comb"] = True

            if day_num not in result["days"]:
                result["days"][day_num] = []
            result["days"][day_num].extend(all_ex)

    # ── Propagar los ejercicios universales (Comb del primer día) a todos los días ──
    # Los abdominales y similares aparecen solo en la primera página del PDF
    # pero deben estar en todos los días.
    if first_pdf_day and first_pdf_day in result["days"]:
        universal_comb = [ex for ex in result["days"][first_pdf_day] if ex.get("is_comb")]
        if universal_comb:
            for day_num, exercises in result["days"].items():
                if day_num == first_pdf_day:
                    continue   # el primer día ya los tiene
                if not exercises or not exercises[0].get("is_comb"):
                    # dict(ex) crea una copia independiente del dict (no una referencia)
                    prepend = [dict(ex) for ex in universal_comb]
                    result["days"][day_num] = prepend + exercises

    return result
