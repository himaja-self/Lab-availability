"""
db.py — Supabase database layer
All interactions with Supabase REST API go through here.
Uses the service role key (SUPABASE_KEY) for full access.
"""

import os
import json
from datetime import date, datetime
import requests
from dotenv import load_dotenv

# Ensure we load the repo's active env file (`parser/.env`) regardless of cwd.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://zyzsourijufzusqmxozj.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')  # service role key

if not SUPABASE_KEY:
    raise RuntimeError('SUPABASE_KEY environment variable is not set.')


def _headers():
    return {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation',
    }


def _url(table):
    return f'{SUPABASE_URL}/rest/v1/{table}'


def _raise_for_status(resp, context=''):
    if not resp.ok:
        raise RuntimeError(f'Supabase error [{context}] {resp.status_code}: {resp.text}')


# ── Semesters ─────────────────────────────────────────────────

def list_semesters():
    resp = requests.get(
        _url('semesters'),
        headers=_headers(),
        params={'order': 'created_at.desc'},
    )
    _raise_for_status(resp, 'list_semesters')
    return resp.json()


    # If setting active, deactivate all others first
def create_semester(name, start_date, end_date, is_active=False):
    # Avoid logging secrets (SUPABASE_KEY) or internal URLs in normal operation.
    if is_active:
        requests.patch(
            _url('semesters'),
            headers=_headers(),
            params={'is_active': 'eq.true'},
            json={'is_active': False},
        )

    resp = requests.post(
        _url('semesters'),
        headers=_headers(),
        json={
            'name': name,
            'start_date': start_date,
            'end_date': end_date,
            'is_active': is_active,
        },
    )
    _raise_for_status(resp, 'create_semester')
    data = resp.json()
    return data[0] if isinstance(data, list) else data


def delete_semester(semester_id):
    # Cascades to lab_sessions and academic_calendars via FK
    resp = requests.delete(
        _url('semesters'),
        headers=_headers(),
        params={'id': f'eq.{semester_id}'},
    )
    _raise_for_status(resp, 'delete_semester')


def get_active_semester_for_date(query_date):
    """Return the active semester that covers the given date string YYYY-MM-DD."""
    resp = requests.get(
        _url('semesters'),
        headers=_headers(),
        params={
            'is_active': 'eq.true',
            'start_date': f'lte.{query_date}',
            'end_date': f'gte.{query_date}',
            'limit': 1,
        },
    )
    _raise_for_status(resp, 'get_active_semester_for_date')
    data = resp.json()
    return data[0] if data else None


# ── Labs ──────────────────────────────────────────────────────

def list_labs():
    resp = requests.get(
        _url('labs'),
        headers=_headers(),
        params={'order': 'room_number.asc'},
    )
    _raise_for_status(resp, 'list_labs')
    return resp.json()


def list_labs_filtered(block=None):
    params = {
        'order': 'room_number.asc',
        'select': 'id,room_number,has_data',
    }
    if block:
        params['room_number'] = f'like.{block.upper()}-%'
    resp = requests.get(_url('labs'), headers=_headers(), params=params)
    _raise_for_status(resp, 'list_labs_filtered')
    return resp.json()


def get_or_create_lab(room_number):
    """Return lab id, creating the lab row if it doesn't exist."""
    # Try to get existing
    resp = requests.get(
        _url('labs'),
        headers=_headers(),
        params={'room_number': f'eq.{room_number}', 'limit': 1},
    )
    _raise_for_status(resp, 'get_lab')
    data = resp.json()

    if data:
        # Update has_data = true
        lab_id = data[0]['id']
        requests.patch(
            _url('labs'),
            headers=_headers(),
            params={'id': f'eq.{lab_id}'},
            json={'has_data': True},
        )
        return lab_id

    # Create new lab
    resp = requests.post(
        _url('labs'),
        headers=_headers(),
        json={'room_number': room_number, 'has_data': True},
    )
    _raise_for_status(resp, 'create_lab')
    created = resp.json()
    return created[0]['id'] if isinstance(created, list) else created['id']


# ── Lab Sessions ──────────────────────────────────────────────

