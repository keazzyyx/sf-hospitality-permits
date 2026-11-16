-- The applicant's answers to the optional intake questions of a memo (apps/api/app/memo/intake.py):
-- {part_of_chain?, other_locations?, floor_area_sqft?, liquor_licence?}. Null when none was answered.
-- The API writes the column only for a memo with at least one answer, so memos without answers do not depend
-- on this migration; a memo with answers does. A clarification run reads them back and applies them again.
alter table public.memos add column if not exists intake jsonb;
