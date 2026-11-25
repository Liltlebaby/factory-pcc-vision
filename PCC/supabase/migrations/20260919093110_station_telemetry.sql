-- Time-series measurements sent by PCC sensor gateways.
-- measurement_id is supplied by the gateway so retries remain idempotent.

create table if not exists public.sensor_telemetry (
  measurement_id text primary key,
  site_id text not null,
  line_id text not null,
  station_id text not null,
  device_id text not null,
  metric text not null,
  value double precision not null,
  unit text not null,
  measured_at timestamptz not null,
  received_at timestamptz not null,
  quality text not null check (quality in ('good', 'uncertain', 'bad', 'stale')),
  source_mode text not null check (source_mode in ('live', 'demo')),
  source_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists sensor_telemetry_station_metric_time_idx
  on public.sensor_telemetry (station_id, metric, measured_at desc);

create index if not exists sensor_telemetry_device_time_idx
  on public.sensor_telemetry (device_id, measured_at desc);

alter table public.sensor_telemetry enable row level security;

revoke all on table public.sensor_telemetry from anon, authenticated;
grant select, insert, update, delete on table public.sensor_telemetry to service_role;
