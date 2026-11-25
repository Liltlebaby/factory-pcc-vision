insert into public.production_lines (id, name)
values ('LINE-1', 'Production Line 1')
on conflict (id) do update set name = excluded.name;

insert into public.furnaces (id, production_line_id, name)
values ('FUR-A', 'LINE-1', 'เตา A')
on conflict (id) do update set
  production_line_id = excluded.production_line_id,
  name = excluded.name;

insert into public.work_orders (id, furnace_id, grade, status, started_at)
values ('WO-2026-0904-01', 'FUR-A', 'AJ2', 'ACTIVE', '2026-09-04T01:00:00Z')
on conflict (id) do update set
  furnace_id = excluded.furnace_id,
  grade = excluded.grade,
  status = excluded.status;

