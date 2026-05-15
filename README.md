# ThirdParty Access (Flask)

## Project Overview
- **Name**: ThirdParty Access
- **Goal**: Consent-based seeker/provider platform with access requests, approvals, payments, and provider payouts.
- **Tech Stack**: Flask, Gunicorn, PostgreSQL (production), SQLite (optional local dev), Flask-Migrate/Alembic.

## What Was Hardened in This Update
1. **Production DB is PostgreSQL-only**
   - App now reads `DATABASE_URL` from env.
   - Legacy Render URI is normalized (`postgres://` → `postgresql://`).
   - In production, missing `DATABASE_URL` raises startup error (no SQLite fallback).

2. **Migration-based schema management**
   - Flask-Migrate/Alembic initialized under `migrations/`.
   - Initial migration creates all required tables and indexes.
   - Production startup no longer performs ad-hoc schema creation.

3. **Safety / data-loss prevention**
   - Removed automatic deploy seeding/reset behavior.
   - Build now runs `flask --app run.py db upgrade` (controlled by env toggle).
   - No startup path drops data.

4. **Secret handling improvements**
   - `SECRET_KEY` remains env-driven and enforced in production.
   - No credentials hardcoded in source.

## Functional Entry URIs (Summary)
- **Core**: `/`, `/about`, `/dashboard`, `/health`
- **Auth**: `/login`, `/register`, `/logout`, `/switch-role`, `/forgot-password`, `/reset-password`
- **Auth APIs**: `/api/auth/register`, `/api/auth/login`, `/api/auth/user/<user_id>`
- **Provider**: `/provider-setup`, `/search`, `/provider/verify`
- **Provider APIs**: `/api/providers/*`, `/api/access/check/<seeker_id>/<provider_id>`, `/api/provider/verify/*`
- **Requests APIs/UI**: `/requests/*`, `/api/requests/*`
- **Access APIs/UI**: `/access/*`, `/api/access/*`
- **Payments APIs/UI**: `/payments/*`, `/api/payments/*`
- **Notifications APIs/UI**: `/notifications/*`, `/api/notifications/*`
- **Reviews APIs/UI**: `/reviews/*`, `/api/reviews/*`
- **Admin APIs/UI**: `/admin/*`, `/api/admin/*`

## Data Models / Storage
- **Production storage**: Render Postgres via `DATABASE_URL`
- **Local optional**: SQLite file (`data/database.sqlite`) only when `DATABASE_URL` is unset and `FLASK_ENV` is not production.
- **Primary tables**: `users`, `providers`, `access_requests`, `access_grants`, `messages`, `notifications`, `payments`, `payouts`, `reviews`, `login_attempts`, `platform_settings`, `verification_requests`, `password_reset_tokens`.

## Required Environment Variables (Render)
- `DATABASE_URL` (**required in production**)
- `SECRET_KEY` (**required in production**)
- `FLASK_ENV=production`
- `RUN_DB_MIGRATIONS=1` (recommended)
- Optional app vars:
  - `PAYCHANGU_SECRET_KEY`
  - `PAYCHANGU_PUBLIC_KEY`
  - `PAYCHANGU_WEBHOOK_SECRET`
  - `BASE_URL`

## Deploy Notes (Render)
1. Build command: `./build.sh`
2. Start command: `gunicorn run:app --bind 0.0.0.0:$PORT --workers 2 --threads 2`
3. Ensure `DATABASE_URL` points to your Render Postgres instance.

## Reliability Note
Render free web services can sleep and have cold starts after inactivity. For better uptime/performance consistency, use a paid plan.

## Not Yet Implemented
- Transactional email provider for password reset links.
- Automated test suite (unit/integration).
- Full production observability (structured logs/tracing).

## Recommended Next Steps
1. Add CI pipeline: lint + smoke test + `flask db upgrade --sql` checks.
2. Add scheduled automated Postgres backups and restore drills.
3. Add app health checks that validate DB connectivity.

## Last Updated
2026-05-14
