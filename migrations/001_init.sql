-- Tidings schema v1. Apply in the Supabase SQL editor (or `psql`) in numeric order.
-- The API accesses these tables only through PostgREST with the service-role key.
-- RLS is enabled on every table with NO policies, so the anon/authenticated keys can read nothing.
-- Foreign keys between synced tables are intentionally omitted: offline-first clients can
-- push children before parents from another device; the API enforces ownership instead.

-- Shared-project safe: every Tidings table is named `tidings_*`, so it can live in the same Supabase
-- project (and `public` schema) as another app without clashing. Nothing else is created or changed.

-- ---------------------------------------------------------------- users
create table if not exists tidings_users (
  id                uuid primary key,
  display_name      text not null default '',
  default_currency  char(3) not null default 'USD',
  is_pro            boolean not null default false,
  pro_expires_at    timestamptz,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  deleted_at        timestamptz,
  server_updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------- occasion years
create table if not exists tidings_occasion_years (
  id                 uuid primary key,
  owner_id           uuid not null,
  name               text not null default '',
  occasion_type      text not null default 'christmas' check (occasion_type in ('christmas','hanukkah','birthday','holiday')),
  year               integer not null,
  total_budget_cents bigint,
  currency           char(3) not null default 'USD',
  occasion_date      timestamptz not null,
  is_archived        boolean not null default false,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  deleted_at         timestamptz,
  server_updated_at  timestamptz not null default now()
);

create table if not exists tidings_year_members (
  id                uuid primary key,
  occasion_year_id  uuid not null,
  user_id           uuid,
  role              text not null check (role in ('owner','co_shopper')),
  invited_email     text not null default '',
  display_name      text not null default '',
  status            text not null default 'invited' check (status in ('invited','accepted')),
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  deleted_at        timestamptz,
  server_updated_at timestamptz not null default now()
);

create table if not exists tidings_groups (
  id                uuid primary key,
  occasion_year_id  uuid not null,
  name              text not null default '',
  sort_order        integer not null default 0,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  deleted_at        timestamptz,
  server_updated_at timestamptz not null default now()
);

create table if not exists tidings_recipients (
  id                    uuid primary key,
  person_id             uuid not null,
  occasion_year_id      uuid not null,
  name                  text not null default '',
  avatar_emoji          text not null default '🎁',
  relationship          text not null default '',
  group_ids             uuid[] not null default '{}',
  budget_cents          bigint,
  notes_private         text not null default '',
  sizes_notes           text not null default '',
  shipping_address      text not null default '',
  linked_user_id        uuid,
  wishlist_id           uuid,
  external_wishlist_url text not null default '',
  sort_order            integer not null default 0,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),
  deleted_at            timestamptz,
  server_updated_at     timestamptz not null default now()
);

create table if not exists tidings_gifts (
  id                      uuid primary key,
  occasion_year_id        uuid not null,
  recipient_id            uuid not null,
  title                   text not null default '',
  status                  text not null default 'idea' check (status in ('idea','to_buy','ordered','shipped','received','wrapped','given')),
  gift_type               text not null default 'regular' check (gift_type in ('regular','stocking_stuffer','card','gift_card','experience','cash')),
  price_paid_cents        bigint,
  price_estimate_cents    bigint,
  currency                char(3) not null default 'USD',
  fx_rate_to_year         double precision not null default 1,
  store                   text not null default '',
  product_url             text not null default '',
  image_url               text not null default '',
  variant                 text not null default '',
  quantity                integer not null default 1 check (quantity > 0),
  notes_private           text not null default '',
  notes_public            text not null default '',
  visibility              text not null default 'co_shopper' check (visibility in ('private','co_shopper')),
  is_surprise_for_user_id uuid,
  purchased_at            timestamptz,
  shipped_at              timestamptz,
  tracking_number         text not null default '',
  carrier                 text not null default '',
  source_wishlist_item_id uuid,
  photos                  jsonb not null default '[]',
  price_at_import_cents   bigint,
  created_by              uuid,
  updated_by              uuid,
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now(),
  deleted_at              timestamptz,
  server_updated_at       timestamptz not null default now()
);

-- Append-only price log (F12, v1.1 price tracking).
create table if not exists tidings_price_history (
  id          uuid primary key default gen_random_uuid(),
  gift_id     uuid not null,
  price_cents bigint not null,
  currency    char(3) not null,
  checked_at  timestamptz not null default now(),
  source_url  text not null default ''
);

-- ---------------------------------------------------------------- wishlists & claims
create table if not exists tidings_wishlists (
  id                     uuid primary key,
  owner_user_id          uuid not null,
  owner_name             text not null default '',
  occasion_year_id       uuid,
  title                  text not null default '',
  slug                   text not null unique,
  is_public_link_enabled boolean not null default true,
  allow_guest_claims     boolean not null default true,
  reveal_claims_after    timestamptz,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now(),
  deleted_at             timestamptz,
  server_updated_at      timestamptz not null default now()
);

