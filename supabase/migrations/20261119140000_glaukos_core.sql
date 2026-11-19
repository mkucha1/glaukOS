-- GlaukOS core schema: crew & ranks, event register, shore link, audio storage.
-- Every report is a chain of events (see frontend/src/types.ts, ShipEvent).
-- Clients (anonymous Supabase users) may only insert the event types they own;
-- the speech/LLM backend writes the rest with the service role key (bypasses RLS).

-- ---------------------------------------------------------------- positions
create table public.positions (
  id          text primary key,
  label       text not null,
  department  text not null check (department in ('command', 'deck', 'engine', 'catering')),
  rank        int  not null,                       -- 1 = highest
  approves    text[] not null default '{}'         -- departments whose reports this position may approve
);

insert into public.positions (id, label, department, rank, approves) values
  ('captain',        'Captain',                   'command',  1, '{command,deck,engine,catering}'),
  ('chief_officer',  'Chief Officer',             'deck',     2, '{deck,catering}'),
  ('chief_engineer', 'Chief Engineer',            'engine',   2, '{engine}'),
  ('2nd_officer',    '2nd Officer',               'deck',     3, '{}'),
  ('2nd_engineer',   '2nd Engineer',              'engine',   3, '{}'),
  ('3rd_officer',    '3rd Officer',               'deck',     4, '{}'),
  ('3rd_engineer',   '3rd Engineer',              'engine',   4, '{}'),
  ('electrician',    'Electro-Technical Officer', 'engine',   4, '{}'),
  ('bosun',          'Bosun',                     'deck',     5, '{}'),
  ('chief_cook',     'Chief Cook',                'catering', 5, '{}'),
  ('ab',             'Able Seaman',               'deck',     6, '{}'),
  ('oiler',          'Oiler',                     'engine',   6, '{}'),
  ('motorman',       'Motorman',                  'engine',   6, '{}'),
  ('messman',        'Messman',                   'catering', 7, '{}');

-- ---------------------------------------------------------------- crew
-- One row per signed-in person (anonymous auth user). "Login" = name + position + station.
create table public.crew (
  id               uuid primary key references auth.users (id) on delete cascade,
  name             text not null check (char_length(name) between 1 and 40),
  position         text not null references public.positions (id),
  actor            text not null check (actor ~ '^[a-z0-9_]+:[a-z0-9_]+$'),  -- "2nd_engineer:mateusz"
  station          text not null check (station in
                     ('bridge','cabins','galley','purifier','ecr','engine','steering','deck','holds','bow','tanks')),
  on_duty          boolean not null default true,
  duty_changed_at  timestamptz not null default now(),
  created_at       timestamptz not null default now()
);
create index crew_actor_idx on public.crew (actor);

-- ---------------------------------------------------------------- ship status (shore link demo switch)
create table public.ship_status (
  id          int primary key default 1 check (id = 1),
  ship_name   text not null default 'Demo Ship',
  link_up     boolean not null default true,
  autopilot   boolean not null default true,   -- scripted pipeline until the speech/LLM backend is live
  updated_at  timestamptz not null default now()
);
insert into public.ship_status default values;

-- ---------------------------------------------------------------- events (the register)
create table public.events (
  event_id    uuid primary key,
  ts          timestamptz not null default now(),
  report_id   uuid,
  type        text not null check (type in (
                'report.recorded', 'report.transcribed', 'report.structured',
                'report.clarification_requested', 'report.clarification_answered', 'report.clarified',
                'report.sensor_checked', 'report.approved', 'report.rejected',
                'task.assigned', 'task.acknowledged', 'task.closed',
                'watch.handover_generated', 'sync.sent')),
  actor       text not null,
  device      text,
  payload     jsonb not null default '{}'::jsonb,
  synced_at   timestamptz,
  department  text not null default 'command' check (department in ('command', 'deck', 'engine', 'catering')),
  actor_id    uuid references auth.users (id) on delete set null
);
create index events_report_idx   on public.events (report_id, ts);
create index events_dept_ts_idx  on public.events (department, ts desc);
create index events_type_idx     on public.events (type);
create index events_unsynced_idx on public.events (ts) where synced_at is null;
create index events_actor_id_idx on public.events (actor_id);

