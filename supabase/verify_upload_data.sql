-- =============================================================================
-- Lab Occupancy — data verification (run in Supabase SQL Editor)
-- Joins lab_sessions → labs to show room_number from lab_id
-- =============================================================================

-- ── 1. Quick summary ─────────────────────────────────────────────────────────

SELECT 'semesters' AS table_name, COUNT(*) AS row_count FROM semesters
UNION ALL
SELECT 'labs', COUNT(*) FROM labs
UNION ALL
SELECT 'lab_sessions', COUNT(*) FROM lab_sessions
UNION ALL
SELECT 'academic_calendars', COUNT(*) FROM academic_calendars
UNION ALL
SELECT 'notifications', COUNT(*) FROM notifications;


-- ── 2. Active semester(s) ───────────────────────────────────────────────────

SELECT
  id,
  name,
  start_date,
  end_date,
  is_active,
  created_at
FROM semesters
ORDER BY is_active DESC, start_date DESC;


-- ── 3. Labs with timetable data flag ─────────────────────────────────────────

SELECT
  id AS lab_id,
  room_number,
  has_data
FROM labs
ORDER BY room_number;


-- ── 4. Sessions per lab (room_number via join) ───────────────────────────────
-- Expected after full Excel upload: ~108 sessions across 14 labs
-- (E-317, E-330, E-331, E-401, E-402, E-403, E-417, E-430,
--  E-501, E-502, E-503, E-504, P-401, P-402)

SELECT
  l.room_number,
  l.has_data,
  s.semester_id,
  sem.name AS semester_name,
  COUNT(*) AS session_count
FROM lab_sessions s
JOIN labs l ON l.id = s.lab_id
LEFT JOIN semesters sem ON sem.id = s.semester_id
GROUP BY l.room_number, l.has_data, s.semester_id, sem.name
ORDER BY l.room_number;


-- ── 5. Total sessions for active semester only ───────────────────────────────

SELECT
  sem.name AS semester_name,
  COUNT(*) AS total_sessions,
  COUNT(DISTINCT s.lab_id) AS labs_with_sessions
FROM lab_sessions s
JOIN semesters sem ON sem.id = s.semester_id
WHERE sem.is_active = true
GROUP BY sem.id, sem.name;


-- ── 6. year_group distribution (constraint check) ────────────────────────────
-- Valid values: I_YEAR, II_YEAR, III_YEAR, IV_YEAR, II_III_YEAR

SELECT
  year_group,
  COUNT(*) AS session_count
FROM lab_sessions
GROUP BY year_group
ORDER BY year_group;

-- Rows with INVALID year_group (should return 0 rows after migration)
SELECT
  id,
  lab_id,
  year_group,
  class_name,
  subject
FROM lab_sessions
WHERE year_group NOT IN ('I_YEAR', 'II_YEAR', 'III_YEAR', 'IV_YEAR', 'II_III_YEAR');


-- ── 7. Orphan sessions (lab_id not in labs) — should be empty ────────────────

SELECT
  s.id,
  s.lab_id,
  s.day_of_week,
  s.start_time,
  s.end_time
FROM lab_sessions s
LEFT JOIN labs l ON l.id = s.lab_id
WHERE l.id IS NULL;


-- ── 8. Labs marked has_data=false but have sessions — inconsistency check ───

SELECT
  l.room_number,
  l.has_data,
  COUNT(s.id) AS session_count
FROM labs l
JOIN lab_sessions s ON s.lab_id = l.id
WHERE l.has_data = false
GROUP BY l.room_number, l.has_data;


-- ── 9. Labs with NO sessions (for active semester) ─────────────────────────

SELECT
  l.room_number,
  l.has_data
FROM labs l
WHERE NOT EXISTS (
  SELECT 1
  FROM lab_sessions s
  JOIN semesters sem ON sem.id = s.semester_id AND sem.is_active = true
  WHERE s.lab_id = l.id
)
ORDER BY l.room_number;


-- ── 10. Full session detail (sample — first 50 rows) ─────────────────────────

SELECT
  l.room_number,
  sem.name AS semester_name,
  s.day_of_week,
  s.start_time,
  s.end_time,
  s.class_name,
  s.subject,
  s.session_type,
  s.year_group,
  s.source_file,
  s.created_at
FROM lab_sessions s
JOIN labs l ON l.id = s.lab_id
LEFT JOIN semesters sem ON sem.id = s.semester_id
ORDER BY l.room_number, s.day_of_week, s.start_time
LIMIT 50;


-- ── 11. Afternoon sessions (start_time >= 13:00) per room ────────────────────
-- Parser should produce ~40 afternoon slots for Lab_timetables.xlsx

SELECT
  l.room_number,
  COUNT(*) AS afternoon_session_count
FROM lab_sessions s
JOIN labs l ON l.id = s.lab_id
WHERE s.start_time >= '13:00:00'
GROUP BY l.room_number
ORDER BY l.room_number;


-- ── 12. Academic calendar entries per semester / year ────────────────────────

SELECT
  sem.name AS semester_name,
  ac.year_of_study,
  ac.event_name,
  ac.start_date,
  ac.end_date,
  ac.makes_labs_free,
  ac.created_at
FROM academic_calendars ac
JOIN semesters sem ON sem.id = ac.semester_id
ORDER BY sem.name, ac.year_of_study, ac.event_name;


-- ── 13. Expected Excel labs present? (14 labs) ─────────────────────────────

WITH expected AS (
  SELECT unnest(ARRAY[
    'E-317', 'E-330', 'E-331', 'E-401', 'E-402', 'E-403', 'E-417', 'E-430',
    'E-501', 'E-502', 'E-503', 'E-504', 'P-401', 'P-402'
  ]) AS room_number
),
actual AS (
  SELECT DISTINCT l.room_number
  FROM lab_sessions s
  JOIN labs l ON l.id = s.lab_id
  JOIN semesters sem ON sem.id = s.semester_id AND sem.is_active = true
)
SELECT
  e.room_number,
  CASE WHEN a.room_number IS NOT NULL THEN 'OK' ELSE 'MISSING' END AS status
FROM expected e
LEFT JOIN actual a ON a.room_number = e.room_number
ORDER BY e.room_number;
