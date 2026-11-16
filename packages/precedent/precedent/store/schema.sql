-- Precedent data layer (PostGIS). Applied by supabase/migrations/20261022000000_precedent.sql
-- and by tests against a scratch database. Idempotent.
create extension if not exists postgis;

create table if not exists public.applications (
  id                     text primary key,
  source                 text not null,
  source_id              text not null,
  source_url             text not null,
  fetched_at             timestamptz not null,
  raw_ref                text,
  kind                   text not null,
  permit_type            text not null,
  use_types              text[] not null default '{}',
  description            text not null default '',
  address                text,
  geom                   geography(point, 4326),
  parcel                 text,
  zoning_district        text,
  status                 text not null default '',
  outcome                text not null default 'unknown',
  filed_at               date,
  decided_at             date,
  hours_close            text,
  late_night             boolean,
  conditions             text[] not null default '{}',
  opposition_noted       boolean,
  decision_summary       text,
  extraction_confidence  text,
  license_type           text,
  extra                  jsonb not null default '{}'::jsonb,
  updated_at             timestamptz not null default now()
);
create index if not exists applications_geom_idx on public.applications using gist (geom);
create index if not exists applications_kind_idx on public.applications (kind, outcome);
create index if not exists applications_source_idx on public.applications (source);
create index if not exists applications_filed_idx on public.applications (filed_at desc);

create table if not exists public.locations (
  normalized_address text primary key,
  address            text not null,
  parcel             text,
  geom               geography(point, 4326) not null,
  zoning_district    text,
  zoning_name        text,
  overlays           text[] not null default '{}',
  neighborhood       text,
  source             text not null,
  source_url         text not null default '',
  fetched_at         timestamptz not null
);
create index if not exists locations_geom_idx on public.locations using gist (geom);

create table if not exists public.overlays (
  id                     text primary key,
  kind                   text not null,
  name                   text not null,
  rules                  text not null,
  code_section           text not null,
  geom                   geometry(multipolygon, 4326),
  district_codes         text[] not null default '{}',
  bar_permission         text not null default 'unknown',
  restaurant_permission  text not null default 'unknown',
  late_night_rule        text,
  source                 text not null,
  source_url             text not null,
  fetched_at             timestamptz not null
);
create index if not exists overlays_geom_idx on public.overlays using gist (geom);
create index if not exists overlays_kind_idx on public.overlays (kind);

create table if not exists public.businesses (
  id                 text primary key,
  dba_name           text not null,
  naics_code         text,
  naics_description  text,
  address            text,
  geom               geography(point, 4326),
  start_date         date,
  end_date           date,
  is_food_or_drink   boolean not null default false,
  is_bar             boolean not null default false,
  source             text not null,
  source_url         text not null,
  fetched_at         timestamptz not null
);
create index if not exists businesses_geom_idx on public.businesses using gist (geom);
create index if not exists businesses_food_idx on public.businesses (is_food_or_drink, end_date);

create table if not exists public.outcomes_feedback (
  id            uuid primary key default gen_random_uuid(),
  memo_id       uuid not null,
  user_id       uuid,
  address       text not null,
  geom          geography(point, 4326),
  concept_type  text not null,
  outcome       text not null check (outcome in ('approved','approved_with_conditions','denied','withdrew','still_pending')),
  notes         text,
  reported_at   timestamptz not null default now()
);
create index if not exists outcomes_feedback_geom_idx on public.outcomes_feedback using gist (geom);
create index if not exists outcomes_feedback_memo_idx on public.outcomes_feedback (memo_id);

create table if not exists public.ingestion_runs (
  id            bigserial primary key,
  source        text not null,
  started_at    timestamptz not null,
  finished_at   timestamptz,
  status        text not null,
  rows_fetched  integer not null default 0,
  rows_upserted integer not null default 0,
  error         text,
  notes         text
);
create index if not exists ingestion_runs_source_idx on public.ingestion_runs (source, started_at desc);

alter table public.applications      enable row level security;
alter table public.locations         enable row level security;
alter table public.overlays          enable row level security;
alter table public.businesses        enable row level security;
alter table public.outcomes_feedback enable row level security;
alter table public.ingestion_runs    enable row level security;
-- no policies: only the service role / direct connection used by the API and the ingestion job can read or write.
