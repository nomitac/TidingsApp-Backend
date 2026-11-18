# Tidings backend

FastAPI service for the Tidings gift-list iOS app. The app talks **only** to this API; this API talks to
Supabase Postgres **only** through PostgREST with the service-role key. The API contract is in
[API_CONTRACT.md](API_CONTRACT.md).

## Run locally

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env            # edit values; leave SUPABASE_URL empty for in-memory storage
APP_KEY=dev-app-key .venv/bin/uvicorn app.main:app --reload --port 8000
```

With `SUPABASE_URL` empty (or `STORAGE_BACKEND=memory`) data lives in process memory and is lost on
restart — handy for the iOS simulator and for tests. Open http://localhost:8000/docs for the OpenAPI UI.

Tests: `.venv/bin/python -m pytest -q`

## Environment variables

| Var | Purpose |
|---|---|
| `APP_KEY` | Shared key the app sends as `X-App-Key` |
| `SUPABASE_URL` | `https://<project>.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | Service-role key (server only, never ship in the app) |
| `STORAGE_BACKEND` | `supabase` or `memory`; defaults to `supabase` when `SUPABASE_URL` is set |
| `PUBLIC_BASE_URL` | Base for wishlist share links (`/w/{slug}`) and OG tags |
| `INVITE_TTL_DAYS` | Co-shopper invite code lifetime (default 14) |
| `APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_BUNDLE_ID`, `APNS_PRIVATE_KEY`, `APNS_USE_SANDBOX` | Token-based APNs. Push is skipped when unset. `APNS_PRIVATE_KEY` is the `.p8` contents (`\n` escapes allowed) |

## Database migrations

Numbered SQL files live in `migrations/`. Apply them in order:

1. Supabase Dashboard → **SQL Editor** → New query.
2. Paste `migrations/001_init.sql`, run. Then `002_indexes.sql`, then `003_grants.sql`, and any later files in number order.

All Tidings tables are named `tidings_*` (in `public`, which the Data API already exposes), so the
project can be shared with another app. The migrations only create, index and grant those 17 tables —
no schema-wide grants, no default-privilege changes, nothing dropped. No dashboard settings needed.

Every table has RLS enabled with **no policies**: the anon key can read nothing, and only the
service-role key used by this API can. Authorization rules (owner / co-shopper / surprise redaction /
hidden claims) are enforced in the API (`app/routers/sync.py`, `app/redaction.py`, `app/claims.py`).

## Deploy on Railway

1. Push this folder as its own GitHub repo, then Railway → New Project → Deploy from GitHub repo.
2. Railway builds the `Dockerfile` (`railway.json` sets the healthcheck to `/health`).
3. Variables: set `APP_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `PUBLIC_BASE_URL`
   (your Railway domain, `https://…`), and APNs vars if you use push.
4. Put the Railway URL and `APP_KEY` into the iOS app's config.

## Layout

```
app/
  main.py            app factory, router wiring, /health
  config.py          pydantic-settings
  auth.py            X-App-Key + X-User-Id dependencies
  repo.py            Repository protocol, SupabaseRepo (PostgREST), MemoryRepo
  schemas.py         synced row shapes + normalisation
  access.py          owner / co-shopper checks
  redaction.py       surprise redaction for the target user
  budget.py          dashboard totals (integer cents)
  claims.py          hidden claiming
  link_parser.py     product page parsing (JSON-LD > OG > title)
  apns.py            APNs sender (ES256 JWT, HTTP/2)
  routers/           users, sync, invites, totals, import_link, wishlists, public_web, telemetry, push, subscriptions
migrations/          numbered .sql files
tests/               pytest (in-memory repo)
```

## Known follow-ups

- StoreKit signed transactions are stored and decoded, but the Apple certificate chain is not yet
  verified (`subscriptions.verified = false`). Verify via the App Store Server API before relying on it for revenue.
- Sync is last-write-wins per row (not per field).
- Secret Santa matches sync only to the organizer's devices; there's no per-participant reveal link yet.
