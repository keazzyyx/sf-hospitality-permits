-- Answer rounds (owner decision of 2026-11-16; apps/api/app/memo/answers.py, apps/api/app/services/memos.py):
-- a memo is run again with more intake answers, free, on the same memo, up to five times. No model call: the
-- answers go on what the intake of the memo's first run left, which is kept with the memo.
--
-- Apply before deploying the API that writes these columns. An API without this migration still makes and serves
-- memos: it writes intake_basis in a write of its own after the memo is saved and only logs when that fails (the
-- memo then cannot be answered with a round), and it reads the other columns only on the answer routes.

-- What the intake of the memo's first run left, before the intake answers (`IntakeBasis`): the checked profile with
-- the clarification answers and overrides applied, what the stated-facts check cleared, and where each fact came
-- from. Null for a memo made before this migration: such a memo is not answered with a round.
alter table public.memos add column if not exists intake_basis jsonb;
-- The rounds that finished and were saved (0: the report the memo was made with).
alter table public.memos add column if not exists answers_round integer not null default 0
  check (answers_round >= 0 and answers_round <= 5);
-- The claim of the round running now (a fresh uuid each round); null when none is running. A round starts only by
-- changing the claim the row had, and saves only while its claim is still the row's.
alter table public.memos add column if not exists answers_run uuid;
-- When the last round was saved.
alter table public.memos add column if not exists answered_at timestamptz;

-- One row per finished round, holding the version of the memo it replaced. `round` is the round that replaced it:
-- the version replaced by round 1 is the report the memo was made with. The id is
-- uuid5(REVISION_NAMESPACE, "<memo_id>:<round>") (apps/api/app/services/memos.py); (memo_id, round) is unique too.
create table if not exists public.memo_revisions (
  id          uuid primary key,
  memo_id     uuid not null references public.memos (id) on delete cascade,
  user_id     uuid not null references auth.users (id) on delete cascade,
  round       integer not null check (round >= 1 and round <= 5),
  intake      jsonb,
  profile     jsonb,
  memo        jsonb,
  teaser      jsonb,
  created_at  timestamptz not null default now(),
  unique (memo_id, round)
);
create index if not exists memo_revisions_memo_idx on public.memo_revisions (memo_id, round);

-- As on memos: the API uses the service role (bypasses RLS), always filters by user_id, and is the only writer.
-- The owner can read their own rows with the browser keys; no one else can, and no browser key can write.
alter table public.memo_revisions enable row level security;
drop policy if exists "memo_revisions: owner can read" on public.memo_revisions;
create policy "memo_revisions: owner can read" on public.memo_revisions for select using (auth.uid() = user_id);
