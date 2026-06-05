-- Upload history schema to match `parser/db.py:log_upload()`.
-- Run this in Supabase SQL editor.
--
-- NOTE:
-- - `labs_updated` stores room numbers affected by an upload.
-- - Keep this table writeable by `service_role` only (Flask backend).

CREATE TABLE IF NOT EXISTS upload_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  semester_id UUID REFERENCES semesters(id),
  filename TEXT,
  file_type TEXT,
  content_type TEXT,
  parse_status TEXT,
  labs_updated TEXT[],
  sessions_added INTEGER,
  sessions_deleted INTEGER DEFAULT 0,
  warnings TEXT[],
  error_message TEXT,
  uploaded_at TIMESTAMPTZ DEFAULT now()
);

GRANT ALL ON upload_history TO service_role;

