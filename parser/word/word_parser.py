"""
Word Document Timetable Parser — VNRVJIET Lab Occupancy System

Handles class-wise Word documents. Each document contains N sections,
each with 3 tables: timetable grid, course table, OE table.
Extracts lab sessions only (cells containing 'LAB').

Alignment with excel_parser.py:
- year_group values: I_YEAR | II_YEAR | III_YEAR | IV_YEAR  (no II_III_YEAR anywhere)
- year_group source: paragraph text 'Class : III Year' -> III_YEAR (not cell content)
- class_name: 'BRANCH-SECTION' e.g. 'CSE-DS-A' (from section header)
- subject: lab short name e.g. 'BDC LAB', 'WT LAB' (always different from class_name)
- session_type: always 'LAB' for word parser (only lab sessions extracted)
"""

import re
from docx import Document
from docx.oxml.ns import qn

# ── Constants ────────────────────────────────────────────────

DAY_MAP = {
    'MONDAY': 'MONDAY', 'TUESDAY': 'TUESDAY', 'WEDNESDAY': 'WEDNESDAY',
    'THURSDAY': 'THURSDAY', 'FRIDAY': 'FRIDAY', 'SATURDAY': 'SATURDAY',
}

DAY_ABBR_MAP = {
    'MON': 'MONDAY', 'TUE': 'TUESDAY', 'WED': 'WEDNESDAY',
    'THU': 'THURSDAY', 'FRI': 'FRIDAY', 'SAT': 'SATURDAY',
}

# Maps Roman numeral from 'Class : III Year' paragraph to DB year_group value.
# Matches excel_parser convention: I_YEAR | II_YEAR | III_YEAR | IV_YEAR
ROMAN_TO_YEAR_GROUP = {
    'I': 'I_YEAR',
    'II': 'II_YEAR',
    'III': 'III_YEAR',
    'IV': 'IV_YEAR',
}


# ── Utilities ────────────────────────────────────────────────

def cell_text(cell):
    return cell.text.strip()


def normalize_room(room):
    """Remove spaces and uppercase: 'E- 402' -> 'E-402', 'D 506' -> 'D-506'."""
    if not room:
        return None
    r = re.sub(r'\s+', '', room.upper())
    r = re.sub(r'^([A-Z])(\d)', r'\1-\2', r)
    return r


def is_lunch_cell(text):
    """Detect the LUNCH column — vertical text like 'L U N C H'."""
    cleaned = re.sub(r'\s+', '', text).upper()
    return 'LUNCH' in cleaned


def parse_time(raw):
    raw = raw.strip().replace('.', ':')
    m = re.search(r'(\d{1,2}):(\d{2})\s*(AM|PM)', raw, re.IGNORECASE)
    if not m:
        return None
    hour, minute, period = int(m.group(1)), int(m.group(2)), m.group(3).upper()
    if period == 'PM' and hour != 12:
        hour += 12
    if period == 'AM' and hour == 12:
        hour = 0
    return '%02d:%02d' % (hour, minute)


# ── Room Field Parser ────────────────────────────────────────

def parse_room_field(room_str):
    """
    Handles all room field formats from course tables:
      'E-501'              -> [('ALL', 'E-501')]
      'E-501 E-503(Thu)'   -> [('ALL', 'E-501'), ('THURSDAY', 'E-503')]
      'E-503(Tue) E-403(Thu)' -> [('TUESDAY','E-503'), ('THURSDAY','E-403')]
      'D 506 & 510'        -> [('ALL','D-506'), ('ALL','D-510')]
      'B-403 / 405'        -> [('ALL','B-403'), ('ALL','B-405')]
    """
    if not room_str:
        return []

    results = []
    text = room_str.upper().strip()
    primary_pattern = re.compile(r'([A-Z])\s*-?\s*(\d{3})\s*(?:\(([A-Za-z]{3})\))?')
    last_block_letter = None
    pos = 0

    while pos < len(text):
        m = primary_pattern.match(text, pos)
        if m:
            block, number, day_abbr = m.group(1), m.group(2), m.group(3)
            room = normalize_room('%s-%s' % (block, number))
            last_block_letter = block
            if day_abbr:
                full_day = DAY_ABBR_MAP.get(day_abbr[:3])
                results.append((full_day or 'ALL', room))
            else:
                results.append(('ALL', room))
            pos = m.end()
            continue

        shared_m = re.match(r'\s*[&/]\s*(\d{3})', text[pos:])
        if shared_m and last_block_letter:
            room = normalize_room('%s-%s' % (last_block_letter, shared_m.group(1)))
            results.append(('ALL', room))
            pos += shared_m.end()
            continue

        pos += 1

    return results


