"""
Excel Timetable Parser
Handles two formats:
  1. Lab-wise: sheet name = room number (e.g. E-402)
  2. Class-wise: sheet has Time/Day header + course table below
"""

import re
import openpyxl
from openpyxl.utils import column_index_from_string

# ── Constants ────────────────────────────────────────────────
LAB_SHEET_RE = re.compile(r'^[A-Z]-?\s*\d{3}\s*$')

DAY_MAP = {
    'MON': 'MONDAY', 'TUE': 'TUESDAY', 'WED': 'WEDNESDAY',
    'THU': 'THURSDAY', 'FRI': 'FRIDAY', 'SAT': 'SATURDAY',
    'MONDAY': 'MONDAY', 'TUESDAY': 'TUESDAY', 'WEDNESDAY': 'WEDNESDAY',
    'THURSDAY': 'THURSDAY', 'FRIDAY': 'FRIDAY', 'SATURDAY': 'SATURDAY',
}

# Time bands for each year group (slot index 0-5 → start, end)
# Slot indices: 0=I, 1=II, 2=III, 3=IV, 4=V, 5=VI (lunch is skipped in data)
I_YEAR_SLOTS = [
    ('09:00', '10:00'),
    ('10:00', '11:00'),
    ('11:00', '12:00'),
    ('12:40', '13:40'),
    ('13:40', '14:40'),
    ('14:40', '15:40'),
]

II_III_YEAR_SLOTS = [
    ('10:00', '11:00'),
    ('11:00', '12:00'),
    ('12:00', '13:00'),
    ('13:40', '14:40'),
    ('14:40', '15:40'),
    ('15:40', '16:40'),
]


# ── Utility Functions ────────────────────────────────────────

def clean(val):
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def normalize_room(room):
    """Remove spaces, uppercase: 'E- 402' → 'E-402'"""
    if not room:
        return None
    return re.sub(r'\s+', '', room.upper())


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


def detect_year_group(text):
    """Detect year group from session text."""
    t = text.upper()
    # I year sessions start with 'I ' or 'I-' or contain '1ST'
    if re.match(r'^I[\s\-]', t) or '1ST' in t or 'FIRST' in t:
        return 'I_YEAR'
    return 'II_III_YEAR'


def get_slot_times(slot_indices, year_group):
    """
    Given a list of slot indices (0-based) that are merged,
    return (start_time, end_time) covering the full block.
    """
    band = I_YEAR_SLOTS if year_group == 'I_YEAR' else II_III_YEAR_SLOTS
    starts = [band[i][0] for i in slot_indices if i < len(band)]
    ends   = [band[i][1] for i in slot_indices if i < len(band)]
    if not starts:
        return None, None
    return starts[0], ends[-1]


def get_merged_span(ws, row, col):
    """
    Given a cell (row, col), return the column span
    if it belongs to a merged cell range.
    Returns (min_col, max_col) or (col, col) if not merged.
    """
    for merge in ws.merged_cells.ranges:
        if merge.min_row <= row <= merge.max_row and \
           merge.min_col <= col <= merge.max_col:
            return merge.min_col, merge.max_col
    return col, col


# ── Lab-Wise Excel Parser ────────────────────────────────────

def parse_lab_wise_sheet(ws, room_number, source_file):
    """
    Parse a single lab-wise sheet.
    Returns list of session dicts ready for DB insertion.
    """
    sessions = []

    # Find the header row (contains 'I', 'II', 'III' slot headers)
    header_row = None
    time_band_rows = []

    for row_idx in range(1, min(20, ws.max_row + 1)):
        row_vals = [clean(ws.cell(row_idx, c).value) for c in range(1, 15)]
        non_none = [v for v in row_vals if v]

        # Header row has slot labels I, II, III, IV, V, VI
        if 'I' in non_none and 'II' in non_none and 'III' in non_none:
            header_row = row_idx
            # Next 1-2 rows are time band rows
            for tb_row in range(row_idx + 1, row_idx + 3):
                tb_vals = [clean(ws.cell(tb_row, c).value) for c in range(1, 15)]
                # Time band rows contain time strings like '10:00-11:00' or '10:00'
                time_vals = [v for v in tb_vals if v and re.search(r'\d{1,2}:\d{2}', v)]
                if time_vals:
                    time_band_rows.append(tb_row)
            break

    if not header_row:
        return sessions  # Can't parse this sheet

    # Identify slot columns from header row
    # Slots are in columns where header = I, II, III, IV, V, VI
    slot_cols = {}  # slot_label → col_index
    slot_order = []
    for col in range(1, ws.max_column + 1):
        val = clean(ws.cell(header_row, col).value)
        if val in ('I', 'II', 'III', 'IV', 'V', 'VI'):
            slot_cols[val] = col
            slot_order.append((col, val))

    if not slot_cols:
        return sessions

    # Sort slot_order by column
    slot_order.sort(key=lambda x: x[0])

    # Map slot label to 0-based index
    slot_label_to_idx = {label: idx for idx, (col, label) in enumerate(slot_order)}

    # Find day rows (rows after time bands that start with a day name)
    day_rows = []
    search_start = (time_band_rows[-1] + 1) if time_band_rows else (header_row + 2)

    for row_idx in range(search_start, ws.max_row + 1):
        cell_val = clean(ws.cell(row_idx, 1).value)
        if not cell_val:
            # Also check col 2
            cell_val = clean(ws.cell(row_idx, 2).value)
        if cell_val:
            day_key = cell_val.upper()[:3]
            if day_key in DAY_MAP:
                day_rows.append((row_idx, DAY_MAP[day_key]))

    # Parse each day row
    for row_idx, day_name in day_rows:
        # Track which slot cols we've already processed (for merge detection)
        processed_cols = set()

        for col, slot_label in slot_order:
            if col in processed_cols:
                continue

            cell = ws.cell(row_idx, col)
            val = clean(cell.value)

            if not val:
                continue

            # Check if this cell is part of a merged range
            min_col, max_col = get_merged_span(ws, row_idx, col)

            # Find all slot labels covered by this merge
            covered_slot_labels = [
                lbl for c, lbl in slot_order
                if min_col <= c <= max_col
            ]
            covered_slot_indices = [slot_label_to_idx[lbl] for lbl in covered_slot_labels]

            # Mark covered columns as processed
            for c, lbl in slot_order:
                if min_col <= c <= max_col:
                    processed_cols.add(c)

            # Determine year group and times
            year_group = detect_year_group(val)
            start_time, end_time = get_slot_times(covered_slot_indices, year_group)

            if not start_time:
                continue

            sessions.append({
                'room_number': normalize_room(room_number),
                'day_of_week': day_name,
                'start_time': start_time,
                'end_time': end_time,
                'class_name': val,
                'subject': val,
                'session_type': classify_session(val),
                'year_group': year_group,
                'source_file': source_file,
            })

    return sessions