def upsert_sessions(sessions, lab_id_map, semester_id, source_file):
    """
    Insert parsed sessions into lab_sessions.
    Deletes existing sessions for the same lab+semester+day before inserting
    to avoid duplicates on re-upload.

    Returns (inserted_count, errors_list)
    """
    inserted = 0
    errors = []

    # Group sessions by room_number so we can delete+reinsert per lab
    by_room = {}
    for s in sessions:
        room = s['room_number']
        by_room.setdefault(room, []).append(s)

    for room, room_sessions in by_room.items():
        lab_id = lab_id_map.get(room)
        if not lab_id:
            errors.append(f'No lab_id found for room {room}')
            continue

        # Delete existing sessions for this lab in this semester
        del_resp = requests.delete(
            _url('lab_sessions'),
            headers=_headers(),
            params={
                'lab_id': f'eq.{lab_id}',
                'semester_id': f'eq.{semester_id}',
            },
        )
        if not del_resp.ok:
            errors.append(f'Failed to clear old sessions for {room}: {del_resp.text}')
            continue

        # Build rows to insert
        rows = []
        for s in room_sessions:
            rows.append({
                'lab_id': lab_id,
                'semester_id': semester_id,
                'day_of_week': s['day_of_week'],
                'start_time': s['start_time'],
                'end_time': s['end_time'],
                'class_name': s.get('class_name', ''),
                'subject': s.get('subject', ''),
                'session_type': s.get('session_type', 'OTHER'),
                'year_group': s.get('year_group', 'II_YEAR'),
                'source_file': source_file,
            })

        if not rows:
            continue

        ins_resp = requests.post(
            _url('lab_sessions'),
            headers=_headers(),
            json=rows,
        )
        if ins_resp.ok:
            inserted += len(rows)
        else:
            errors.append(f'Insert failed for {room}: {ins_resp.text}')

    return inserted, errors


# ── Academic Calendar ─────────────────────────────────────────

def list_academic_events(semester_id=None, year_of_study=None):
    params = {'order': 'start_date.asc'}
    if semester_id:
        params['semester_id'] = f'eq.{semester_id}'
    if year_of_study is not None:
        params['year_of_study'] = f'eq.{year_of_study}'
    resp = requests.get(_url('academic_calendars'), headers=_headers(), params=params)
    _raise_for_status(resp, 'list_academic_events')
    return resp.json()


def add_academic_event(semester_id, event_name, start_date, end_date, year_of_study=None,
                       makes_labs_free=False):
    payload = {
        'semester_id': semester_id,
        'event_name': event_name,
        'start_date': start_date,
        'end_date': end_date,
        'makes_labs_free': makes_labs_free,
    }
    if year_of_study is not None:
        payload['year_of_study'] = year_of_study
    resp = requests.post(_url('academic_calendars'), headers=_headers(), json=payload)
    _raise_for_status(resp, 'add_academic_event')
    data = resp.json()
    return data[0] if isinstance(data, list) else data


def upsert_academic_calendar_event(semester_id, year_of_study, event_name, start_date, end_date,
                                   makes_labs_free=False):
    """Upsert one row keyed by (semester_id, year_of_study, event_name)."""
    resp = requests.get(
        _url('academic_calendars'),
        headers=_headers(),
        params={
            'semester_id': f'eq.{semester_id}',
            'year_of_study': f'eq.{year_of_study}',
            'event_name': f'eq.{event_name}',
            'limit': 1,
        },
    )
    _raise_for_status(resp, 'upsert_academic_calendar_event_lookup')
    existing = resp.json()

    payload = {
        'semester_id': semester_id,
        'year_of_study': year_of_study,
        'event_name': event_name,
        'start_date': start_date,
        'end_date': end_date,
        'makes_labs_free': makes_labs_free,
    }

    if existing:
        row_id = existing[0]['id']
        patch = requests.patch(
            _url('academic_calendars'),
            headers=_headers(),
            params={'id': f'eq.{row_id}'},
            json=payload,
        )
        _raise_for_status(patch, 'upsert_academic_calendar_event_patch')
        data = patch.json()
        return data[0] if isinstance(data, list) else data

    post = requests.post(_url('academic_calendars'), headers=_headers(), json=payload)
    _raise_for_status(post, 'upsert_academic_calendar_event_post')
    data = post.json()
    return data[0] if isinstance(data, list) else data


