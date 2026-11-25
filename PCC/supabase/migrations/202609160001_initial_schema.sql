-- Production Control Center · initial Supabase/PostgreSQL schema
-- Server routes are the only database clients. Browser roles receive no access.

create extension if not exists pgcrypto;

create table if not exists public.production_lines (
  id text primary key,
  name text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.furnaces (
  id text primary key,
  production_line_id text not null references public.production_lines(id),
  name text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.work_orders (
  id text primary key,
  furnace_id text not null references public.furnaces(id),
  grade text not null,
  status text not null default 'ACTIVE'
    check (status in ('PLANNED', 'ACTIVE', 'COMPLETED', 'CANCELLED')),
  started_at timestamptz not null,
  ended_at timestamptz,
  created_at timestamptz not null default now(),
  check (ended_at is null or ended_at >= started_at)
);

create table if not exists public.measurements (
  id uuid primary key default gen_random_uuid(),
  work_order_id text references public.work_orders(id),
  furnace_id text not null references public.furnaces(id),
  measurement_type text not null
    check (measurement_type in ('WEIGHT', 'TEMPERATURE', 'POND_TEMPERATURE')),
  source text not null,
  value numeric not null,
  unit text not null,
  measured_at timestamptz not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists measurements_furnace_time_idx
  on public.measurements (furnace_id, measured_at desc);
create index if not exists measurements_work_order_time_idx
  on public.measurements (work_order_id, measured_at desc);

create table if not exists public.comparisons (
  id uuid primary key default gen_random_uuid(),
  measurement_id uuid not null unique references public.measurements(id) on delete cascade,
  reference_value numeric,
  lower_limit numeric,
  upper_limit numeric,
  delta numeric,
  status text not null
    check (status in ('GREEN', 'YELLOW', 'RED', 'SENSOR_ERROR')),
  rule_code text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.incidents (
  id uuid primary key default gen_random_uuid(),
  work_order_id text references public.work_orders(id),
  furnace_id text not null references public.furnaces(id),
  incident_type text not null,
  severity text not null check (severity in ('WARNING', 'CRITICAL')),
  status text not null default 'OPEN'
    check (status in ('OPEN', 'ACKNOWLEDGED', 'IN_PROGRESS', 'RESOLVED', 'CLOSED')),
  title text not null,
  assignee text,
  details jsonb not null default '{}'::jsonb,
  opened_at timestamptz not null default now(),
  acknowledged_at timestamptz,
  closed_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists incidents_status_time_idx
  on public.incidents (status, opened_at desc);

create table if not exists public.incident_events (
  id uuid primary key default gen_random_uuid(),
  incident_id uuid not null references public.incidents(id) on delete cascade,
  actor text not null,
  action text not null,
  note text,
  created_at timestamptz not null default now()
);

create index if not exists incident_events_incident_time_idx
  on public.incident_events (incident_id, created_at);

create table if not exists public.rack_count_events (
  id uuid primary key default gen_random_uuid(),
  camera_id text not null,
  rack_number bigint not null check (rack_number >= 0),
  track_id bigint not null,
  quantity integer not null default 1 check (quantity > 0),
  confidence numeric(5, 4) check (confidence between 0 and 1),
  occurred_at timestamptz not null,
  created_at timestamptz not null default now(),
  unique (camera_id, occurred_at, track_id)
);

create index if not exists rack_count_events_camera_time_idx
  on public.rack_count_events (camera_id, occurred_at desc);

-- The public schema is exposed by Supabase's Data API. Keep all operational
-- data private and access it only from trusted Next.js server routes.
alter table public.production_lines enable row level security;
alter table public.furnaces enable row level security;
alter table public.work_orders enable row level security;
alter table public.measurements enable row level security;
alter table public.comparisons enable row level security;
alter table public.incidents enable row level security;
alter table public.incident_events enable row level security;
alter table public.rack_count_events enable row level security;

revoke all on table
  public.production_lines,
  public.furnaces,
  public.work_orders,
  public.measurements,
  public.comparisons,
  public.incidents,
  public.incident_events,
  public.rack_count_events
from anon, authenticated;

grant select, insert, update, delete on table
  public.production_lines,
  public.furnaces,
  public.work_orders,
  public.measurements,
  public.comparisons,
  public.incidents,
  public.incident_events,
  public.rack_count_events
to service_role;