def parse_lab_wise_excel(wb, source_file):
    """Parse all lab-wise sheets in a workbook."""
    all_sessions = []
    parsed_sheets = []
    skipped_sheets = []

    for sheet_name in wb.sheetnames:
        if LAB_SHEET_RE.match(sheet_name.strip()):
            ws = wb[sheet_name]
            room = normalize_room(sheet_name.strip())
            sessions = parse_lab_wise_sheet(ws, room, source_file)
            all_sessions.extend(sessions)
            parsed_sheets.append(sheet_name)
        else:
            skipped_sheets.append(sheet_name)

    return all_sessions, parsed_sheets, skipped_sheets


# ── Class-Wise Excel Parser ──────────────────────────────────

def is_class_wise_sheet(ws):
    """
    Detect if a sheet is a class-wise timetable.
    Looks for 'Time' or 'Day' in header area and a course table below.
    """
    for row_idx in range(1, min(15, ws.max_row + 1)):
        for col in range(1, min(10, ws.max_column + 1)):
            val = clean(ws.cell(row_idx, col).value)
            if val and ('TIME' in val.upper() or 'COURSE' in val.upper() or 'SUBJECT' in val.upper()):
                return True
    return False


def parse_class_wise_excel(wb, source_file):
    """
    Parse class-wise Excel sheets.
    Returns sessions derived from class timetable → lab room mapping.
    """
    # For now, delegate to same logic as Word class-wise parser
    # Most class-wise Excel files follow similar table structure
    all_sessions = []
    warnings = []

    for sheet_name in wb.sheetnames:
        if LAB_SHEET_RE.match(sheet_name.strip()):
            continue  # Already handled by lab-wise parser

        ws = wb[sheet_name]
        if not is_class_wise_sheet(ws):
            continue

        # Extract timetable and course table from sheet
        # This is complex — flag as warning for now
        warnings.append(
            f"Sheet '{sheet_name}' appears to be class-wise format. "
            "Manual review recommended."
        )

    return all_sessions, warnings


# ── Main Excel Parse Entry Point ─────────────────────────────

def parse_excel(filepath, source_file):
    """
    Main entry point for Excel parsing.
    Auto-detects lab-wise vs class-wise content.
    Returns dict with sessions and metadata.
    """
    wb = openpyxl.load_workbook(filepath, data_only=True)

    result = {
        'sessions': [],
        'labs_found': [],
        'parsed_sheets': [],
        'skipped_sheets': [],
        'warnings': [],
        'content_types_found': [],
    }

    # Step 1: Parse lab-wise sheets
    lab_sessions, parsed, skipped = parse_lab_wise_excel(wb, source_file)
    if lab_sessions:
        result['sessions'].extend(lab_sessions)
        result['parsed_sheets'].extend(parsed)
        result['content_types_found'].append('lab_wise')
        result['labs_found'] = list({s['room_number'] for s in lab_sessions})

    # Step 2: Check remaining sheets for class-wise format
    class_sessions, class_warnings = parse_class_wise_excel(wb, source_file)
    if class_sessions:
        result['sessions'].extend(class_sessions)
        result['content_types_found'].append('class_wise')
    result['warnings'].extend(class_warnings)
    result['skipped_sheets'].extend(skipped)

    return result