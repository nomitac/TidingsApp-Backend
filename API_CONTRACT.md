# Tidings API contract (v1)

Shared by `tidings-ios` and `tidings-backend`. JSON is **snake_case**. Timestamps are ISO-8601 UTC
with milliseconds, e.g. `2026-11-15T22:44:01.123Z`. IDs are UUID strings (lowercase accepted, clients may send uppercase — server must normalise to lowercase). Money is always `*_cents` integer + `currency` (3-letter).

## Auth

Every `/v1/*` route requires:

| Header | Meaning |
|---|---|
| `X-App-Key` | Shared app key (env `APP_KEY`). Wrong/missing → 401 |
| `X-User-Id` | Persistent anonymous user UUID (Keychain + iCloud KV on device). Must be a registered user (except on `POST /v1/users`) → else 401 |

Public routes (no headers): `GET /health`, `GET /w/{slug}`, `POST /w/{slug}/items/{item_id}/claim`, `POST /w/{slug}/items/{item_id}/release`.

## Endpoints

### `GET /health` → `{"status":"ok"}`

### `POST /v1/users` — register / update self
Body `{ "id", "display_name", "default_currency" }` — `id` must equal `X-User-Id`. Returns the user row.

### `GET /v1/me` → `{ "id", "display_name", "default_currency", "is_pro": bool, "pro_expires_at": ts|null }`

### `POST /v1/sync` — offline-first sync
Request:
```json
{ "since": "<server_time from previous sync or null>",
  "changes": { "<table>": [ <row>, ... ] } }
```
Response:
```json
{ "server_time": "<ts>",
  "changes": { "<table>": [ <row>, ... ] },
  "redacted_gifts": [ { "id", "occasion_year_id", "recipient_id", "status", "created_at", "updated_at", "deleted_at" } ],
  "rejected": [ { "table", "id", "reason" } ] }
```
Synced tables (row shapes below): `occasion_years, year_members, groups, recipients, gifts, wishlists, wishlist_items, secret_santa_exchanges, activity_log`.

Write rules (server enforces, rejected rows go to `rejected`, never 4xx for the whole batch):
- Last-write-wins per row: incoming row applied only if `updated_at >= stored updated_at`. Soft delete = `deleted_at` set; rows are never hard-deleted.
- Server stamps `server_updated_at = now()` on every applied write (not exposed to clients); pulls filter on it (`> since`).
- `occasion_years`: create only if `owner_id == user`; update only by owner.
- `year_members`: write only by year owner.
- `groups, recipients, gifts, activity_log`: user must be owner or *accepted* member of `occasion_year_id`.
- `gifts`: a co-shopper may not write a gift whose stored or incoming `is_surprise_for_user_id == user` (rejected `surprise`). Server stamps `created_by` (on insert) / `updated_by`.
- `wishlists`, `wishlist_items`: only wishlist owner (`owner_user_id == user`; items via their wishlist).
- `secret_santa_exchanges`: only `organizer_id == user`.

