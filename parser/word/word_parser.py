"""
Word Document Timetable Parser
Handles two formats:
  1. Lab-wise: table has Room No. + I-YEAR / II & III YEAR rows
  2. Class-wise: table has Time/Day header + course table below (like III year docx)
"""

import re
from docx import Document
from dateutil import parser as date_parser

# ── Constants ────────────────────────────────────────────────

DAY_MAP = {
    'MON': 'MONDAY', 'TUE': 'TUESDAY', 'WED': 'WEDNESDAY',
    'THU': 'THURSDAY', 'FRI': 'FRIDAY', 'SAT': 'SATURDAY',
    'MONDAY': 'MONDAY', 'TUESDAY': 'TUESDAY', 'WEDNESDAY': 'WEDNESDAY',
    'THURSDAY': 'THURSDAY', 'FRIDAY': 'FRIDAY', 'SATURDAY': 'SATURDAY',
}

DAY_ABBREV = {
    'MON': 'MONDAY', 'TUE': 'TUESDAY', 'WED': 'WEDNESDAY',
    'THU': 'THURSDAY', 'FRI': 'FRIDAY', 'SAT': 'SATURDAY',
}

# Slot times for class-wise Word docs (II & III year, 6 slots)
# Slots 0-2 = morning, slots 3-5 = afternoon
II_III_YEAR_SLOTS = [
    ('10:00', '11:00'),
    ('11:00', '12:00'),
    ('12:00', '13:00'),
    ('13:40', '14:40'),
    ('14:40', '15:40'),
    ('15:40', '16:40'),
]

I_YEAR_SLOTS = [
    ('09:00', '10:00'),
    ('10:00', '11:00'),
    ('11:00', '12:00'),
    ('12:40', '13:40'),
    ('13:40', '14:40'),
    ('14:40', '15:40'),
]


# ── Utility Functions ────────────────────────────────────────

def clean(val):
    if val is None:
        return None
    s = str(val).strip().replace('\n', ' ').replace('\r', '')
    return s if s else None


