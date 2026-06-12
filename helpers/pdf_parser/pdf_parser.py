"""
helpers/pdf_parser.py — PDF data extraction logic.

Responsibilities:
    - Read the PDF file with pdfplumber
    - Detect days, exercises, weekly repetitions and comments
    - Return the data in a Python structure (dicts and lists)
"""

import re
import pdfplumber


# ── PDF position constants ────────────────────────────────────────────────────
# pdfplumber measures coordinates in points from the top-left corner.

# X coordinate that divides the PDF into left and right columns
COL_SPLIT_X = 290

# X coordinate ranges where exercise numbers appear.
# Tuples: (x_minimum, x_maximum)
LEFT_EX_NUM_X_RANGE  = (55, 80)
RIGHT_EX_NUM_X_RANGE = (345, 370)

# Minimum Y coordinate to skip the PDF header (logo, title, etc.)
HEADER_BOTTOM_Y = 230


def group_lines(words, y_tolerance=4):
    """
    Groups words into lines based on their vertical position (Y coordinate).

    pdfplumber extracts each word with its exact position. Two words on the
    same line may have slightly different Y values (e.g. 100.1 vs 100.4), so
    we use a tolerance of 4 points to group them.

    Parameters:
        words       — list of dicts with keys 'text', 'x0', 'top', etc.
        y_tolerance — how many points of Y difference are considered "same line"

    Returns: list of lines, where each line is a list of words ordered left to right.
    """
    if not words:
        return []

    # Sort words: first by rounded Y (to group), then by X
    words = sorted(words, key=lambda w: (round(w["top"] / y_tolerance) * y_tolerance, w["x0"]))

    lines = []
    current_line = [words[0]]

    # Iterate through each word and add it to the current line or start a new one
    for word in words[1:]:
        if abs(word["top"] - current_line[0]["top"]) <= y_tolerance:
            current_line.append(word)
        else:
            # New line: save the previous one sorted by X
            lines.append(sorted(current_line, key=lambda w: w["x0"]))
            current_line = [word]

    lines.append(sorted(current_line, key=lambda w: w["x0"]))
    return lines


def line_text(line):
    """Returns the human-readable text for one grouped PDF line."""
    return " ".join(w["text"] for w in line)


