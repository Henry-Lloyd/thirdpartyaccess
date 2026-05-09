# ThirdParty Access (Flask)

## Project Overview
- **Name**: ThirdParty Access
- **Tagline**: Where Access Meets Consent
- **Goal**: A consent-based platform where seekers can request and pay for access to verified providers.
- **Tech Stack**: Python Flask, SQLite, Tailwind CSS (CDN), Font Awesome

## Completed Features
- Dual-role auth (seeker/provider with same email supported per role)
- Provider profile setup and search
- Access request and grant workflow
- PayChangu payment + payout integration flow
- Wallet and payout history pages
- Admin dashboard basics (account management + broadcast)
- Verification upload/submit flow for providers
- Profile picture upload/remove
- Password reset token flow
- PWA assets (manifest + service worker)
- **Security and reliability improvements in this update:**
  - Added strict API payload validation for auth endpoints
  - Improved login lockout reliability using timezone-aware Python checks
  - Added production `SECRET_KEY` safety guard
  - Added secure response headers (HSTS in production, frame/content/referrer protections)
  - Added `/health` endpoint for monitoring

## Functional Entry URIs (Paths + Parameters)

### Public / Core Pages
- `GET /` — Homepage
- `GET /about` — About page (requires login)
- `GET /dashboard` — User dashboard (requires login)
- `GET /health` — Health status JSON

### Auth
- `GET|POST /login?role=seeker|provider`
- `GET|POST /register?role=seeker|provider`
- `GET /switch-role`
- `GET /logout`
- `GET|POST /forgot-password?role=seeker|provider`
- `GET|POST /reset-password?token=<token>`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/user/<user_id>`

### Provider
- `GET|POST /provider-setup`
- `GET /search?q=<keyword>`
- `GET|POST /provider/verify`
- `POST /api/providers`
- `GET /api/providers/search?q=<keyword>&category=<category>&requesterId=<user_id>`
- `GET /api/providers/<provider_id>?requesterId=<user_id>`
- `GET /api/providers/user/<user_id>`
- `PUT /api/providers/<provider_id>`
- `GET /api/access/check/<seeker_id>/<provider_id>`
- `POST /api/provider/verify/upload`
- `POST /api/provider/verify/submit`
- `GET /api/provider/verify/status`

### Other Modules
- Requests: `/requests/*`, `/api/requests/*`
- Access: `/access/*`, `/api/access/*`
- Payments: `/payments/*`, `/api/payments/*`
- Notifications: `/notifications/*`, `/api/notifications/*`
- Reviews: `/reviews/*`, `/api/reviews/*`
- Admin: `/admin/*`, `/api/admin/*`

## Data Models and Storage
- **Storage**: SQLite (`data/database.sqlite`)
- **Primary tables**: `users`, `providers`, `access_requests`, `access_grants`, `payments`, `payouts`, `notifications`, `reviews`, `verification_requests`, `password_reset_tokens`, `platform_settings`, `login_attempts`

## Features Not Yet Implemented
- Real email delivery for password reset (currently token is shown in UI)
- End-to-end automated tests (unit/integration)
- Full CSRF token middleware across every POST form/API action
- Advanced observability (structured logs, error tracing dashboard)

## Recommended Next Development Steps
1. Integrate transactional email (SendGrid/Resend) for password reset links.
2. Add CSRF protection middleware and hidden form token helpers globally.
3. Add pytest test suite for auth, payments, and admin critical paths.
4. Add role-based audit logs for all admin actions.
5. Add deployment profiles (Render/Railway/Heroku) with environment templates.

## Quick Start
```bash
pip install -r requirements.txt
python run.py --seed
# App: http://localhost:3000
```

## Deployment
- **Platform**: Python-compatible hosts (Render, Railway, Heroku, VPS)
- **Runtime**: `gunicorn run:app`
- **Status**: Ready for deployment
- **Last Updated**: 2026-05-09