def upsert_academic_calendar_events(semester_id, year_of_study, events):
    """Bulk upsert calendar events for one semester + year group."""
    saved = []
    for ev in events:
        event_name = ev.get('event_name')
        start_date = ev.get('start_date')
        end_date = ev.get('end_date')
        if not event_name or not start_date:
            continue

        makes_labs_free = ev.get('makes_labs_free', False)

        # COMMENCEMENT: single date; end_date mirrors start if omitted
        if event_name == 'COMMENCEMENT':
            end_date = end_date or start_date
            makes_labs_free = False
        elif not end_date:
            # Optional SE-I / SE-II may be omitted when empty
            if event_name in ('SE_I', 'SE_II'):
                continue
            raise ValueError(f'end_date required for event {event_name}')

        row = upsert_academic_calendar_event(
            semester_id=semester_id,
            year_of_study=year_of_study,
            event_name=event_name,
            start_date=start_date,
            end_date=end_date,
            makes_labs_free=makes_labs_free,
        )
        saved.append(row)
    return saved


def delete_academic_event(event_id):
    resp = requests.delete(
        _url('academic_calendars'),
        headers=_headers(),
        params={'id': f'eq.{event_id}'},
    )
    _raise_for_status(resp, 'delete_academic_event')


def get_calendar_events_for_semester(semester_id):
    resp = requests.get(
        _url('academic_calendars'),
        headers=_headers(),
        params={
            'semester_id': f'eq.{semester_id}',
            'order': 'year_of_study.asc,start_date.asc',
        },
    )
    _raise_for_status(resp, 'get_calendar_events_for_semester')
    return resp.json()


def _is_holiday(query_date, semester_id):
    """Return holiday name if date is a holiday, else None. Best-effort if table missing."""
    try:
        resp = requests.get(
            _url('holidays'),
            headers=_headers(),
            params={
                'date': f'eq.{query_date}',
                'semester_id': f'eq.{semester_id}',
                'limit': 1,
            },
        )
        if not resp.ok:
            return None
        data = resp.json()
        return data[0].get('name') if data else None
    except Exception:
        return None


def _freed_years_for_date(query_date, semester_id):
    """
    Return set of year_of_study values (1–4) whose sessions are free on query_date
    per academic calendar rules:
      - before COMMENCEMENT start_date for that year
      - within SE_I / SE_II / SEE_THEORY ranges where makes_labs_free=true
    """
    parsed = datetime.strptime(query_date, '%Y-%m-%d').date()
    events = get_calendar_events_for_semester(semester_id)
    freed = set()

    for year in (1, 2, 3, 4):
        year_events = [e for e in events if e.get('year_of_study') == year]

        for ev in year_events:
            if ev.get('event_name') == 'COMMENCEMENT' and ev.get('start_date'):
                comm = datetime.strptime(ev['start_date'], '%Y-%m-%d').date()
                if parsed < comm:
                    freed.add(year)
                    break

        if year in freed:
            continue

        for ev in year_events:
            if not ev.get('makes_labs_free'):
                continue
            if ev.get('event_name') not in ('SE_I', 'SE_II', 'SEE_THEORY'):
                continue
            if not ev.get('start_date') or not ev.get('end_date'):
                continue
            start = datetime.strptime(ev['start_date'], '%Y-%m-%d').date()
            end = datetime.strptime(ev['end_date'], '%Y-%m-%d').date()
            if start <= parsed <= end:
                freed.add(year)
                break

    return freed


def _calendar_banner_info(query_date, semester_id):
    """
    Build exam_period banner text when academic calendar affects the date.
    Returns (day_status, message) or (None, None).
    """
    parsed = datetime.strptime(query_date, '%Y-%m-%d').date()
    events = get_calendar_events_for_semester(semester_id)
    notes = []

    for year in (1, 2, 3, 4):
        year_events = [e for e in events if e.get('year_of_study') == year]
        for ev in year_events:
            if not ev.get('start_date'):
                continue
            name = ev.get('event_name')
            start = datetime.strptime(ev['start_date'], '%Y-%m-%d').date()
            end_str = ev.get('end_date') or ev['start_date']
            end = datetime.strptime(end_str, '%Y-%m-%d').date()

            if name == 'COMMENCEMENT' and parsed < start:
                notes.append(f'Year {year}: before commencement of classes')
                break
            if ev.get('makes_labs_free') and name in ('SE_I', 'SE_II', 'SEE_THEORY'):
                if start <= parsed <= end:
                    label = name.replace('_', '-')
                    notes.append(f'Year {year}: {label} exam period')
                    break

    if not notes:
        return None, None

    message = (
        'Academic calendar applies today — '
        + '; '.join(notes)
        + '. Sessions for those year groups are not counted as occupying labs.'
    )
    return 'exam_period', message