-- ---------------------------------------------------------------- helpers (security definer: read crew/events past RLS)
create function public.my_actor() returns text
language sql stable security definer set search_path = '' as $$
  select c.actor from public.crew c where c.id = (select auth.uid())
$$;

create function public.my_department() returns text
language sql stable security definer set search_path = '' as $$
  select p.department from public.crew c join public.positions p on p.id = c.position where c.id = (select auth.uid())
$$;

create function public.my_approves() returns text[]
language sql stable security definer set search_path = '' as $$
  select coalesce((select p.approves from public.crew c join public.positions p on p.id = c.position
                   where c.id = (select auth.uid())), '{}'::text[])
$$;

create function public.can_approve(dept text) returns boolean
language sql stable security definer set search_path = '' as $$
  select dept = any (public.my_approves())
$$;

create function public.is_reporter(rid uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.events e
                 where e.report_id = rid and e.type = 'report.recorded' and e.actor_id = (select auth.uid()))
$$;

create function public.is_assignee(rid uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.events e
                 where e.report_id = rid and e.type = 'task.assigned' and e.payload ->> 'assignee' = public.my_actor())
$$;

-- Your department, departments you approve, and any report assigned to you.
create function public.can_read(dept text, rid uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select dept = public.my_department()
      or dept = any (public.my_approves())
      or (rid is not null and public.is_assignee(rid))
$$;

-- ---------------------------------------------------------------- triggers
create function public.events_before_insert() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_dept text;
  v_link boolean;
  v_actor text;
begin
  -- A report belongs to the department of whoever recorded it; later events inherit it.
  if new.report_id is not null and new.type <> 'report.recorded' then
    select e.department into v_dept from public.events e
    where e.report_id = new.report_id and e.type = 'report.recorded' limit 1;
  end if;
  if v_dept is null and auth.uid() is not null then
    v_dept := public.my_department();
  end if;
  new.department := coalesce(v_dept, new.department, 'command');

  -- Client-originated events are signed with the caller's identity; it cannot be spoofed.
  if auth.uid() is not null then
    new.actor_id := auth.uid();
    if new.type in ('report.recorded', 'report.clarification_answered', 'report.approved', 'report.rejected',
                    'task.assigned', 'task.acknowledged', 'task.closed') then
      v_actor := public.my_actor();
      if v_actor is not null then new.actor := v_actor; end if;
    end if;
  end if;

  -- Shore link: events reach shore immediately when the link is up, otherwise they wait.
  select s.link_up into v_link from public.ship_status s where s.id = 1;
  new.synced_at := case when coalesce(v_link, true) then now() else null end;
  new.ts := coalesce(new.ts, now());
  return new;
end;
$$;

create trigger events_before_insert before insert on public.events
for each row execute function public.events_before_insert();

create function public.crew_touch_duty() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.on_duty is distinct from old.on_duty then new.duty_changed_at := now(); end if;
  new.id := old.id;
  return new;
end;
$$;

create trigger crew_touch_duty before update on public.crew
for each row execute function public.crew_touch_duty();

-- ---------------------------------------------------------------- RLS
alter table public.positions   enable row level security;
alter table public.crew        enable row level security;
alter table public.ship_status enable row level security;
alter table public.events      enable row level security;

create policy positions_read on public.positions for select to anon, authenticated using (true);

create policy crew_read   on public.crew for select to authenticated using (true);
create policy crew_insert on public.crew for insert to authenticated with check (id = (select auth.uid()));
create policy crew_update on public.crew for update to authenticated
  using (id = (select auth.uid())) with check (id = (select auth.uid()));

create policy ship_status_read on public.ship_status for select to authenticated using (true);

create policy events_read on public.events for select to authenticated
  using (public.can_read(department, report_id));

-- Anyone signed in may file a report (event_id = report_id keeps re-sends idempotent).
create policy events_insert_report on public.events for insert to authenticated
  with check (type = 'report.recorded' and event_id = report_id and actor_id = (select auth.uid()));

-- Only the reporter answers the follow-up question on their report.
create policy events_insert_answer on public.events for insert to authenticated
  with check (type = 'report.clarification_answered' and public.is_reporter(report_id));

-- Approve / reject / assign: captain everywhere, department heads in their departments.
create policy events_insert_decision on public.events for insert to authenticated
  with check (type in ('report.approved', 'report.rejected', 'task.assigned', 'task.closed')
              and public.can_approve(department));

-- The assignee accepts and closes their own task.
create policy events_insert_task on public.events for insert to authenticated
  with check (type in ('task.acknowledged', 'task.closed') and public.is_assignee(report_id));

-- ---------------------------------------------------------------- RPCs
create function public.sync_status() returns jsonb
language sql stable security definer set search_path = '' as $$
  select jsonb_build_object(
    'link_up', s.link_up,
    'queued', (select count(*) from public.events e where e.synced_at is null),
    'last_sent_at', (select max(e.synced_at) from public.events e))
  from public.ship_status s where s.id = 1
$$;

create function public.set_link(p_up boolean) returns void
language plpgsql security definer set search_path = '' as $$
begin
  if cardinality(public.my_approves()) = 0 then
    raise exception 'Only the captain or a head of department can switch the shore link' using errcode = '42501';
  end if;
  update public.ship_status set link_up = p_up, updated_at = now() where id = 1;
  if p_up then
    update public.events set synced_at = now() where synced_at is null;
  end if;
end;
$$;

-- Scripted stand-in for the speech + LLM backend, used only while ship_status.autopilot = true.
-- The real backend turns it off: update public.ship_status set autopilot = false;
create function public.demo_autopilot(p_report_id uuid, p_answer text default null) returns void
language plpgsql security definer set search_path = '' as $$
declare
  v_on boolean;
  v_n int;
  v_no int;
  v_form jsonb;
begin
  select autopilot into v_on from public.ship_status where id = 1;
  if not coalesce(v_on, false) then return; end if;
  if not public.is_reporter(p_report_id) then
    raise exception 'Not your report' using errcode = '42501';
  end if;

  if p_answer is null then
    select count(*) into v_n from public.events where type = 'report.recorded' and actor_id = (select auth.uid());
    if v_n % 2 = 1 then
      insert into public.events (event_id, ts, report_id, type, actor, payload) values
        (gen_random_uuid(), now() + interval '1 second', p_report_id, 'report.transcribed', 'system:autopilot',
         jsonb_build_object('text', 'Pompa chłodzenia, ciśnienie spada do 1,8 bara, przeciek na uszczelnieniu.', 'lang', 'pl')),
        (gen_random_uuid(), now() + interval '2 seconds', p_report_id, 'report.structured', 'system:autopilot',
         jsonb_build_object('equipment', 'Cooling water pump', 'sfi_code', '721', 'parameter', 'discharge pressure',
           'value', 1.8, 'unit', 'bar', 'defect', 'leak at mechanical seal', 'priority', 2,
           'location', 'Engine room, lower platform',
           'text_en', 'Cooling water pump: discharge pressure dropping to 1.8 bar, leak at mechanical seal.',
           'lang_original', 'pl', 'missing_fields', jsonb_build_array('equipment number'), 'confidence', 0.71)),
        (gen_random_uuid(), now() + interval '3 seconds', p_report_id, 'report.clarification_requested', 'system:autopilot',
         jsonb_build_object('question', 'Pompa numer jeden czy numer dwa?', 'options', jsonb_build_array('No. 1', 'No. 2')));
    else
      insert into public.events (event_id, ts, report_id, type, actor, payload) values
        (gen_random_uuid(), now() + interval '1 second', p_report_id, 'report.transcribed', 'system:autopilot',
         jsonb_build_object('text', 'Wirówka paliwa numer jeden, duże wibracje i hałas na bębnie. Przełączyłem na wirówkę numer dwa.', 'lang', 'pl')),
        (gen_random_uuid(), now() + interval '2 seconds', p_report_id, 'report.structured', 'system:autopilot',
         jsonb_build_object('equipment', 'HFO purifier No. 1', 'sfi_code', '734', 'parameter', 'vibration',
           'defect', 'abnormal vibration and noise at bowl', 'priority', 3, 'location', 'Purifier room',
           'action_taken', 'Switched to purifier No. 2',
           'text_en', 'HFO purifier No. 1: abnormal vibration and noise at bowl. Switched over to purifier No. 2.',
           'lang_original', 'pl', 'missing_fields', '[]'::jsonb, 'confidence', 0.88)),
        (gen_random_uuid(), now() + interval '3 seconds', p_report_id, 'report.sensor_checked', 'system:autopilot',
         jsonb_build_object('tag', 'PUR1_VIB', 'sensor_value', 11.4, 'unit', 'mm/s', 'matches', true));
    end if;
  else
    v_no := case when p_answer ~* '(1|one|jed)' and p_answer !~* '(2|two|dwa)' then 1 else 2 end;
    v_form := jsonb_build_object('equipment', 'Cooling water pump No. ' || v_no, 'sfi_code', '721',
      'parameter', 'discharge pressure', 'value', 1.8, 'unit', 'bar', 'defect', 'leak at mechanical seal',
      'priority', 2, 'location', 'Engine room, lower platform',
      'text_en', 'Cooling water pump No. ' || v_no || ': discharge pressure dropping to 1.8 bar, leak at mechanical seal.',
      'lang_original', 'pl', 'missing_fields', '[]'::jsonb, 'confidence', 0.92);
    insert into public.events (event_id, ts, report_id, type, actor, payload) values
      (gen_random_uuid(), now() + interval '1 second', p_report_id, 'report.clarified', 'system:autopilot',
       jsonb_build_object('answer', p_answer)),
      (gen_random_uuid(), now() + interval '2 seconds', p_report_id, 'report.structured', 'system:autopilot', v_form),
      (gen_random_uuid(), now() + interval '3 seconds', p_report_id, 'report.sensor_checked', 'system:autopilot',
       jsonb_build_object('tag', 'CWP' || v_no || '_PT', 'sensor_value', 1.9, 'unit', 'bar', 'matches', true));
  end if;
end;
$$;

revoke all on function public.sync_status()                 from public, anon;
revoke all on function public.set_link(boolean)             from public, anon;
revoke all on function public.demo_autopilot(uuid, text)    from public, anon;
revoke all on function public.my_actor()                    from public, anon;
revoke all on function public.my_department()               from public, anon;
revoke all on function public.my_approves()                 from public, anon;
revoke all on function public.can_approve(text)             from public, anon;
revoke all on function public.is_reporter(uuid)             from public, anon;
revoke all on function public.is_assignee(uuid)             from public, anon;
revoke all on function public.can_read(text, uuid)          from public, anon;
grant execute on function public.sync_status()              to authenticated;
grant execute on function public.set_link(boolean)          to authenticated;
grant execute on function public.demo_autopilot(uuid, text) to authenticated;
grant execute on function public.my_actor()                 to authenticated;
grant execute on function public.my_department()            to authenticated;
grant execute on function public.my_approves()              to authenticated;
grant execute on function public.can_approve(text)          to authenticated;
grant execute on function public.is_reporter(uuid)          to authenticated;
grant execute on function public.is_assignee(uuid)          to authenticated;
grant execute on function public.can_read(text, uuid)       to authenticated;

-- ---------------------------------------------------------------- realtime
alter publication supabase_realtime add table public.events, public.crew, public.ship_status;

-- ---------------------------------------------------------------- audio storage
-- Path: recordings/{auth uid}/{report_id}.webm  (answers: {report_id}-answer-{uuid}.webm)
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('recordings', 'recordings', false, 26214400, array['audio/*'])
on conflict (id) do nothing;

create policy recordings_upload on storage.objects for insert to authenticated
  with check (bucket_id = 'recordings' and (storage.foldername(name))[1] = (select auth.uid()::text));

create policy recordings_read on storage.objects for select to authenticated
  using (bucket_id = 'recordings'
         and ((storage.foldername(name))[1] = (select auth.uid()::text) or cardinality(public.my_approves()) > 0));
