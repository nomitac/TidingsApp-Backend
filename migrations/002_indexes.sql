-- Indexes for sync pulls (server_updated_at > since) and ownership lookups.

create index if not exists tidings_occasion_years_owner_idx        on tidings_occasion_years (owner_id);
create index if not exists tidings_occasion_years_sua_idx          on tidings_occasion_years (server_updated_at);

create index if not exists tidings_year_members_user_idx           on tidings_year_members (user_id, status);
create index if not exists tidings_year_members_year_sua_idx       on tidings_year_members (occasion_year_id, server_updated_at);

create index if not exists tidings_groups_year_sua_idx             on tidings_groups (occasion_year_id, server_updated_at);
create index if not exists tidings_recipients_year_sua_idx         on tidings_recipients (occasion_year_id, server_updated_at);
create index if not exists tidings_recipients_person_idx           on tidings_recipients (person_id);
create index if not exists tidings_gifts_year_sua_idx              on tidings_gifts (occasion_year_id, server_updated_at);
create index if not exists tidings_gifts_recipient_idx             on tidings_gifts (recipient_id);
create index if not exists tidings_activity_log_year_sua_idx       on tidings_activity_log (occasion_year_id, server_updated_at);

create index if not exists tidings_wishlists_owner_idx             on tidings_wishlists (owner_user_id, server_updated_at);
create index if not exists tidings_wishlist_items_wishlist_sua_idx on tidings_wishlist_items (wishlist_id, server_updated_at);
create index if not exists tidings_claims_item_idx                 on tidings_claims (wishlist_item_id, status);

create index if not exists tidings_exchanges_organizer_sua_idx     on tidings_secret_santa_exchanges (organizer_id, server_updated_at);
create index if not exists tidings_push_tokens_user_idx            on tidings_push_tokens (user_id);
create index if not exists tidings_subscriptions_user_idx          on tidings_subscriptions (user_id);
create index if not exists tidings_analytics_events_name_idx       on tidings_analytics_events (name, occurred_at);
create index if not exists tidings_error_logs_occurred_idx         on tidings_error_logs (occurred_at);