Read rules (pull returns rows changed since `since` for years the user owns or is an accepted member of, plus the user's own wishlists/items/exchanges):
- **Surprise redaction (Sec. 7):** gifts with `is_surprise_for_user_id == user` are NOT in `changes.gifts`; they appear only in `redacted_gifts` (no title, price, store, url, image, variant, notes, photos).
- Recipients with `linked_user_id == user`: `notes_private`, `budget_cents`, `sizes_notes`, `shipping_address` blanked (`""` / null).
- `activity_log` rows with `surprise_for_user_id == user`: `summary_full` replaced by `summary_redacted`.
- **Claims are never part of sync.**

### `POST /v1/years/{year_id}/invites` (owner only) → `{ "code": "ABCD1234", "expires_at" }`
### `POST /v1/invites/{code}/accept` body `{ "display_name" }` → `{ "occasion_year_id" }`
Creates/updates a `year_members` row `{role: co_shopper, status: accepted, user_id}`. Owner cannot accept own invite (400). Next sync returns the year.

### `GET /v1/years/{year_id}/totals` → server-computed budget totals (F12), same math as the client:
```json
{ "currency", "budget_cents"|null, "spent_cents", "projected_cents", "remaining_cents"|null,
  "people_total", "people_done", "gifts_by_status": {"idea":n,...},
  "per_recipient": [ {"recipient_id","name","budget_cents","spent_cents","projected_cents","gift_count","done_count","over_budget"} ] }
```
Math: per gift, amount in year currency = `round(cents * fx_rate_to_year)` (banker's rounding NOT used; round half away from zero), × `quantity`.
`spent` = Σ `price_paid_cents` (fallback `price_estimate_cents`) for status ≥ `ordered`.
`projected` = spent + Σ `price_estimate_cents` (fallback `price_paid_cents`) for `idea`/`to_buy`.
Done = status ≥ `received`. A person is done when they have ≥1 gift and all gifts are done. Deleted gifts/recipients excluded. Viewer redaction applies (redacted gifts count toward counts but not money).

### `POST /v1/import-link` body `{ "url" }` →
`{ "ok": bool, "url", "title", "image_url", "price_cents"|null, "currency"|null, "store", "variant", "error"|null }`
Server fetches (follow redirects, realistic UA, 8s timeout). Priority JSON-LD `Product` (name, image, offers.price/priceCurrency, color/size) > OpenGraph/Twitter meta (`og:title`, `og:image`, `product:price:amount`, `product:price:currency`) > `<title>`. Store from domain map (amazon→Amazon, target→Target, etsy→Etsy, walmart→Walmart, bestbuy→Best Buy, sephora→Sephora, nordstrom→Nordstrom, apple→Apple, else bare domain). On failure `ok:false` with `store` still filled — never 5xx.

### Wishlists (Sec. 8)
- `GET /v1/wishlists/by-slug/{slug}` →
  `{ "wishlist": {...}, "is_owner": bool, "items": [ {...item, "claimed": bool|null, "claimed_by_me": bool|null } ] }`
  **If requester is the owner, `claimed` and `claimed_by_me` are `null` and no claim data is present anywhere in the response** (unless `reveal_claims_after` has passed — then still null here; use reveal endpoint).
- `POST /v1/wishlist-items/{item_id}/claim` body `{ "claimer_name", "status": "claimed"|"purchased" }` → `{ "claim_id" }`. 409 if already claimed by someone else. 403 if requester owns the wishlist.
- `POST /v1/wishlist-items/{item_id}/release` → releases requester's own claim.
- `GET /v1/wishlists/{wishlist_id}/reveal` → owner only, only after `reveal_claims_after` (else 403) → `{ "items": [{ "item_id", "claimed", "claimer_name" }] }`.

### Public web (no app, no account)
- `GET /w/{slug}` → server-rendered HTML wishlist (OG meta for link previews). Each item shows Claim button or "Claimed". Guest claim form asks name (+ optional email). Guest token kept in an HttpOnly cookie so the guest can release their own claim.
- `POST /w/{slug}/items/{item_id}/claim` (form `claimer_name`, `claimer_email`) → 303 back to page.
- `POST /w/{slug}/items/{item_id}/release` → 303 back.

### Telemetry (own DB tables, no third-party SDK)
- `POST /v1/events` body `{ "events": [ { "name", "properties": {}, "occurred_at" } ] }` → `{ "accepted": n }`
- `POST /v1/errors` body `{ "errors": [ { "message", "context": {}, "occurred_at", "app_version" } ] }` → `{ "accepted": n }`

### Push
- `POST /v1/push-tokens` body `{ "token", "platform": "ios", "environment": "sandbox"|"production" }`
- Server sends APNs (token-based JWT, ES256, PyJWT) e.g. to the owner when a co-shopper accepts an invite. Never notifies a wishlist owner about claims.

### Subscriptions (StoreKit 2)
- `POST /v1/subscriptions` body `{ "product_id", "transaction_id", "original_transaction_id", "expires_at"|null, "signed_transaction": "<JWS>" }` → `{ "is_pro", "pro_expires_at" }`.

## Row shapes (sync)

```
occasion_years: id, owner_id, name, occasion_type(christmas|hanukkah|birthday|holiday), year, total_budget_cents?, currency, occasion_date(ts), is_archived, created_at, updated_at, deleted_at?
year_members:   id, occasion_year_id, user_id?, role(owner|co_shopper), invited_email, display_name, status(invited|accepted), created_at, updated_at, deleted_at?
groups:         id, occasion_year_id, name, sort_order, created_at, updated_at, deleted_at?
recipients:     id, person_id, occasion_year_id, name, avatar_emoji, relationship, group_ids[uuid], budget_cents?, notes_private, sizes_notes, shipping_address, linked_user_id?, wishlist_id?, external_wishlist_url, sort_order, created_at, updated_at, deleted_at?
gifts:          id, occasion_year_id, recipient_id, title, status(idea|to_buy|ordered|shipped|received|wrapped|given), gift_type(regular|stocking_stuffer|card|gift_card|experience|cash),
                price_paid_cents?, price_estimate_cents?, currency, fx_rate_to_year(float), store, product_url, image_url, variant, quantity, notes_private, notes_public,
                visibility(private|co_shopper), is_surprise_for_user_id?, purchased_at?, shipped_at?, tracking_number, carrier, source_wishlist_item_id?,
                photos[{id,kind,local_file,storage_path?}], price_at_import_cents?, created_by?, updated_by?, created_at, updated_at, deleted_at?
wishlists:      id, owner_user_id, owner_name, occasion_year_id?, title, slug, is_public_link_enabled, allow_guest_claims, reveal_claims_after?, created_at, updated_at, deleted_at?
wishlist_items: id, wishlist_id, title, product_url, image_url, price_cents?, currency, variant, priority(1-3), notes_public, sort_order, created_at, updated_at, deleted_at?
secret_santa_exchanges: id, occasion_year_id, name, budget_cents?, currency, draw_date, organizer_id, participants[{id,name,email}], exclusions[{id,giver_id,cannot_draw_id}],
                matches[{giver_id,recipient_id,revealed_at?}], organizer_can_see_matches, status(draft|drawn), created_at, updated_at, deleted_at?
activity_log:   id, occasion_year_id, actor_user_id, actor_name, entity_type, entity_id, action, summary_redacted, summary_full, surprise_for_user_id?, created_at, updated_at, deleted_at?
```
Unknown fields in incoming rows are ignored; missing optional fields default.
