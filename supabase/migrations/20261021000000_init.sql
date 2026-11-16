-- Permit Memo schema. Apply with `supabase db push` (linked project) or `supabase db reset` locally.
create extension if not exists pgcrypto;

-- ---------- helpers --------------------------------------------------------------------
create or replace function public.set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

-- ---------- profiles -------------------------------------------------------------------
create table public.profiles (
  id                     uuid primary key references auth.users (id) on delete cascade,
  email                  text,
  plans_created          integer not null default 0,
  plan_credits           integer not null default 0,
  subscription_status    text,            -- active | trialing | past_due | canceled | null
  stripe_customer_id     text unique,
  stripe_subscription_id text,
  current_period_end     timestamptz,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);
create trigger profiles_updated_at before update on public.profiles
  for each row execute function public.set_updated_at();

-- auto-create a profile row on signup (the API also upserts defensively)
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, email) values (new.id, new.email)
  on conflict (id) do update set email = excluded.email;
  return new;
end $$;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------- plans ----------------------------------------------------------------------
create table public.plans (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references auth.users (id) on delete cascade,
  title            text not null,
  description      text not null,
  target_open_date date,
  status           text not null check (status in ('pending_clarification', 'generating', 'ready', 'failed')),
  version          integer not null default 1,
  profile          jsonb,
  clarification    jsonb,
  plan             jsonb,
  error            text,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);
create index plans_user_created_idx on public.plans (user_id, created_at desc);
create trigger plans_updated_at before update on public.plans
  for each row execute function public.set_updated_at();

-- ---------- plan_steps (done / notes live here so reruns can preserve them) -------------
create table public.plan_steps (
  id         uuid primary key default gen_random_uuid(),
  plan_id    uuid not null references public.plans (id) on delete cascade,
  step_key   text not null,               -- catalog permit id, e.g. sf.health_permit
  position   integer not null,
  name       text not null,
  done       boolean not null default false,
  done_at    timestamptz,
  notes      text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (plan_id, step_key)
);
create index plan_steps_plan_idx on public.plan_steps (plan_id, position);
create trigger plan_steps_updated_at before update on public.plan_steps
  for each row execute function public.set_updated_at();

-- ---------- usage_events (server-side analytics / audit) --------------------------------
create table public.usage_events (
  id         bigserial primary key,
  user_id    uuid references auth.users (id) on delete set null,
  event      text not null,
  properties jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index usage_events_user_idx on public.usage_events (user_id, created_at desc);
create index usage_events_event_idx on public.usage_events (event, created_at desc);

-- ---------- previews (anonymous, pre-signup; purged after 7 days) ----------------------
create table public.previews (
  id               uuid primary key default gen_random_uuid(),
  description      text not null,
  target_open_date date,
  status           text not null default 'generating',
  profile          jsonb,
  result           jsonb,
  clarification    jsonb,
  ip_hash          text,
  created_at       timestamptz not null default now(),
  expires_at       timestamptz not null default now() + interval '7 days'
);
create index previews_expires_idx on public.previews (expires_at);

-- ---------- leads (email capture for unsupported cities) --------------------------------
create table public.leads (
  id          uuid primary key default gen_random_uuid(),
  email       text not null,
  city        text,
  state       text,
  description text,
  created_at  timestamptz not null default now()
);
create index leads_email_idx on public.leads (email);

-- ---------- row level security -----------------------------------------------------------
-- The API uses the service role (bypasses RLS) and always filters by user_id.
-- These policies protect direct access with the anon/authenticated keys from the browser.
alter table public.profiles     enable row level security;
alter table public.plans        enable row level security;
alter table public.plan_steps   enable row level security;
alter table public.usage_events enable row level security;
alter table public.previews     enable row level security;
alter table public.leads        enable row level security;

create policy "profiles: owner can read"   on public.profiles for select using (auth.uid() = id);
create policy "profiles: owner can update email only" on public.profiles for update
  using (auth.uid() = id) with check (auth.uid() = id and plans_created = (select p.plans_created from public.profiles p where p.id = auth.uid())
                                      and plan_credits = (select p.plan_credits from public.profiles p where p.id = auth.uid())
                                      and subscription_status is not distinct from (select p.subscription_status from public.profiles p where p.id = auth.uid()));

create policy "plans: owner can read"      on public.plans for select using (auth.uid() = user_id);
create policy "plans: owner can delete"    on public.plans for delete using (auth.uid() = user_id);

create policy "plan_steps: owner can read" on public.plan_steps for select
  using (exists (select 1 from public.plans p where p.id = plan_id and p.user_id = auth.uid()));
create policy "plan_steps: owner can update progress" on public.plan_steps for update
  using (exists (select 1 from public.plans p where p.id = plan_id and p.user_id = auth.uid()))
  with check (exists (select 1 from public.plans p where p.id = plan_id and p.user_id = auth.uid()));

create policy "usage_events: owner can read" on public.usage_events for select using (auth.uid() = user_id);
-- previews and leads: no policies → only the service role can touch them.

-- ---------- housekeeping -------------------------------------------------------------------
create or replace function public.purge_expired_previews() returns void
language sql security definer as $$
  delete from public.previews where expires_at < now();
$$;
-- Schedule with pg_cron if enabled on your project:
--   select cron.schedule('purge-previews', '0 4 * * *', $$select public.purge_expired_previews()$$);
