-- Tidings: explicit table privileges. Safe to re-run.
-- Only the backend (service_role key) may touch these tables. The public anon/authenticated
-- roles get nothing, so even if an anon key leaked, the Data API exposes no Tidings data.

grant usage on schema public to service_role;
grant select, insert, update, delete on all tables in schema public to service_role;
grant usage, select on all sequences in schema public to service_role;

revoke all on all tables in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;

-- Tables created by future migrations follow the same rule.
alter default privileges in schema public grant select, insert, update, delete on tables to service_role;
alter default privileges in schema public revoke all on tables from anon, authenticated;