# ── Availability ──────────────────────────────────────────────

def _years_for_year_group(year_group):
    mapping = {
        'I_YEAR':   {1},
        'II_YEAR':  {2},
        'III_YEAR': {3},
        'IV_YEAR':  {4},
        'II_III_YEAR': {2, 3, 4},  # keep for backwards compat if old data exists
    }
    return mapping.get(year_group, {2, 3, 4})


def _lab_department_label(room_number):
    dash = room_number.find('-')
    if dash > 0:
        return f'{room_number[:dash]} Block'
    return room_number


def get_availability(query_date, start_time, end_time, semester_id=None, block=None):
    """
    Main availability logic.
    Returns dict with available_labs, occupied_labs, no_data_labs, day_status, message.
    """
    parsed_date = datetime.strptime(query_date, '%Y-%m-%d').date()
    day_names = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY']
    day_of_week = day_names[parsed_date.weekday()]

    def _all_free_response(day_status, message, status=None, calendar_note=None):
        all_labs = list_labs_filtered(block=block)
        return {
            'status': status or day_status,
            'day_status': day_status,
            'message': message,
            'date': query_date,
            'day': day_of_week,
            'start_time': start_time,
            'end_time': end_time,
            'available_labs': [
                {
                    'room_number': l['room_number'],
                    'department': _lab_department_label(l['room_number']),
                    'status': 'available',
                }
                for l in all_labs
            ],
            'occupied_labs': [],
            'no_data_labs': [],
            'calendar_note': calendar_note,
        }

    # Step 1 — Sunday
    if parsed_date.weekday() == 6:
        return _all_free_response('sunday', 'No classes on Sundays', status='sunday')

    # Step 2 — Active semester (needed for holiday + calendar checks)
    if not semester_id:
        semester = get_active_semester_for_date(query_date)
        if not semester:
            return {
                'status': 'no_semester',
                'day_status': 'normal',
                'message': 'No active semester found for this date. Please check semester configuration.',
                'date': query_date,
                'day': day_of_week,
                'start_time': start_time,
                'end_time': end_time,
                'available_labs': [],
                'occupied_labs': [],
                'no_data_labs': [],
                'calendar_note': None,
            }
        semester_id = semester['id']

    # Step 2 — Holiday (best-effort; skipped if holidays table absent)
    holiday_name = _is_holiday(query_date, semester_id)
    if holiday_name:
        return _all_free_response(
            'holiday',
            f'This date is a holiday: {holiday_name}. All labs are free.',
            status='holiday',
            calendar_note=holiday_name,
        )

    # Step 5 — Per-year academic calendar frees
    freed_years = _freed_years_for_date(query_date, semester_id)
    all_years_free = freed_years >= {1, 2, 3, 4}
    if all_years_free:
        return _all_free_response(
            'exam_period',
            'Labs are free due to academic calendar (exam / pre-commencement period).',
            status='labs_free',
            calendar_note='Academic calendar',
        )

    # Step 6 — Overlapping lab sessions for this day/time
    resp = requests.get(
        _url('lab_sessions'),
        headers={**_headers(), 'Prefer': 'return=representation'},
        params={
            'semester_id': f'eq.{semester_id}',
            'day_of_week': f'eq.{day_of_week}',
            'start_time': f'lt.{end_time}',
            'end_time': f'gt.{start_time}',
            'select': 'lab_id,class_name,subject,session_type,start_time,end_time,year_group',
        },
    )
    _raise_for_status(resp, 'get_occupied_sessions')
    occupied_sessions = resp.json()

    all_labs = list_labs_filtered(block=block)

    lab_sessions_map = {}
    for s in occupied_sessions:
        ys = _years_for_year_group(s.get('year_group'))
        if ys & freed_years:
            continue
        lab_sessions_map.setdefault(s['lab_id'], []).append(s)

    available_labs = []
    occupied_labs = []
    no_data_labs = []

    for lab in all_labs:
        lab_id = lab['id']
        dept = _lab_department_label(lab['room_number'])

        if not lab.get('has_data'):
            no_data_labs.append({
                'room_number': lab['room_number'],
                'department': dept,
                'status': 'no_data',
            })
            continue

        sessions_for_lab = lab_sessions_map.get(lab_id, [])
        if sessions_for_lab:
            primary = sessions_for_lab[0]
            occupied_labs.append({
                'room_number': lab['room_number'],
                'department': dept,
                'status': 'occupied',
                'occupied_by': primary.get('class_name', ''),
                'start_time': primary.get('start_time'),
                'end_time': primary.get('end_time'),
                'sessions': sessions_for_lab,
            })
        else:
            available_labs.append({
                'room_number': lab['room_number'],
                'department': dept,
                'status': 'available',
            })

    for lab in no_data_labs:
        _notify_missing_data(lab['room_number'])

    day_status = 'normal'
    message = None
    calendar_note = None
    if freed_years:
        banner_status, banner_msg = _calendar_banner_info(query_date, semester_id)
        if banner_status:
            day_status = banner_status
            message = banner_msg
            calendar_note = banner_msg

    return {
        'status': 'ok',
        'day_status': day_status,
        'message': message,
        'date': query_date,
        'day': day_of_week,
        'start_time': start_time,
        'end_time': end_time,
        'available_labs': available_labs,
        'occupied_labs': occupied_labs,
        'no_data_labs': no_data_labs,
        'calendar_note': calendar_note,
    }