def build_room_map(room_str):
    room_map = {}
    for day_key, room in parse_room_field(room_str):
        room_map.setdefault(day_key, []).append(room)
    return room_map


def get_rooms_for_day(room_map, day):
    return room_map.get(day) or room_map.get('ALL') or []


# ── Table Classification ─────────────────────────────────────

def get_unique_cells(row):
    seen = set()
    result = []
    for cell in row.cells:
        if id(cell) not in seen:
            seen.add(id(cell))
            result.append(cell)
    return result


def is_course_table(table):
    if not table.rows:
        return False
    headers = ' '.join(cell_text(c) for c in get_unique_cells(table.rows[0])).upper()
    return 'COURSE CODE' in headers and 'ROOM' in headers


def is_timetable(table):
    if not table.rows:
        return False
    header_text = ' '.join(cell_text(c) for c in get_unique_cells(table.rows[0])).upper()
    has_time = bool(re.search(r'\d{1,2}[\.:]\d{2}\s*(AM|PM)', header_text, re.IGNORECASE))
    has_day_col = 'TIME' in header_text or 'DAY' in header_text
    return has_time and has_day_col


# ── Section Metadata Extraction ──────────────────────────────

def extract_section_meta(paragraphs):
    """
    Reads class metadata from the paragraph block before each timetable table.
    Extracts branch, section letter, and year -> year_group.
    year_group uses same values as excel_parser: I_YEAR | II_YEAR | III_YEAR | IV_YEAR.
    """
    combined = ' '.join(paragraphs)

    branch_m = re.search(
        r'Branch\s*[:\-]\s*([A-Za-z0-9&\-\(\), ]+?)(?=Programme|Regulation|Section|Class|$)',
        combined
    )
    section_m = re.search(r'Section\s*[:\-]\s*([A-Z])', combined)
    year_m = re.search(r'Class\s*[:\-]\s*(I{1,3}V?|IV)\s*Year', combined, re.IGNORECASE)

    branch = branch_m.group(1).strip() if branch_m else 'UNKNOWN'
    section = section_m.group(1) if section_m else '?'
    roman = year_m.group(1).upper() if year_m else 'III'
    year_group = ROMAN_TO_YEAR_GROUP.get(roman, 'II_YEAR')

    return {
        'branch': branch,
        'section': section,
        'year_group': year_group,
        'class_name': '%s-%s' % (branch, section),
    }


# ── Course Table → Lab Lookup ────────────────────────────────

def build_lab_lookup(course_table):
    """
    Builds {short_name -> room_map} from the course table.
    Only rows containing LAB or Laboratory are included.
    Handles both '(WT Lab)' style short names and '(AECS)' acronym style.
    """
    lookup = {}

    for row in course_table.rows[1:]:
        cells = get_unique_cells(row)
        if len(cells) < 3:
            continue

        name_col = cell_text(cells[1])
        room_col = cell_text(cells[2])

        if 'LAB' not in name_col.upper() and 'LABORATOR' not in name_col.upper():
            continue

        room_map = build_room_map(room_col)
        if not room_map:
            continue

        # Prefer the parenthesised short name e.g. '(WT Lab)' or '(BDC Lab)'
        short_m = re.search(r'\(([^)]+(?:Lab|Laboratory)[^)]*)\)', name_col, re.IGNORECASE)
        if short_m:
            short_name = re.sub(r'\s+', ' ', short_m.group(1).strip().upper())
            lookup[short_name] = room_map
        else:
            # Fall back to acronym e.g. '(AECS)' -> adds 'AECS' and 'AECS LAB'
            acronym_m = re.search(r'\(([A-Z]{2,})\)', name_col)
            if acronym_m:
                acronym = acronym_m.group(1)
                lookup[acronym] = room_map
                lookup[acronym + ' LAB'] = room_map

    return lookup


def resolve_lab_cell(cell_text_val, lab_lookup, day):
    """
    Given a timetable cell like 'BDC LAB / WT LAB', returns a list of
    (lab_name, room_number) pairs — one per lab in split-batch slots.
    """
    if 'LAB' not in cell_text_val.upper():
        return []

    results = []
    parts = [p.strip() for p in re.split(r'/', cell_text_val)]

    for part in parts:
        part_upper = part.upper().strip()
        room_map = lab_lookup.get(part_upper)

        if room_map is None:
            for key, rmap in lab_lookup.items():
                if part_upper in key or key in part_upper:
                    room_map = rmap
                    break

        if room_map is None:
            continue

        rooms = get_rooms_for_day(room_map, day)
        for room in rooms:
            if room:
                results.append((part_upper, normalize_room(room)))

    return results


