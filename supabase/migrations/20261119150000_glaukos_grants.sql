-- Newer Supabase projects do not grant the API roles access to public tables by default.
-- These grants open the tables to the Data API; row-level security still decides which rows.
grant usage on schema public to anon, authenticated;

grant select on public.positions to anon, authenticated;
grant select, insert, update on public.crew to authenticated;
grant select on public.ship_status to authenticated;
grant select, insert on public.events to authenticated;

-- The speech/LLM backend uses the service role key.
grant all on public.positions, public.crew, public.ship_status, public.events to service_role;