create table if not exists tidings_wishlist_items (
  id                uuid primary key,
  wishlist_id       uuid not null,
  title             text not null default '',
  product_url       text not null default '',
  image_url         text not null default '',
  price_cents       bigint,
  currency          char(3) not null default 'USD',
  variant           text not null default '',
  priority          integer not null default 2 check (priority between 1 and 3),
  notes_public      text not null default '',
  sort_order        integer not null default 0,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  deleted_at        timestamptz,
  server_updated_at timestamptz not null default now()
);

-- Claims are NEVER returned to the wishlist owner (enforced in the API).
create table if not exists tidings_claims (
  id                uuid primary key,
  wishlist_item_id  uuid not null,
  claimer_user_id   uuid,
  guest_token       text,
  claimer_name      text not null default '',
  claimer_email     text not null default '',
  status            text not null default 'claimed' check (status in ('claimed','purchased','released')),
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  deleted_at        timestamptz,
  server_updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------- secret santa
create table if not exists tidings_secret_santa_exchanges (
  id                        uuid primary key,
  occasion_year_id          uuid not null,
  name                      text not null default '',
  budget_cents              bigint,
  currency                  char(3) not null default 'USD',
  draw_date                 timestamptz not null default now(),
  organizer_id              uuid not null,
  participants              jsonb not null default '[]',
  exclusions                jsonb not null default '[]',
  matches                   jsonb not null default '[]',
  organizer_can_see_matches boolean not null default false,
  status                    text not null default 'draft' check (status in ('draft','drawn')),
  created_at                timestamptz not null default now(),
  updated_at                timestamptz not null default now(),
  deleted_at                timestamptz,
  server_updated_at         timestamptz not null default now()
);

-- ---------------------------------------------------------------- activity, invites
create table if not exists tidings_activity_log (
  id                   uuid primary key,
  occasion_year_id     uuid not null,
  actor_user_id        uuid not null,
  actor_name           text not null default '',
  entity_type          text not null default '',
  entity_id            uuid not null,
  action               text not null default '',
  summary_redacted     text not null default '',
  summary_full         text not null default '',
  surprise_for_user_id uuid,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now(),
  deleted_at           timestamptz,
  server_updated_at    timestamptz not null default now()
);

create table if not exists tidings_invites (
  id                uuid primary key,
  code              text not null unique,
  occasion_year_id  uuid not null,
  created_by        uuid not null,
  expires_at        timestamptz not null,
  accepted_by       uuid,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  deleted_at        timestamptz,
  server_updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------- push, subscriptions
create table if not exists tidings_push_tokens (
  id                uuid primary key,
  user_id           uuid not null,
  token             text not null unique,
  platform          text not null default 'ios',
  environment       text not null default 'production' check (environment in ('sandbox','production')),
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  deleted_at        timestamptz,
  server_updated_at timestamptz not null default now()
);

create table if not exists tidings_subscriptions (
  id                      uuid primary key,
  user_id                 uuid not null,
  product_id              text not null,
  transaction_id          text not null,
  original_transaction_id text not null default '',
  expires_at              timestamptz,
  signed_transaction      text not null default '',
  verified                boolean not null default false,
  created_at              timestamptz not null default now()
);

-- ---------------------------------------------------------------- telemetry (own tables, no 3rd-party SDK)
create table if not exists tidings_analytics_events (
  id          uuid primary key,
  user_id     uuid,
  name        text not null,
  properties  jsonb not null default '{}',
  occurred_at timestamptz not null,
  received_at timestamptz not null default now()
);

create table if not exists tidings_error_logs (
  id          uuid primary key,
  user_id     uuid,
  message     text not null,
  context     jsonb not null default '{}',
  occurred_at timestamptz not null,
  app_version text not null default '',
  received_at timestamptz not null default now()
);

-- ---------------------------------------------------------------- RLS: on, no policies
alter table tidings_users          enable row level security;
alter table tidings_occasion_years enable row level security;
alter table tidings_year_members   enable row level security;
alter table tidings_groups         enable row level security;
alter table tidings_recipients     enable row level security;
alter table tidings_gifts          enable row level security;
alter table tidings_price_history  enable row level security;
alter table tidings_wishlists      enable row level security;
alter table tidings_wishlist_items enable row level security;
alter table tidings_claims         enable row level security;
alter table tidings_secret_santa_exchanges enable row level security;
alter table tidings_activity_log   enable row level security;
alter table tidings_invites        enable row level security;
alter table tidings_push_tokens    enable row level security;
alter table tidings_subscriptions  enable row level security;
alter table tidings_analytics_events enable row level security;
alter table tidings_error_logs     enable row level security;