def is_exercise_number(word, col):
    """
    Returns True when a word is the exercise number marker for a column.

    PDFs have exercise numbers at specific X positions.
    This function verifies that:
      1. The text is a digit
      2. It is in the range 1-20
      3. It is in the correct X zone for the column ('left' or 'right')
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
    Parses the exercises from ONE horizontal column of the PDF.

    The PDF has two exercise columns (left and right).
    This function filters the words that fall within [x_min, x_max]
    and builds a list of exercises with their weekly repetitions.

    Returns a tuple:
        exercises   — list of dicts: {number, name, is_comb, top, x0, week_reps}
                      top/x0 preserve the visual location of the exercise number so
                      the caller can reconstruct page order across both columns.
        comb_groups — list of [first_ex_ref, count] to re-apply combos cross-column.
                      first_ex_ref is the actual exercise object stored in exercises,
                      not a copied identifier, so the caller can find the exact start
                      row even when exercise numbers restart in the right column.
    """
    # Filter only words that fall in this column and below the header
    words = [w for w in all_words if x_min <= w["x0"] < x_max and w["top"] > header_bottom_y]
    if not words:
        return [], []

    # Work line-by-line after spatial grouping; the parser logic depends on the
    # visual reading order more than on the raw word list returned by pdfplumber.
    lines = group_lines(words)

    exercises          = []
    current_ex         = None     # exercise currently being built
    pending_name_parts = []       # name fragments seen BEFORE the exercise number
    week_reps          = [None, None, None, None]   # repetitions for 4 weeks
    comb_count         = 0        # how many exercises the current Comb has
    comb_assigned      = 0        # how many of the Comb have been marked
    comb_groups        = []       # to re-apply combos cross-column later; entries: [ex_ref, count]
    current_comb_start = None     # reference to the first exercise in the current Comb

    def save_exercise():
        """
        Saves the current exercise to the list and resets the state.
        Nested function (closure): can access and modify outer scope
        variables using 'nonlocal'.
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

        # Ignore set and weight header lines
        if re.match(r"^Series\s+\d", txt) or re.match(r"^kg\b", txt):
            continue

        # Detect "Comb xN" — indicates the next N exercises are combined.
        # The actual group may continue across columns, so here we only record
        # where the group starts inside this column and how many items it spans.
        m_comb = re.match(r"^Comb\s+x(\d+)", txt, re.IGNORECASE)
        if m_comb:
            comb_count = int(m_comb.group(1))
            comb_assigned = 0
            current_comb_start = None
            continue

        # Detect "repeticiones X X X" → week 1 repetitions (3 sets)
        m = re.match(r"^repeticiones\s+(\d+)\s+(\d+)\s+(\d+)", txt)
        if m and current_ex is not None:
            week_reps[0] = [int(m.group(1)), int(m.group(2)), int(m.group(3))]
            continue

        # Detect weekly progression: "2da X", "3ra X", "4ta X"
        # Use re.search (not re.match) to find the pattern anywhere in the line,
        # capturing lines like "HANDS BEHIND NECK 2da 6" or "2da 8 EACH LEG"
        m2 = re.search(r"(2da|3ra|4ta)\s+(\d+)", txt)
        if m2 and current_ex is not None:
            week_idx = {"2da": 1, "3ra": 2, "4ta": 3}[m2.group(1)]
            rep = int(m2.group(2))
            if week_reps[0] is not None:
                week_reps[week_idx] = [rep, rep, rep]   # same reps for all 3 sets

            # Extract comment: text before or after the "2da X" token
            before = txt[:m2.start()].strip()
            after  = txt[m2.end():].strip()
            # Ignore load suggestions like "con mas peso"
            after = re.sub(r"con\s+mas\s+peso.*", "", after, flags=re.IGNORECASE).strip()
            comment = (before or after).strip()
            if comment and not re.match(r"^[\d\s]+$", comment):
                # setdefault: only saves if there is NOT already a comment (doesn't overwrite)
                current_ex.setdefault("comment", comment)
            continue

        # Check if any word in this line is an exercise number.
        # next(..., None) returns the first element matching the condition, or None if none.
        ex_num_word = next((w for w in line if is_exercise_number(w, col_side)), None)

        if ex_num_word is not None:
            # Capture the pending name BEFORE saving (save_exercise clears it)
            name_from_above = " ".join(pending_name_parts).strip()

            save_exercise()   # save the previous exercise if there was one

            num = int(ex_num_word["text"])

            # Exercise name = words to the right of the number on the same line
            name_words  = [w["text"] for w in line if w["x0"] > ex_num_word["x0"]]
            name_inline = " ".join(name_words).strip()

            # Combine name from above (pending) with the name from the number line
            if name_inline and name_from_above:
                name = name_from_above + " " + name_inline
            elif name_inline:
                name = name_inline
            else:
                name = name_from_above

            # Store the exercise-number position. The caller later sorts all
            # exercises from both columns by (top, x0) to reconstruct the true
            # visual order of the page before re-applying Comb membership.
            ex_top = ex_num_word.get("top", 0)
            ex_x0  = ex_num_word.get("x0", 0)
            current_ex = {"number": num, "name": name.strip(), "is_comb": False,
                          "top": ex_top, "x0": ex_x0}

            # Mark as combined if we are inside a Comb block
            if comb_count > 0 and comb_assigned < comb_count:
                current_ex["is_comb"] = True
                if current_comb_start is None:
                    # Register the first object of the group. Using the object
                    # reference avoids ambiguous lookups when the right column
                    # restarts numbering from 1.
                    current_comb_start = current_ex
                    comb_groups.append([current_ex, comb_count])
                comb_assigned += 1
                if comb_assigned >= comb_count:
                    # Comb group finished, reset counters
                    comb_count = 0
                    comb_assigned = 0
                    current_comb_start = None
            pending_name_parts = []
            week_reps = [None, None, None, None]
            continue

        # Line without an exercise number: may be a name fragment or a comment
        if txt and not re.match(r"^[\d\s]+$", txt):
            skip_patterns = r"^(repeticiones|Series|kg|2da|3ra|4ta|\d+(\.\d+)?[\s\|]*)+$"
            if not re.match(skip_patterns, txt):
                all_weeks_done = all(week_reps[i] is not None for i in range(4))
                if current_ex is None or all_weeks_done:
                    # Name that appears BEFORE the next exercise's number
                    pending_name_parts.append(txt)
                elif week_reps[0] is None:
                    # Name continuation, before "repeticiones".
                    # Some exercise names wrap onto their own line instead of
                    # fitting next to the exercise number.
                    current_ex["name"] = (current_ex["name"] + " " + txt).strip()
                else:
                    # Text after "repeticiones" that is not a progression → it's a comment
                    # (e.g. "HANDS BEHIND THE NECK" on a separate line)
                    current_ex.setdefault("comment", txt)

    save_exercise()   # save the last exercise in the column
    return exercises, comb_groups


def parse_pdf(pdf_path):
    """
    Reads the full PDF and returns the structured data for all days.

    Returns a dict with:
        'vigencia_start' — start date (str "DD/MM/YYYY")
        'vigencia_end'   — end date
        'days'           — dict {day_number: [list of exercises]}

    Note: the first Comb group in the PDF (universal exercises like abs)
    is automatically propagated to ALL days.
    """
    result = {"vigencia_start": None, "vigencia_end": None, "days": {}}
    first_pdf_day   = None   # day from the first PDF page (to identify the universal Comb)
    comb_group_id   = 0      # globally unique ID per comb group across all pages

    # Open the PDF with pdfplumber ('with' ensures it is closed when done)
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()         # list of dicts with each word and its position
            text  = page.extract_text() or ""    # plain text of the page

            # Extract "Vigencia: DD/MM/YYYY - DD/MM/YYYY" from the first page
            if result["vigencia_start"] is None:
                m = re.search(r"Vigencia:\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})", text)
                if m:
                    result["vigencia_start"] = m.group(1)
                    result["vigencia_end"]   = m.group(2)

            # Detect the day number: digit centered at X≈294, Y≈218
            day_num = None
            for w in words:
                if (w["text"].isdigit() and 1 <= int(w["text"]) <= 10
                        and 280 < w["x0"] < 310 and 210 < w["top"] < 235):
                    day_num = int(w["text"])
                    break

            if day_num is None:
                # Continuation page (no day header) → add to the last day
                if result["days"]:
                    last_day = max(result["days"].keys())
                    day_num = last_day
                else:
                    continue
                effective_header_bottom = 50   # continuation pages don't have a large header
            else:
                effective_header_bottom = HEADER_BOTTOM_Y
                if first_pdf_day is None:
                    first_pdf_day = day_num

            # Parse left and right columns separately
            left_ex,  left_comb_groups  = parse_column(words, 0, COL_SPLIT_X, "left",  effective_header_bottom)
            right_ex, right_comb_groups = parse_column(words, COL_SPLIT_X, 9999, "right", effective_header_bottom)

            # Merge both columns sorted by page position (top-to-bottom, left-to-right).
            # Sorting by (top, x0) preserves the visual page order, which is critical
            # for correctly identifying combined pairs when the right column restarts
            # exercise numbering (e.g. right-col #1 pairs with left-col #9).
            all_ex = sorted(left_ex + right_ex, key=lambda e: (e.get("top", 0), e.get("x0", 0)))

            # Re-apply Comb membership globally.
            # Problem: parse_column marks combos within its own column.
            # If a Comb has exercises in both columns (e.g. 1 left, 2 right, 3 left),
            # the right column doesn't know that exercise 2 is part of the Comb.
            # Solution: use comb_groups (object reference + count) to mark the correct
            # exercises in the combined list from both columns.
            all_comb_groups = left_comb_groups + right_comb_groups
            if all_comb_groups:
                for ex in all_ex:
                    ex["is_comb"] = False   # reset first
                for start_ex, count in all_comb_groups:
                    # Find the starting exercise by object identity (not by number),
                    # so number resets / duplicates in the right column are handled correctly.
                    start_idx = next((i for i, e in enumerate(all_ex) if e is start_ex), None)
                    if start_idx is None:
                        continue
                    for i in range(start_idx, min(start_idx + count, len(all_ex))):
                        all_ex[i]["is_comb"]       = True
                        all_ex[i]["comb_group"]    = comb_group_id
                    # Give each Comb its own stable page-level ID so later Sheet
                    # formatting can distinguish adjacent combined blocks.
                    comb_group_id += 1

            if day_num not in result["days"]:
                result["days"][day_num] = []
            result["days"][day_num].extend(all_ex)

            # Remember the first day's Comb metadata so we can later identify the
            # universal warmup block without guessing from exercise names alone.
            if day_num == first_pdf_day and all_comb_groups and "_first_day_comb_groups" not in result:
                result["_first_day_comb_groups"] = all_comb_groups

    # ── Propagate universal exercises (Comb from the first day) to all days ──
    # Abs and similar exercises appear only on the first PDF page
    # but must be present in all days.
    if first_pdf_day and first_pdf_day in result["days"]:
        # The warmup is the FIRST comb group (topmost on the page) in the first day.
        # Use comb_groups to know exactly how many exercises it contains, avoiding
        # accidentally including other Comb groups that start right after the warmup.
        # Keep the temporary metadata out of the public return value.
        first_day_groups = result.pop("_first_day_comb_groups", [])
        warmup_count = 0
        if first_day_groups:
            # The universal warmup is defined as the earliest Comb block on the
            # first day. We use the recorded count of that block so we copy only
            # its members, even if another Comb starts immediately afterwards.
            earliest = min(first_day_groups, key=lambda g: g[0].get("top", 0))
            warmup_count = earliest[1]
        universal_comb = [ex for ex in result["days"][first_pdf_day][:warmup_count]
                          if ex.get("is_comb")]
        if universal_comb:
            universal_names = {ex["name"] for ex in universal_comb}
            for day_num, exercises in result["days"].items():
                if day_num == first_pdf_day:
                    continue   # first day already has them
                # Only prepend if the universal exercises are missing entirely.
                # Name-based detection is sufficient here because these copied
                # warmup exercises should appear unchanged across days.
                existing_names = {ex["name"] for ex in exercises}
                if not universal_names.intersection(existing_names):
                    prepend = [dict(ex) for ex in universal_comb]
                    result["days"][day_num] = prepend + exercises

    return result