# ── Slot Time Parser ─────────────────────────────────────────

def parse_slot_times(header_row):
    """Reads actual clock times from timetable header row by column index."""
    slot_times = {}
    for i, cell in enumerate(header_row.cells):
        text = cell_text(cell)
        times = re.findall(r'\d{1,2}[\.:]\d{2}\s*(?:AM|PM)', text, re.IGNORECASE)
        if len(times) >= 2:
            start = parse_time(times[0])
            end = parse_time(times[1])
            if start and end:
                slot_times[i] = (start, end)
    return slot_times


# ── Session Extractor ────────────────────────────────────────

def _extract_lab_sessions(tt_table, course_table, meta,
                           sessions, labs_found, warnings, source_file):
    lab_lookup = build_lab_lookup(course_table)
    if not lab_lookup:
        warnings.append('No lab entries found in course table for %s' % meta.get('class_name'))
        return

    slot_times = parse_slot_times(tt_table.rows[0])
    if not slot_times:
        warnings.append('Could not parse slot times for %s' % meta.get('class_name'))
        return

    for row in tt_table.rows[1:]:
        raw_cells = row.cells
        if not raw_cells:
            continue

        day_raw = cell_text(raw_cells[0]).upper().strip()
        day = DAY_MAP.get(day_raw) or DAY_ABBR_MAP.get(day_raw[:3])
        if not day:
            continue

        seen_ids = set()

        for col_idx, cell in enumerate(raw_cells):
            if col_idx == 0:
                continue

            cid = id(cell)
            if cid in seen_ids:
                continue
            seen_ids.add(cid)

            text = cell_text(cell)
            if not text or is_lunch_cell(text):
                continue

            span_cols = [j for j, c in enumerate(raw_cells) if id(c) == cid]
            covered = [slot_times[c] for c in span_cols if c in slot_times]
            if not covered:
                continue

            start_time = min(t[0] for t in covered)
            end_time = max(t[1] for t in covered)

            lab_rooms = resolve_lab_cell(text, lab_lookup, day)
            if not lab_rooms:
                continue

            for lab_name, room in lab_rooms:
                labs_found.add(room)
                sessions.append({
                    'room_number':  room,
                    'day_of_week':  day,
                    'start_time':   start_time,
                    'end_time':     end_time,
                    'class_name':   meta.get('class_name', ''),
                    'subject':      lab_name,
                    'session_type': 'LAB',
                    # year_group from paragraph metadata, not cell text.
                    # Uses same values as excel_parser: I_YEAR|II_YEAR|III_YEAR|IV_YEAR
                    'year_group':   meta.get('year_group', 'II_YEAR'),
                    'source_file':  source_file,
                })


def _get_table_for_element(doc, xml_element):
    for table in doc.tables:
        if table._element is xml_element:
            return table
    return None


# ── Main Entry Point ─────────────────────────────────────────

def parse_word(filepath, source_file):
    doc = Document(filepath)

    sessions = []
    warnings = []
    labs_found = set()

    para_buffer = []
    pending_tt = None

    for block in doc.element.body:
        tag = block.tag.split('}')[-1]

        if tag == 'p':
            texts = [n.text or '' for n in block.iter() if n.tag == qn('w:t')]
            text = ''.join(texts).strip()
            if text:
                para_buffer.append(text)

        elif tag == 'tbl':
            table = _get_table_for_element(doc, block)
            if table is None:
                continue

            if is_course_table(table):
                if pending_tt is not None:
                    tt_table, tt_meta = pending_tt
                    _extract_lab_sessions(
                        tt_table, table, tt_meta,
                        sessions, labs_found, warnings, source_file
                    )
                    pending_tt = None
                para_buffer = []

            elif is_timetable(table):
                meta = extract_section_meta(para_buffer)
                pending_tt = (table, meta)
                para_buffer = []

            else:
                para_buffer = []

    if pending_tt is not None:
        warnings.append(
            'Timetable for %s found no following course table — sessions not extracted.'
            % pending_tt[1].get('class_name', 'unknown')
        )

    return {
        'sessions':   sessions,
        'labs_found': sorted(labs_found),
        'warnings':   warnings,
    }


if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else 'test.docx'
    result = parse_word(path, path.split('/')[-1])
    print('Sessions:  %d' % len(result['sessions']))
    print('Labs found: %s' % result['labs_found'])
    print('Warnings:  %s' % result['warnings'])
    print()
    for s in result['sessions']:
        print('  %-22s %-10s %s-%s  %-8s %-25s [%s]' % (
            s['class_name'], s['day_of_week'],
            s['start_time'], s['end_time'],
            s['room_number'], s['subject'],
            s['year_group'],
        ))
