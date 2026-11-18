-- Tidings: privileges for the 17 `tidings_*` tables ONLY. Safe to re-run.
-- Grants are listed table-by-table on purpose: nothing applies to "all tables" and no default
-- privileges change, so any other app's tables in this project are never touched.
-- Only the backend (service_role key) may read or write; anon/authenticated get nothing
-- (and RLS is on with no policies as a second lock).

revoke all on table
  tidings_users,
  tidings_occasion_years,
  tidings_year_members,
  tidings_groups,
  tidings_recipients,
  tidings_gifts,
  tidings_price_history,
  tidings_wishlists,
  tidings_wishlist_items,
  tidings_claims,
  tidings_secret_santa_exchanges,
  tidings_activity_log,
  tidings_invites,
  tidings_push_tokens,
  tidings_subscriptions,
  tidings_analytics_events,
  tidings_error_logs
from anon, authenticated;

grant select, insert, update, delete on table
  tidings_users,
  tidings_occasion_years,
  tidings_year_members,
  tidings_groups,
  tidings_recipients,
  tidings_gifts,
  tidings_price_history,
  tidings_wishlists,
  tidings_wishlist_items,
  tidings_claims,
  tidings_secret_santa_exchanges,
  tidings_activity_log,
  tidings_invites,
  tidings_push_tokens,
  tidings_subscriptions,
  tidings_analytics_events,
  tidings_error_logs
to service_role;
