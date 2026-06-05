"""
Lab Occupancy System — Flask API
Routes:
  POST /api/parse/excel        - Upload + parse Excel timetable
  POST /api/parse/word         - Upload + parse Word timetable
  POST /api/semesters          - Create a semester
  GET  /api/semesters          - List all semesters
  DELETE /api/semesters/<id>   - Delete a semester and all its data
  POST /api/academic-calendar  - Add an academic calendar event
  GET  /api/academic-calendar  - List events for a semester
  DELETE /api/academic-calendar/<id> - Delete an event
  GET  /api/availability       - Check lab availability
  GET  /api/labs               - List all labs
  GET  /api/notifications      - List notifications (admin)
  PATCH /api/notifications/<id>/read - Mark notification as read
  GET  /api/health             - Health check
"""

import os
import tempfile
import traceback
from datetime import datetime

from flask import Flask, request, jsonify
from flask_cors import CORS

from db import (
    get_or_create_lab,
    upsert_sessions,
    create_semester,
    list_semesters,
    delete_semester,
    add_academic_event,
    list_academic_events,
    upsert_academic_calendar_events,
    delete_academic_event,
    get_availability,
    list_labs,
    list_notifications,
    mark_notification_read,
    mark_all_notifications_read,
    log_upload,
    create_notification,
)
from excel.excel_parser import parse_excel
from word.word_parser import parse_word

app = Flask(__name__)
CORS(app)

# ── Health ────────────────────────────────────────────────────

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'timestamp': datetime.utcnow().isoformat()})


# ── Semesters ─────────────────────────────────────────────────

@app.route('/api/semesters', methods=['GET'])
def get_semesters():
    try:
        semesters = list_semesters()
        return jsonify(semesters)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/semesters', methods=['POST'])
def post_semester():
    data = request.json
    required = ['name', 'start_date', 'end_date']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'Missing field: {field}'}), 400
    try:
        semester = create_semester(
            name=data['name'],
            start_date=data['start_date'],
            end_date=data['end_date'],
            is_active=data.get('is_active', False),
        )
        return jsonify(semester), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/semesters/<semester_id>', methods=['DELETE'])
def del_semester(semester_id):
    try:
        delete_semester(semester_id)
        return jsonify({'message': 'Semester and all related data deleted.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Academic Calendar ─────────────────────────────────────────

@app.route('/api/academic-calendar', methods=['GET'])
def get_academic_events():
    semester_id = request.args.get('semester_id')
    year_of_study = request.args.get('year_of_study')
    try:
        year = int(year_of_study) if year_of_study else None
        events = list_academic_events(semester_id, year_of_study=year)
        return jsonify(events)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/academic-calendar', methods=['POST'])
def post_academic_event():
    data = request.json or {}

    # Bulk upsert: { semester_id, year_of_study, events: [...] }
    if 'events' in data:
        semester_id = data.get('semester_id')
        year_of_study = data.get('year_of_study')
        events = data.get('events')
        if not semester_id or year_of_study is None or not isinstance(events, list):
            return jsonify({'error': 'semester_id, year_of_study, and events[] are required'}), 400
        try:
            saved = upsert_academic_calendar_events(semester_id, int(year_of_study), events)
            return jsonify({'saved': saved, 'count': len(saved)}), 200
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # Single event (legacy)
    required = ['semester_id', 'event_name', 'start_date', 'end_date']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'Missing field: {field}'}), 400
    try:
        event = add_academic_event(
            semester_id=data['semester_id'],
            event_name=data['event_name'],
            start_date=data['start_date'],
            end_date=data['end_date'],
            year_of_study=data.get('year_of_study'),
            makes_labs_free=data.get('makes_labs_free', False),
        )
        return jsonify(event), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/academic-calendar/<event_id>', methods=['DELETE'])
