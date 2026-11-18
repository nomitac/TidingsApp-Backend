-- Indexes for sync pulls (server_updated_at > since) and ownership lookups.

create index if not exists occasion_years_owner_idx        on occasion_years (owner_id);
create index if not exists occasion_years_sua_idx          on occasion_years (server_updated_at);

create index if not exists year_members_user_idx           on year_members (user_id, status);
create index if not exists year_members_year_sua_idx       on year_members (occasion_year_id, server_updated_at);

create index if not exists groups_year_sua_idx             on groups (occasion_year_id, server_updated_at);
create index if not exists recipients_year_sua_idx         on recipients (occasion_year_id, server_updated_at);
create index if not exists recipients_person_idx           on recipients (person_id);
create index if not exists gifts_year_sua_idx              on gifts (occasion_year_id, server_updated_at);
create index if not exists gifts_recipient_idx             on gifts (recipient_id);
create index if not exists activity_log_year_sua_idx       on activity_log (occasion_year_id, server_updated_at);

create index if not exists wishlists_owner_idx             on wishlists (owner_user_id, server_updated_at);
create index if not exists wishlist_items_wishlist_sua_idx on wishlist_items (wishlist_id, server_updated_at);
create index if not exists claims_item_idx                 on claims (wishlist_item_id, status);

create index if not exists exchanges_organizer_sua_idx     on secret_santa_exchanges (organizer_id, server_updated_at);
create index if not exists push_tokens_user_idx            on push_tokens (user_id);
create index if not exists subscriptions_user_idx          on subscriptions (user_id);
create index if not exists analytics_events_name_idx       on analytics_events (name, occurred_at);
create index if not exists error_logs_occurred_idx         on error_logs (occurred_at);