def _notify_missing_data(room_number):
    """Create a missing data notification if one doesn't already exist (unread)."""
    # Best-effort: if schema is missing (e.g., related_lab column not added yet),
    # do not break availability responses.
    try:
        # Check for existing unread notification for this lab
        resp = requests.get(
            _url('notifications'),
            headers=_headers(),
            params={
                'type': 'eq.missing_data',
                'related_lab': f'eq.{room_number}',
                'is_read': 'eq.false',
                'limit': 1,
            },
        )
        if resp.ok and resp.json():
            return  # Already notified

        requests.post(
            _url('notifications'),
            headers=_headers(),
            json={
                'message': f'No timetable data found for lab {room_number}. Please upload timetable.',
                'type': 'missing_data',
                'related_lab': room_number,
            },
        )
    except Exception as e:
        # Non-critical path; do not break availability responses.
        print(f'[notifications] missing_data notify skipped for {room_number}: {e}')


# ── Notifications ─────────────────────────────────────────────

def list_notifications():
    resp = requests.get(
        _url('notifications'),
        headers=_headers(),
        params={'order': 'created_at.desc', 'limit': 50},
    )
    _raise_for_status(resp, 'list_notifications')
    return resp.json()


def mark_notification_read(notif_id):
    resp = requests.patch(
        _url('notifications'),
        headers=_headers(),
        params={'id': f'eq.{notif_id}'},
        json={'is_read': True},
    )
    _raise_for_status(resp, 'mark_notification_read')


def mark_all_notifications_read():
    resp = requests.patch(
        _url('notifications'),
        headers=_headers(),
        params={'is_read': 'eq.false'},
        json={'is_read': True},
    )
    _raise_for_status(resp, 'mark_all_notifications_read')


def create_notification(message, notif_type, related_lab=None):
    payload = {'message': message, 'type': notif_type}
    if related_lab:
        payload['related_lab'] = related_lab
    resp = requests.post(_url('notifications'), headers=_headers(), json=payload)
    # Don't raise — notifications are non-critical


# ── Upload History ────────────────────────────────────────────

def log_upload(semester_id, filename, file_type, content_type,
               parse_status, labs_updated, sessions_added,
               warnings, error_message=None, sessions_deleted=0):
    # Best-effort logging: `upload_history` might not exist yet in Supabase.
    try:
        payload = {
            'semester_id': semester_id,
            'filename': filename,
            'file_type': file_type,
            'content_type': content_type,
            'parse_status': parse_status,
            'labs_updated': labs_updated,
            'sessions_added': sessions_added,
            'sessions_deleted': sessions_deleted,
            'warnings': warnings,
        }
        if error_message:
            payload['error_message'] = error_message
        requests.post(_url('upload_history'), headers=_headers(), json=payload)
    except Exception:
        # Non-critical path; ignore failures (missing table, RLS, network, etc.)
        return