def del_academic_event(event_id):
    try:
        delete_academic_event(event_id)
        return jsonify({'message': 'Event deleted.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── File Upload + Parse ───────────────────────────────────────

def handle_upload(parse_fn, file_ext):
    """Shared logic for Excel and Word upload routes."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded. Use multipart/form-data with key "file".'}), 400

    semester_id = request.form.get('semester_id')
    if not semester_id:
        return jsonify({'error': 'semester_id is required in form data.'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'Empty filename.'}), 400

    # Save to temp file
    suffix = f'.{file_ext}'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        result = parse_fn(tmp_path, file.filename)
        sessions = result.get('sessions', [])
        warnings = result.get('warnings', [])
        labs_found = result.get('labs_found', [])

        inserted = 0
        errors = []

        if sessions:
            # Ensure all labs exist in DB
            lab_id_map = {}
            for room in labs_found:
                lab_id = get_or_create_lab(room)
                lab_id_map[room] = lab_id

            # Insert sessions
            inserted, errors = upsert_sessions(sessions, lab_id_map, semester_id, file.filename)

        # Log the upload
        parse_status = 'success'
        if errors and inserted == 0:
            parse_status = 'failed'
        elif errors:
            parse_status = 'partial'
        elif not sessions:
            parse_status = 'failed'
            warnings.append('No sessions found in file. Check file format.')

        log_upload(
            semester_id=semester_id,
            filename=file.filename,
            file_type=file_ext,
            content_type=result.get('content_types_found', ['unknown'])[0] if result.get('content_types_found') else 'unknown',
            parse_status=parse_status,
            labs_updated=labs_found,
            sessions_added=inserted,
            warnings=warnings,
            error_message='; '.join(errors) if errors else None,
        )

        # Create success/error notification
        if parse_status == 'success':
            create_notification(
                message=f"File '{file.filename}' parsed successfully. {inserted} sessions added for {len(labs_found)} lab(s).",
                notif_type='upload_success',
            )
        elif parse_status == 'partial':
            create_notification(
                message=f"File '{file.filename}' partially parsed. {inserted} sessions added. {len(errors)} errors.",
                notif_type='upload_partial',
            )
        else:
            create_notification(
                message=f"File '{file.filename}' failed to parse. Check format.",
                notif_type='upload_error',
            )

        hint = None
        if any('lab_sessions_year_group_check' in e for e in errors):
            hint = (
                'Supabase year_group constraint is outdated. Run '
                'supabase/lab_sessions_year_group.sql in the SQL Editor, then re-upload.'
            )

        return jsonify({
            'status': parse_status,
            'sessions_inserted': inserted,
            'labs_found': labs_found,
            'warnings': warnings,
            'errors': errors,
            'hint': hint,
        })

    except Exception as e:
        traceback.print_exc()
        log_upload(
            semester_id=semester_id,
            filename=file.filename,
            file_type=file_ext,
            content_type='unknown',
            parse_status='failed',
            labs_updated=[],
            sessions_added=0,
            warnings=[],
            error_message=str(e),
        )
        create_notification(
            message=f"File '{file.filename}' failed to parse: {str(e)}",
            notif_type='upload_error',
        )
        return jsonify({'error': str(e)}), 500
    finally:
        # On Windows, libraries like openpyxl can keep file handles open briefly.
        # Best-effort cleanup; don't fail the API response due to temp delete issues.
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@app.route('/api/parse/excel', methods=['POST'])
def upload_excel():
    return handle_upload(parse_excel, 'xlsx')


@app.route('/api/parse/word', methods=['POST'])
def upload_word():
    return handle_upload(parse_word, 'docx')


# ── Availability ──────────────────────────────────────────────

@app.route('/api/availability', methods=['GET'])
def check_availability():
    """
    Query params:
      date        - YYYY-MM-DD (required)
      start_time  - HH:MM in 24h (required)
      end_time    - HH:MM in 24h (required)
      semester_id    - UUID (optional, uses active semester if omitted)
      block          - A|B|C|D|E|P (optional, filters labs by room prefix)
    """
    date = request.args.get('date')
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    semester_id = request.args.get('semester_id')
    block = request.args.get('block')

    if not date or not start_time or not end_time:
        return jsonify({'error': 'date, start_time, end_time are required'}), 400

    # Basic format validation
    try:
        datetime.strptime(date, '%Y-%m-%d')
        datetime.strptime(start_time, '%H:%M')
        datetime.strptime(end_time, '%H:%M')
    except ValueError as e:
        return jsonify({'error': f'Invalid format: {e}'}), 400

    if start_time >= end_time:
        return jsonify({'error': 'start_time must be before end_time'}), 400

    try:
        result = get_availability(date, start_time, end_time, semester_id, block=block)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ── Labs ──────────────────────────────────────────────────────

@app.route('/api/labs', methods=['GET'])
def get_labs():
    try:
        labs = list_labs()
        return jsonify(labs)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Notifications ─────────────────────────────────────────────

@app.route('/api/notifications', methods=['GET'])
def get_notifications():
    try:
        notifications = list_notifications()
        return jsonify(notifications)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/notifications/read-all', methods=['PATCH'])
def read_all_notifications():
    try:
        mark_all_notifications_read()
        return jsonify({'message': 'All notifications marked as read.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/notifications/<notif_id>/read', methods=['PATCH'])
def read_notification(notif_id):
    try:
        mark_notification_read(notif_id)
        return jsonify({'message': 'Marked as read.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Run ───────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, port=port)