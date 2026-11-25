-- PCC authentication, role catalogue, incident workflow and immutable audit trail.
-- Authorization decisions in the application use auth.jwt().app_metadata.pcc_role.
-- raw_user_meta_data is intentionally never used for authorization because users
-- can edit it themselves.

create table if not exists public.pcc_user_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null check (char_length(display_name) between 1 and 120),
  role text not null check (role in ('admin', 'operator', 'viewer')),
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on column public.pcc_user_profiles.role is
  'Administrative catalogue. The same role must be assigned by an administrator to auth.users.raw_app_meta_data.pcc_role before it is effective.';

alter table public.station_alerts
  add column if not exists workflow_state text not null default 'OPEN'
    check (workflow_state in ('OPEN', 'ACKNOWLEDGED', 'VERIFYING', 'CLOSED')),
  add column if not exists acknowledged_at timestamptz,
  add column if not exists acknowledged_by uuid references auth.users(id) on delete set null,
  add column if not exists resolved_at timestamptz,
  add column if not exists resolved_by uuid references auth.users(id) on delete set null,
  add column if not exists resolution_note text;

update public.station_alerts
set workflow_state = 'CLOSED'
where state = 'CLOSED' and workflow_state <> 'CLOSED';

create table if not exists public.station_incident_actions (
  id bigint generated always as identity primary key,
  action_key text not null unique,
  alert_key text not null references public.station_alerts(alert_key) on delete cascade,
  action text not null check (action in ('ACKNOWLEDGE', 'RESOLVE', 'REOPEN', 'NOTE')),
  actor_user_id uuid not null references auth.users(id) on delete restrict,
  actor_role text not null check (actor_role in ('admin', 'operator')),
  note text,
  occurred_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  check (action <> 'RESOLVE' or nullif(btrim(note), '') is not null)
);

create index if not exists station_incident_actions_alert_time_idx
  on public.station_incident_actions (alert_key, occurred_at desc);

create index if not exists station_incident_actions_actor_time_idx
  on public.station_incident_actions (actor_user_id, occurred_at desc);

