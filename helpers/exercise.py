"""
helpers/exercise.py — Utilidades sobre ejercicios individuales.

Responsabilidades:
    - Formatear el nombre de un ejercicio para mostrarlo en la planilla
    - Calcular el nombre del tab (próximo lunes)
    - Convertir la lista de ejercicios en un layout de filas para la tabla
"""

from datetime import date, timedelta


def make_tab_name(_vigencia_start=None, _vigencia_end=None):
    """
    Genera el nombre del tab de Google Sheets usando el próximo lunes.
    Formato: "19/05/26-..."
    Si hoy es lunes, va al lunes siguiente (no al de hoy).
    """
    today = date.today()
    # weekday() retorna 0=lunes ... 6=domingo
    # Esta fórmula calcula cuántos días faltan para el próximo lunes
    days_until_monday = (7 - today.weekday()) % 7 or 7
    next_monday = today + timedelta(days=days_until_monday)
    return next_monday.strftime("%d/%m/%y") + "-..."


def exercise_display_name(ex):
    """
    Retorna el nombre del ejercicio para mostrarlo en la planilla.
    Si el ejercicio tiene un comentario (ej: "MANOS ATRAS DE LA NUCA"),
    lo agrega entre paréntesis en minúscula: "Abdominal recto largo (manos atras de la nuca)"
    """
    name    = ex["name"]
    comment = ex.get("comment", "").strip()   # .get() retorna "" si no existe la clave "comment"
    return f"{name} ({comment.lower()})" if comment else name


def day_exercise_layout(exercises):
    """
    Convierte la lista de ejercicios de un día en pares (tipo, ejercicio).
    Tipos:
        'comb' — ejercicio combinado (fondo amarillo, sin separador entre ellos)
        'solo' — ejercicio individual (fondo blanco, con borde propio)

    Retorna una lista de tuplas: [('comb', ex), ('solo', ex), ...]
    """
    # Esto es una "list comprehension": forma compacta de construir una lista con un for
    return [("comb" if ex.get("is_comb") else "solo", ex) for ex in exercises]