def clean_multiline(val):
    """Keep newlines for parsing room annotations."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def normalize_room(room):
    if not room:
        return None
    # Remove spaces around hyphen, uppercase
    room = re.sub(r'\s+', '', room.upper())
    # Ensure format like E-402
    return room


def classify_session(text):
    t = text.upper()
    if 'TRAINING' in t:
        return 'TRAINING'
    if 'MINOR' in t:
        return 'MINOR'
    if 'WORKSHOP' in t:
        return 'WORKSHOP'
    if 'LAB' in t:
        return 'LAB'
    return 'OTHER'


def get_cell_text(cell):
    """Extract full text from a table cell including all paragraphs."""
    return '\n'.join(p.text.strip() for p in cell.paragraphs if p.text.strip())


def extract_year_from_doc(doc):
    """
    Extract year of study from document paragraphs.
    Looks for 'I Year', 'II Year', 'III Year', 'IV Year'
    """
    for para in doc.paragraphs:
        text = para.text.upper()
        if 'IV YEAR' in text or '4TH YEAR' in text:
            return 4
        if 'III YEAR' in text or '3RD YEAR' in text:
            return 3
        if 'II YEAR' in text or '2ND YEAR' in text:
            return 2
        if 'I YEAR' in text or '1ST YEAR' in text:
            return 1
    return None


# ── Room Annotation Parser ───────────────────────────────────

def parse_room_field(room_text):
    """
    Parse room field from course table.
    Handles:
      'E-402'                         → {None: 'E-402'}  (all days)
      'E-501\nE-503(Thu)'             → {'TUESDAY': 'E-501', 'THURSDAY': 'E-503'}
      'E-502(Fri)\nE-315(Wed)'        → {'FRIDAY': 'E-502', 'WEDNESDAY': 'E-315'}
      'E-503(Tue)\nE-403(Thu)'        → {'TUESDAY': 'E-503', 'THURSDAY': 'E-403'}

    Returns dict: {day_or_None: room_number}
    None key means "used on all days this lab appears"
    """
    if not room_text:
        return {}

    result = {}
    lines = room_text.strip().split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check for day annotation: E-402(Thu) or E-402(Thursday)
        match = re.match(r'([A-Z]-?\d{3})\s*\((\w+)\)', line, re.IGNORECASE)
        if match:
            room = normalize_room(match.group(1))
            day_raw = match.group(2).upper()[:3]
            day = DAY_ABBREV.get(day_raw)
            if room and day:
                result[day] = room
        else:
            # No day annotation → default room
            room = normalize_room(re.sub(r'\(.*?\)', '', line).strip())
            if room and re.match(r'^[A-Z]-?\d{3}$', room):
                result[None] = room  # None = default (all days)

    return result


def resolve_room_for_day(room_map, day):
    """
    Given a room_map from parse_room_field and a day,
    return the correct room number.
    """
    if day in room_map:
        return room_map[day]
    if None in room_map:
        return room_map[None]
    return None


# ── Class-Wise Word Parser ───────────────────────────────────

def is_timetable_table(table):
    """
    Detect if a table is a class timetable grid.
    Looks for day names in first column and slot numbers/times in first row.
    """
    if not table.rows:
        return False

    # Check first row for time/slot indicators
    first_row_text = ' '.join(
        get_cell_text(cell).upper() for cell in table.rows[0].cells
    )
    has_slots = bool(re.search(r'\b(I|II|III|IV|V|VI)\b|10:00|11:00|09:00', first_row_text))

    # Check first column for day names
    day_count = 0
    for row in table.rows[1:]:
        cell_text = get_cell_text(row.cells[0]).upper()[:3]
        if cell_text in DAY_ABBREV:
            day_count += 1

    return has_slots and day_count >= 3


def is_course_table(table):
    """
    Detect if a table is a course/subject table.
    Looks for 'Course Code', 'Subject', 'Room', 'Lab' columns.
    """
    if not table.rows:
        return False
    first_row_text = ' '.join(
        get_cell_text(cell).upper() for cell in table.rows[0].cells
    )
    indicators = ['COURSE', 'SUBJECT', 'CODE', 'ROOM', 'FACULTY', 'LAB']
    return sum(1 for ind in indicators if ind in first_row_text) >= 2


def parse_course_table(table):
    """
    Parse course table to build subject→room mapping.
    Returns dict: {subject_keyword: {day_or_None: room}}

    subject_keyword is normalized (uppercase, stripped)
    """
    course_map = {}

    if not table.rows:
        return course_map

    # Find column indices for subject name and room
    header_row = table.rows[0]
    header_texts = [get_cell_text(cell).upper() for cell in header_row.cells]

    subject_col = None
    room_col = None

    for i, h in enumerate(header_texts):
        if 'COURSE' in h or 'SUBJECT' in h or 'NAME' in h:
            if subject_col is None:
                subject_col = i
        if 'ROOM' in h or 'LAB ROOM' in h or 'VENUE' in h:
            room_col = i

    # Fallback: if headers not found, try common positions
    if subject_col is None:
        subject_col = 1  # usually second column
    if room_col is None:
        # Look for column with room-like values
        for i, h in enumerate(header_texts):
            if re.search(r'[A-Z]-\d{3}', h):
                room_col = i
                break
        if room_col is None:
            room_col = 3  # usually fourth column

    for row in table.rows[1:]:
        if len(row.cells) <= max(subject_col, room_col):
            continue

        subject_text = clean(get_cell_text(row.cells[subject_col]))
        room_text = clean_multiline(get_cell_text(row.cells[room_col]))

        if not subject_text or not room_text:
            continue

        # Only care about lab subjects
        if 'LAB' not in subject_text.upper():
            continue

        # Normalize subject to a keyword for matching
        # e.g. "Big Data Computing Lab (BDC Lab)" → "BDC LAB"
        # Extract abbreviation in parentheses if present
        abbrev_match = re.search(r'\(([^)]+)\)', subject_text)
        if abbrev_match:
            keyword = abbrev_match.group(1).upper().strip()
        else:
            keyword = subject_text.upper().strip()

        room_map = parse_room_field(room_text)
        if room_map:
            course_map[keyword] = room_map

            # Also add the full subject name as a key
            full_key = subject_text.upper().strip()
            if full_key != keyword:
                course_map[full_key] = room_map

    return course_map


def find_lab_in_course_map(cell_text, course_map):
    """
    Given a timetable cell text like 'BDC LAB' or 'WT LAB',
    find matching entry in course_map.
    Returns list of (keyword, room_map) tuples (could be multiple for split batches).
    """
    matches = []
    cell_upper = cell_text.upper()

    # Handle split batches: 'BDC LAB/WT LAB' or 'BDC LAB / WT LAB'
    parts = re.split(r'[/\n]', cell_upper)

    for part in parts:
        part = part.strip()
        if 'LAB' not in part:
            continue

        for keyword, room_map in course_map.items():
            # Check if keyword appears in this part
            kw_clean = re.sub(r'\s+', ' ', keyword).strip()
            part_clean = re.sub(r'\s+', ' ', part).strip()

            if kw_clean in part_clean or part_clean in kw_clean:
                matches.append((keyword, room_map))
                break

    return matches


def detect_slot_times(timetable_table, year_group='II_III_YEAR'):
    """
    Try to extract actual slot times from the timetable header row.
    Falls back to default time bands if parsing fails.
    """
    band = I_YEAR_SLOTS if year_group == 'I_YEAR' else II_III_YEAR_SLOTS

    if not timetable_table.rows:
        return band

    # Look for time patterns in first 2 rows
    time_pattern = re.compile(r'(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})')
    extracted = []

    for row in timetable_table.rows[:2]:
        for cell in row.cells:
            text = get_cell_text(cell)
            for match in time_pattern.finditer(text):
                extracted.append((match.group(1), match.group(2)))

    if len(extracted) >= 6:
        return extracted[:6]

    return band


def parse_class_wise_word(doc, source_file):
    """
    Parse class-wise Word document.
    Groups tables as: [timetable_table, course_table, elective_table] per section.
    Returns list of session dicts.
    """
    sessions = []
    warnings = []

    tables = doc.tables
    year_of_study = extract_year_from_doc(doc)

    # Determine year group for time slots
    if year_of_study == 1:
        year_group = 'I_YEAR'
        slot_band = I_YEAR_SLOTS
    else:
        year_group = 'II_III_YEAR'
        slot_band = II_III_YEAR_SLOTS

    # Extract section name from paragraphs between tables
    # We'll collect all paragraphs and table in document order
    # by iterating doc body elements

    # Group tables: every timetable table is followed by a course table
    timetable_tables = []
    course_tables = []

    for table in tables:
        if is_timetable_table(table):
            timetable_tables.append(table)
        elif is_course_table(table):
            course_tables.append(table)

    # Pair each timetable with its corresponding course table
    # They appear in order: TT1, Course1, TT2, Course2 ...
    pairs = []
    tt_idx = 0
    ct_idx = 0

    # Walk through all tables in order to pair them
    tt_set = set(id(t) for t in timetable_tables)
    ct_set = set(id(t) for t in course_tables)

    current_tt = None
    for table in tables:
        if id(table) in tt_set:
            current_tt = table
        elif id(table) in ct_set and current_tt is not None:
            pairs.append((current_tt, table))
            current_tt = None

    if not pairs:
        warnings.append("Could not pair timetable tables with course tables.")
        return sessions, warnings

    # Parse each section
    for tt_table, course_table in pairs:
        # Build course→room map from course table
        course_map = parse_course_table(course_table)

        if not course_map:
            warnings.append("Course table found but no lab rooms extracted.")
            continue

        # Extract section name from timetable table (usually in header area)
        section_name = None
        if tt_table.rows:
            header_text = get_cell_text(tt_table.rows[0].cells[0])
            if re.search(r'\b(DS|CYS|AI|CSE|ECE|EEE|MECH|CIVIL)\b', header_text, re.IGNORECASE):
                section_name = clean(header_text)

        # Get slot times from timetable (or use defaults)
        slot_times = detect_slot_times(tt_table, year_group)

        # Parse each day row in the timetable
        for row in tt_table.rows[1:]:  # skip header row
            if not row.cells:
                continue

            day_cell = get_cell_text(row.cells[0]).upper().strip()
            day_key = day_cell[:3]
            day_name = DAY_MAP.get(day_key) or DAY_MAP.get(day_cell)

            if not day_name:
                continue

            # Examine each slot cell (columns 1 onwards, skip day column)
            # Track which column indices we've processed
            processed_cols = set()
            cells = row.cells

            slot_idx = 0  # 0-based slot index
            for col_idx in range(1, len(cells)):
                if col_idx in processed_cols:
                    slot_idx += 1
                    continue

                cell_text = get_cell_text(cells[col_idx]).strip()

                if not cell_text:
                    slot_idx += 1
                    continue

                cell_upper = cell_text.upper()

                # Skip lunch
                if 'LUNCH' in cell_upper or cell_upper == 'L':
                    continue

                # Check if this is a lab session
                if 'LAB' not in cell_upper:
                    slot_idx += 1
                    continue

                # Detect merged span (3 consecutive identical cells = 3-hour lab)
                merge_end = col_idx
                for next_col in range(col_idx + 1, min(col_idx + 3, len(cells))):
                    next_text = get_cell_text(cells[next_col]).strip().upper()
                    if next_text == cell_upper or not next_text:
                        merge_end = next_col
                        processed_cols.add(next_col)
                    else:
                        break

                # Determine start and end slot indices for this block
                start_slot = slot_idx
                end_slot = start_slot + (merge_end - col_idx)

                # Get time range
                if start_slot < len(slot_times):
                    start_time = slot_times[start_slot][0]
                else:
                    start_time = slot_times[-1][0]

                if end_slot < len(slot_times):
                    end_time = slot_times[end_slot][1]
                else:
                    end_time = slot_times[-1][1]

                # Find lab(s) from course map
                lab_matches = find_lab_in_course_map(cell_text, course_map)

                if not lab_matches:
                    warnings.append(
                        f"Could not find room for '{cell_text}' on {day_name}. "
                        "Check course table."
                    )
                    slot_idx += 1
                    continue

                for keyword, room_map in lab_matches:
                    room = resolve_room_for_day(room_map, day_name[:3])

                    if not room:
                        warnings.append(
                            f"No room found for '{keyword}' on {day_name}."
                        )
                        continue

                    sessions.append({
                        'room_number': room,
                        'day_of_week': day_name,
                        'start_time': start_time,
                        'end_time': end_time,
                        'class_name': section_name or '',
                        'subject': keyword,
                        'session_type': classify_session(keyword),
                        'year_group': year_group,
                        'source_file': source_file,
                    })

                slot_idx += 1

    return sessions, warnings


# ── Lab-Wise Word Parser ─────────────────────────────────────

def is_lab_wise_table(table):
    """
    Detect if a table is a lab-wise timetable.
    Looks for 'Room No.' or 'I-YEAR' / 'II & III YEAR' in the table.
    """
    full_text = ''
    for row in table.rows[:5]:
        for cell in row.cells:
            full_text += get_cell_text(cell).upper() + ' '

    return (
        'ROOM NO' in full_text or
        'I-YEAR' in full_text or
        'I YEAR' in full_text or
        ('II' in full_text and 'III YEAR' in full_text)
    )


def parse_lab_wise_word(doc, source_file):
    """
    Parse lab-wise Word timetable.
    Structure similar to Excel lab-wise sheets.
    """
    sessions = []
    warnings = []

    for table in doc.tables:
        if not is_lab_wise_table(table):
            continue

        # Extract room number from table metadata
        room_number = None
        for row in table.rows[:5]:
            for cell in row.cells:
                text = get_cell_text(cell)
                room_match = re.search(r'\b([A-Z]-?\s*\d{3})\b', text)
                if room_match:
                    room_number = normalize_room(room_match.group(1))
                    break
            if room_number:
                break

        if not room_number:
            warnings.append("Lab-wise Word table found but could not extract room number.")
            continue

        # Find header row with slot labels
        header_row_idx = None
        slot_cols = {}

        for row_idx, row in enumerate(table.rows):
            row_texts = [get_cell_text(c).upper().strip() for c in row.cells]
            if 'I' in row_texts and 'II' in row_texts:
                header_row_idx = row_idx
                for col_idx, text in enumerate(row_texts):
                    if text in ('I', 'II', 'III', 'IV', 'V', 'VI'):
                        slot_cols[text] = col_idx
                break

        if header_row_idx is None:
            warnings.append(f"Could not find slot header row in lab-wise table for {room_number}.")
            continue

        # Detect time bands (rows after header)
        # Find I-YEAR and II&III-YEAR rows
        year_time_map = {}
        for row in table.rows[header_row_idx + 1: header_row_idx + 4]:
            row_texts = [get_cell_text(c) for c in row.cells]
            first_cell = row_texts[0].upper() if row_texts else ''

            times_in_row = []
            for text in row_texts:
                time_matches = re.findall(r'\d{1,2}:\d{2}', text)
                times_in_row.extend(time_matches)

            if 'I' in first_cell and 'YEAR' in first_cell and times_in_row:
                year_time_map['I_YEAR'] = times_in_row
            elif 'II' in first_cell and times_in_row:
                year_time_map['II_III_YEAR'] = times_in_row

        # Sort slot labels
        slot_order = sorted(slot_cols.items(), key=lambda x: x[1])  # (label, col_idx)

        # Parse day rows
        for row in table.rows[header_row_idx + 1:]:
            row_texts = [get_cell_text(c) for c in row.cells]
            if not row_texts:
                continue

            day_key = row_texts[0].upper().strip()[:3]
            day_name = DAY_MAP.get(day_key)
            if not day_name:
                continue

            processed = set()
            for label, col_idx in slot_order:
                if col_idx in processed or col_idx >= len(row_texts):
                    continue

                cell_text = clean(row_texts[col_idx])
                if not cell_text:
                    continue

                # Detect merge span by checking adjacent identical cells
                merge_slots = [label]
                for next_label, next_col in slot_order:
                    if next_col <= col_idx:
                        continue
                    next_text = clean(row_texts[next_col]) if next_col < len(row_texts) else None
                    if next_text == cell_text or not next_text:
                        merge_slots.append(next_label)
                        processed.add(next_col)
                    else:
                        break

                year_group = 'I_YEAR' if re.match(r'^I[\s\-]', cell_text, re.IGNORECASE) else 'II_III_YEAR'
                band = I_YEAR_SLOTS if year_group == 'I_YEAR' else II_III_YEAR_SLOTS

                slot_label_to_idx = {lbl: idx for idx, (lbl, _) in enumerate(slot_order)}
                slot_indices = [slot_label_to_idx.get(s, 0) for s in merge_slots]

                start_time = band[slot_indices[0]][0] if slot_indices[0] < len(band) else band[0][0]
                end_time = band[slot_indices[-1]][1] if slot_indices[-1] < len(band) else band[-1][1]

                sessions.append({
                    'room_number': room_number,
                    'day_of_week': day_name,
                    'start_time': start_time,
                    'end_time': end_time,
                    'class_name': cell_text,
                    'subject': cell_text,
                    'session_type': classify_session(cell_text),
                    'year_group': year_group,
                    'source_file': source_file,
                })

    return sessions, warnings


# ── Main Word Parse Entry Point ──────────────────────────────

def parse_word(filepath, source_file):
    """
    Main entry point for Word document parsing.
    Auto-detects lab-wise vs class-wise content.
    """
    doc = Document(filepath)

    result = {
        'sessions': [],
        'labs_found': [],
        'warnings': [],
        'content_types_found': [],
    }

    # Check for lab-wise tables first
    lab_wise_tables = [t for t in doc.tables if is_lab_wise_table(t)]
    if lab_wise_tables:
        sessions, warnings = parse_lab_wise_word(doc, source_file)
        result['sessions'].extend(sessions)
        result['warnings'].extend(warnings)
        result['content_types_found'].append('lab_wise')

    # Check for class-wise tables
    tt_tables = [t for t in doc.tables if is_timetable_table(t)]
    if tt_tables:
        sessions, warnings = parse_class_wise_word(doc, source_file)
        result['sessions'].extend(sessions)
        result['warnings'].extend(warnings)
        result['content_types_found'].append('class_wise')

    if not result['content_types_found']:
        result['warnings'].append(
            "Could not detect timetable format in this Word document. "
            "Manual review required."
        )

    result['labs_found'] = list({s['room_number'] for s in result['sessions']})

    return result