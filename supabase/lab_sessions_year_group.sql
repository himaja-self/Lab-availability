-- Run once in Supabase SQL Editor.
-- Expands lab_sessions.year_group to match excel_parser / word_parser output.
-- Old constraint typically only allowed: I_YEAR, II_III_YEAR

ALTER TABLE lab_sessions
  DROP CONSTRAINT IF EXISTS lab_sessions_year_group_check;

ALTER TABLE lab_sessions
  ADD CONSTRAINT lab_sessions_year_group_check
  CHECK (year_group IN (
    'I_YEAR',
    'II_YEAR',
    'III_YEAR',
    'IV_YEAR',
    'II_III_YEAR'   -- keep for any legacy rows
  ));