create table if not exists public.pcc_audit_events (
  id bigint generated always as identity primary key,
  audit_key text not null unique,
  actor_user_id uuid references auth.users(id) on delete set null,
  actor_role text check (actor_role in ('admin', 'operator', 'viewer', 'system')),
  action text not null,
  entity_type text not null,
  entity_id text not null,
  before_state jsonb,
  after_state jsonb,
  request_id text,
  occurred_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create index if not exists pcc_audit_events_entity_time_idx
  on public.pcc_audit_events (entity_type, entity_id, occurred_at desc);

create index if not exists pcc_audit_events_actor_time_idx
  on public.pcc_audit_events (actor_user_id, occurred_at desc);

alter table public.pcc_user_profiles enable row level security;
alter table public.station_incident_actions enable row level security;
alter table public.pcc_audit_events enable row level security;

-- Browser clients do not access the authorization catalogue or audit tables
-- directly. Next.js validates the user, checks app_metadata.pcc_role and performs
-- writes with the server-only secret key. This keeps policy enforcement in one
-- auditable server boundary and prevents BOLA/IDOR via the Data API.
revoke all on table
  public.pcc_user_profiles,
  public.station_incident_actions,
  public.pcc_audit_events
from anon, authenticated;

grant select, insert, update, delete on table
  public.pcc_user_profiles,
  public.station_incident_actions,
  public.pcc_audit_events
to service_role;

grant usage, select on sequence
  public.station_incident_actions_id_seq,
  public.pcc_audit_events_id_seq
to service_role;

-- Keep the operator workflow aligned with the server-side rule lifecycle. A
-- rule closing an alert always closes its workflow. If the rule reopens later,
-- the acknowledgement and resolution must start again for the new occurrence.
create or replace function public.pcc_sync_station_alert_workflow()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if new.state = 'CLOSED' then
    new.workflow_state := 'CLOSED';
  elsif tg_op = 'UPDATE' and old.state = 'CLOSED' and new.state = 'OPEN' then
    new.workflow_state := 'OPEN';
    new.acknowledged_at := null;
    new.acknowledged_by := null;
    new.resolved_at := null;
    new.resolved_by := null;
    new.resolution_note := null;
  end if;
  return new;
end;
$$;

drop trigger if exists station_alert_workflow_lifecycle on public.station_alerts;
create trigger station_alert_workflow_lifecycle
before insert or update of state on public.station_alerts
for each row execute function public.pcc_sync_station_alert_workflow();

revoke execute on function public.pcc_sync_station_alert_workflow() from public, anon, authenticated;
grant execute on function public.pcc_sync_station_alert_workflow() to service_role;

-- Apply an operator action, append the action journal and append the immutable
-- audit record in one database transaction. The function is SECURITY INVOKER;
-- it does not bypass RLS and is executable only by the server-side service role.
create or replace function public.pcc_apply_incident_action(
  p_alert_key text,
  p_action text,
  p_note text,
  p_actor_user_id uuid,
  p_actor_role text,
  p_action_key text,
  p_audit_key text,
  p_request_id text
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_alert public.station_alerts%rowtype;
  v_before jsonb;
  v_existing boolean;
  v_now timestamptz := now();
begin
  if p_actor_role not in ('admin', 'operator') then
    raise exception using errcode = '42501', message = 'incident_action_forbidden';
  end if;
  if not exists (
    select 1
    from public.pcc_user_profiles profile
    where profile.user_id = p_actor_user_id
      and profile.active = true
      and profile.role = p_actor_role
  ) then
    raise exception using errcode = '42501', message = 'incident_actor_inactive_or_role_mismatch';
  end if;
  if p_action not in ('ACKNOWLEDGE', 'RESOLVE', 'NOTE') then
    raise exception using errcode = '22023', message = 'invalid_incident_action';
  end if;
  if p_action in ('RESOLVE', 'NOTE') and nullif(btrim(p_note), '') is null then
    raise exception using errcode = '22023', message = 'incident_note_required';
  end if;
  if p_action = 'RESOLVE' and char_length(btrim(p_note)) < 3 then
    raise exception using errcode = '22023', message = 'incident_note_too_short';
  end if;
  if p_note is not null and char_length(p_note) > 1000 then
    raise exception using errcode = '22023', message = 'incident_note_too_long';
  end if;

  select * into v_alert
  from public.station_alerts
  where alert_key = p_alert_key
  for update;

  if not found then
    raise exception using errcode = 'P0002', message = 'incident_not_found';
  end if;

  -- Serialize actions for the same alert before checking the idempotency key,
  -- so concurrent retries cannot both pass the existence check.
  select exists(
    select 1 from public.station_incident_actions where action_key = p_action_key
  ) into v_existing;
  if v_existing then
    return to_jsonb(v_alert);
  end if;
  if v_alert.state = 'CLOSED' or v_alert.workflow_state = 'CLOSED' then
    raise exception using errcode = 'P0001', message = 'incident_already_closed';
  end if;

  v_before := to_jsonb(v_alert);

  if p_action = 'ACKNOWLEDGE' then
    if v_alert.workflow_state <> 'OPEN' then
      raise exception using errcode = 'P0001', message = 'incident_not_open';
    end if;
    update public.station_alerts
    set workflow_state = 'ACKNOWLEDGED',
        acknowledged_at = v_now,
        acknowledged_by = p_actor_user_id,
        updated_at = v_now
    where alert_key = p_alert_key
    returning * into v_alert;
  elsif p_action = 'RESOLVE' then
    if v_alert.workflow_state <> 'ACKNOWLEDGED' then
      raise exception using errcode = 'P0001', message = 'incident_not_acknowledged';
    end if;
    update public.station_alerts
    set workflow_state = 'VERIFYING',
        resolved_at = v_now,
        resolved_by = p_actor_user_id,
        resolution_note = btrim(p_note),
        updated_at = v_now
    where alert_key = p_alert_key
    returning * into v_alert;
  else
    update public.station_alerts
    set updated_at = v_now
    where alert_key = p_alert_key
    returning * into v_alert;
  end if;

  insert into public.station_incident_actions (
    action_key, alert_key, action, actor_user_id, actor_role, note, occurred_at
  ) values (
    p_action_key, p_alert_key, p_action, p_actor_user_id, p_actor_role,
    nullif(btrim(p_note), ''), v_now
  );

  insert into public.pcc_audit_events (
    audit_key, actor_user_id, actor_role, action, entity_type, entity_id,
    before_state, after_state, request_id, occurred_at
  ) values (
    p_audit_key, p_actor_user_id, p_actor_role,
    'incident.' || lower(p_action), 'station_alert', p_alert_key,
    v_before, to_jsonb(v_alert), p_request_id, v_now
  );

  return to_jsonb(v_alert);
end;
$$;

revoke execute on function public.pcc_apply_incident_action(
  text, text, text, uuid, text, text, text, text
) from public, anon, authenticated;
grant execute on function public.pcc_apply_incident_action(
  text, text, text, uuid, text, text, text, text
) to service_role;
