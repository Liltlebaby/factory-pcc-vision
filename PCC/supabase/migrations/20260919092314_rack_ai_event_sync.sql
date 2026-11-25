-- Durable, idempotent delivery of Vision Monitor events into PCC.

alter table public.rack_count_events
  add column if not exists source_event_id text,
  add column if not exists source_cursor bigint,
  add column if not exists task_id text,
  add column if not exists station_id text,
  add column if not exists model_version text,
  add column if not exists rule_version text,
  add column if not exists source_payload jsonb not null default '{}'::jsonb;

create unique index if not exists rack_count_events_source_event_id_idx
  on public.rack_count_events (source_event_id);

create unique index if not exists rack_count_events_source_cursor_idx
  on public.rack_count_events (camera_id, source_cursor);

create index if not exists rack_count_events_station_time_idx
  on public.rack_count_events (station_id, occurred_at desc);

create table if not exists public.integration_sync_state (
  integration_id text primary key,
  last_cursor bigint not null default 0 check (last_cursor >= 0),
  last_success_at timestamptz,
  last_error text,
  updated_at timestamptz not null default now()
);

alter table public.integration_sync_state enable row level security;

revoke all on table public.integration_sync_state from anon, authenticated;
grant select, insert, update, delete on table public.integration_sync_state to service_role;
