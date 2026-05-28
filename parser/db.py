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

load_dotenv()

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
    print(f"DEBUG URL: {_url('semesters')}")
    print(f"DEBUG KEY: {SUPABASE_KEY[:20] if SUPABASE_KEY else 'NONE'}")
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
                'year_group': s.get('year_group', 'II_III_YEAR'),
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


# ── Holidays ──────────────────────────────────────────────────

def list_holidays(semester_id=None):
    params = {'order': 'date.asc'}
    if semester_id:
        params['semester_id'] = f'eq.{semester_id}'
    resp = requests.get(_url('holidays'), headers=_headers(), params=params)
    _raise_for_status(resp, 'list_holidays')
    return resp.json()


def add_holiday(date, name, semester_id):
    resp = requests.post(
        _url('holidays'),
        headers=_headers(),
        json={'date': date, 'name': name, 'semester_id': semester_id},
    )
    _raise_for_status(resp, 'add_holiday')
    data = resp.json()
    return data[0] if isinstance(data, list) else data


def delete_holiday(holiday_id):
    resp = requests.delete(
        _url('holidays'),
        headers=_headers(),
        params={'id': f'eq.{holiday_id}'},
    )
    _raise_for_status(resp, 'delete_holiday')


def is_holiday(query_date, semester_id):
    """Return holiday name if date is a holiday, else None."""
    resp = requests.get(
        _url('holidays'),
        headers=_headers(),
        params={
            'date': f'eq.{query_date}',
            'semester_id': f'eq.{semester_id}',
            'limit': 1,
        },
    )
    _raise_for_status(resp, 'is_holiday')
    data = resp.json()
    return data[0]['name'] if data else None


# ── Academic Calendar ─────────────────────────────────────────

def list_academic_events(semester_id=None):
    params = {'order': 'start_date.asc'}
    if semester_id:
        params['semester_id'] = f'eq.{semester_id}'
    resp = requests.get(_url('academic_calendars'), headers=_headers(), params=params)
    _raise_for_status(resp, 'list_academic_events')
    return resp.json()


def add_academic_event(semester_id, event_name, start_date, end_date, year_of_study=None, makes_labs_free=False):
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


def delete_academic_event(event_id):
    resp = requests.delete(
        _url('academic_calendars'),
        headers=_headers(),
        params={'id': f'eq.{event_id}'},
    )
    _raise_for_status(resp, 'delete_academic_event')


def get_calendar_events_for_date(query_date, semester_id):
    """Return all academic calendar events that cover the given date."""
    resp = requests.get(
        _url('academic_calendars'),
        headers=_headers(),
        params={
            'semester_id': f'eq.{semester_id}',
            'start_date': f'lte.{query_date}',
            'end_date': f'gte.{query_date}',
        },
    )
    _raise_for_status(resp, 'get_calendar_events_for_date')
    return resp.json()


# ── Availability ──────────────────────────────────────────────

def get_availability(query_date, start_time, end_time, semester_id=None):
    """
    Main availability logic.
    Returns dict with:
      - available_labs: list of free labs
      - occupied_labs: list of occupied labs with session details
      - no_data_labs: list of labs with no timetable
      - status: 'ok' | 'holiday' | 'sunday' | 'no_semester' | 'labs_free'
      - message: human-readable explanation
    """
    # 1. Check if Sunday
    parsed_date = datetime.strptime(query_date, '%Y-%m-%d').date()
    if parsed_date.weekday() == 6:  # Sunday
        all_labs = list_labs()
        return {
            'status': 'sunday',
            'message': 'It is a Sunday. All labs are free.',
            'available_labs': [{'room_number': l['room_number'], 'id': l['id']} for l in all_labs],
            'occupied_labs': [],
            'no_data_labs': [],
        }

    # 2. Find active semester
    if not semester_id:
        semester = get_active_semester_for_date(query_date)
        if not semester:
            return {
                'status': 'no_semester',
                'message': 'No active semester found for this date. Please check semester configuration.',
                'available_labs': [],
                'occupied_labs': [],
                'no_data_labs': [],
            }
        semester_id = semester['id']

    # 3. Check holiday
    holiday_name = is_holiday(query_date, semester_id)
    if holiday_name:
        all_labs = list_labs()
        return {
            'status': 'holiday',
            'message': f'This date is a holiday: {holiday_name}. All labs are free.',
            'available_labs': [{'room_number': l['room_number'], 'id': l['id']} for l in all_labs],
            'occupied_labs': [],
            'no_data_labs': [],
        }

    # 4. Check academic calendar — are labs free on this date?
    calendar_events = get_calendar_events_for_date(query_date, semester_id)
    free_events = [e for e in calendar_events if e.get('makes_labs_free')]

    if free_events:
        event_names = ', '.join(e['event_name'] for e in free_events)
        all_labs = list_labs()
        return {
            'status': 'labs_free',
            'message': f'Labs are free due to: {event_names}.',
            'available_labs': [{'room_number': l['room_number'], 'id': l['id']} for l in all_labs],
            'occupied_labs': [],
            'no_data_labs': [],
            'calendar_events': [e['event_name'] for e in free_events],
        }

    # 5. Map date to day of week
    day_names = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY']
    day_of_week = day_names[parsed_date.weekday()]

    if day_of_week == 'SUNDAY':
        all_labs = list_labs()
        return {
            'status': 'sunday',
            'message': 'It is a Sunday. All labs are free.',
            'available_labs': [{'room_number': l['room_number'], 'id': l['id']} for l in all_labs],
            'occupied_labs': [],
            'no_data_labs': [],
        }

    # 6. Fetch occupied sessions that overlap with the requested window
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

    # 7. Get all labs
    all_labs = list_labs()

    # Build occupied lab_id set
    occupied_lab_ids = {s['lab_id'] for s in occupied_sessions}

    # Map lab_id → session details
    lab_sessions_map = {}
    for s in occupied_sessions:
        lab_sessions_map.setdefault(s['lab_id'], []).append(s)

    available_labs = []
    occupied_labs = []
    no_data_labs = []

    for lab in all_labs:
        lab_id = lab['id']
        if not lab.get('has_data'):
            no_data_labs.append({
                'room_number': lab['room_number'],
                'id': lab_id,
                'message': 'No timetable data uploaded for this lab.',
            })
        elif lab_id in occupied_lab_ids:
            sessions_for_lab = lab_sessions_map.get(lab_id, [])
            occupied_labs.append({
                'room_number': lab['room_number'],
                'id': lab_id,
                'sessions': sessions_for_lab,
            })
        else:
            available_labs.append({
                'room_number': lab['room_number'],
                'id': lab_id,
            })

    # 8. If there are labs with no data, notify admin (deduplicated)
    for lab in no_data_labs:
        _notify_missing_data(lab['room_number'])

    return {
        'status': 'ok',
        'date': query_date,
        'day_of_week': day_of_week,
        'start_time': start_time,
        'end_time': end_time,
        'available_labs': available_labs,
        'occupied_labs': occupied_labs,
        'no_data_labs': no_data_labs,
        'calendar_events': [e['event_name'] for e in calendar_events],
    }


def _notify_missing_data(room_number):
    """Create a missing data notification if one doesn't already exist (unread)."""
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
    resp = requests.post(_url('upload_history'), headers=_headers(), json=payload)
    # Non-critical, don't raise