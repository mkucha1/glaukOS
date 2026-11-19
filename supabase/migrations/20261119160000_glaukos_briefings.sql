-- Watch handover briefings written by the ship worker's LLM (qwen, backend/decision: shipdec worker).
-- Additive only: new tables, nothing in events / crew / positions changes.
--
-- Flow: the app inserts a request row (status 'requested', its watch window) -> the worker, seeing it,
-- writes the briefing with qwen from the reports the requester may read (same rule as can_read)
-- and sets status 'done' + text (or 'failed' + error). The app polls its own row.
-- worker_status.last_seen is the worker's heartbeat: if it is stale, the app builds the briefing
-- locally from the register (src/lib/handover.ts), exactly as before.

create table public.briefings (
  id            uuid primary key,
  requested_by  uuid not null default auth.uid() references auth.users (id) on delete cascade,
  watch         text not null check (watch ~ '^[0-9]{2}-[0-9]{2}$'),
  window_from   timestamptz not null,
  window_to     timestamptz not null,
  lang          text not null default 'en',
  status        text not null default 'requested' check (status in ('requested', 'working', 'done', 'failed')),
  text          text,
  model         text,
  error         text,
  requested_at  timestamptz not null default now(),
  generated_at  timestamptz
);
create index briefings_pending_idx on public.briefings (requested_at) where status = 'requested';

create table public.worker_status (
  id         int primary key default 1 check (id = 1),
  last_seen  timestamptz,
  info       jsonb not null default '{}'::jsonb
);
insert into public.worker_status default values;

alter table public.briefings     enable row level security;
alter table public.worker_status enable row level security;

-- Anyone signed in may ask for a briefing for themselves and read their own briefings.
create policy briefings_insert on public.briefings for insert to authenticated
  with check (requested_by = (select auth.uid()) and status = 'requested' and text is null);
create policy briefings_read on public.briefings for select to authenticated
  using (requested_by = (select auth.uid()));

create policy worker_status_read on public.worker_status for select to authenticated using (true);

grant select, insert on public.briefings to authenticated;
grant select on public.worker_status to authenticated;
-- The worker uses the secret / service role key.
grant all on public.briefings, public.worker_status to service_role;
