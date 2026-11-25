-- Server-side evaluation history and active alerts for sensor telemetry.
-- All writes come from trusted PCC server routes using the service role.

create table if not exists public.station_rule_observations (
  id uuid primary key default gen_random_uuid(),
  station_id text not null,
  rule_key text not null,
  rule_code text not null,
  source_measurement_id text not null
    references public.sensor_telemetry(measurement_id) on delete cascade,
  metric text not null,
  process_status text not null
    check (process_status in ('GREEN', 'YELLOW', 'RED', 'SENSOR_ERROR')),
  severity text check (severity in ('WARNING', 'CRITICAL')),
  is_violation boolean not null,
  title text not null,
  message text not null,
  owner text not null,
  recommended_action text not null,
  evaluated_at timestamptz not null,
  created_at timestamptz not null default now(),
  unique (source_measurement_id, rule_key)
);

create index if not exists station_rule_observations_station_time_idx
  on public.station_rule_observations (station_id, evaluated_at desc);

create table if not exists public.station_alerts (
  alert_key text primary key,
  site_id text not null,
  line_id text not null,
  station_id text not null,
  rule_key text not null,
  rule_code text not null,
  source_measurement_id text
    references public.sensor_telemetry(measurement_id) on delete set null,
  state text not null check (state in ('OPEN', 'CLOSED')),
  process_status text not null
    check (process_status in ('YELLOW', 'RED', 'SENSOR_ERROR')),
  severity text not null check (severity in ('WARNING', 'CRITICAL')),
  title text not null,
  message text not null,
  owner text not null,
  recommended_action text not null,
  opened_at timestamptz not null,
  last_observed_at timestamptz not null,
  closed_at timestamptz,
  occurrence_count integer not null default 1 check (occurrence_count > 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check ((state = 'OPEN' and closed_at is null) or state = 'CLOSED')
);

create index if not exists station_alerts_state_time_idx
  on public.station_alerts (state, last_observed_at desc);
create index if not exists station_alerts_station_state_idx
  on public.station_alerts (station_id, state, last_observed_at desc);

create table if not exists public.station_alert_events (
  event_key text primary key,
  alert_key text not null references public.station_alerts(alert_key) on delete cascade,
  source_measurement_id text
    references public.sensor_telemetry(measurement_id) on delete set null,
  transition text not null check (transition in ('OPEN', 'OBSERVED', 'CLOSED')),
  rule_code text not null,
  process_status text not null
    check (process_status in ('GREEN', 'YELLOW', 'RED', 'SENSOR_ERROR')),
  message text not null,
  occurred_at timestamptz not null,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists station_alert_events_alert_time_idx
  on public.station_alert_events (alert_key, occurred_at desc);

alter table public.station_rule_observations enable row level security;
alter table public.station_alerts enable row level security;
alter table public.station_alert_events enable row level security;

revoke all on table
  public.station_rule_observations,
  public.station_alerts,
  public.station_alert_events
from anon, authenticated;

grant select, insert, update, delete on table
  public.station_rule_observations,
  public.station_alerts,
  public.station_alert_events
to service_role;
