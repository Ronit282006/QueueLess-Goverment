# QueueLess Government Office

QueueLess is an AI-assisted queue operating system for public service offices. Citizens reserve a virtual token, follow a live ETA, and arrive when needed. Staff manage counters and service transitions; administrators review analytics, fairness, system health, and counter recommendations.

## What works

- Citizen registration/login, JWT sessions, password hashing, and role-based citizen/staff/admin APIs.
- Office, department, service, and document directory; QR token creation, arrival check-in, cancellation, feedback, and token event history.
- Atomic per-office/service token sequences, PostgreSQL persistence, Redis queue cache, distributed rate limits, and Redis Pub/Sub WebSocket fan-out.
- Explainable wait estimates that use queue position, active counters, service history, congestion, and no-show observations. Gradient-boosting models are trained/evaluated from labelled service records; measured MAE/R² and sample count are exposed. Estimates fall back to a transparent analytical model when evidence is weak.
- Staff counter availability, call/start/skip/complete workflow, service-time recording, and audit history.
- Admin-configurable priority rules, human-approved counter recommendations, analytics (demand, peak hours, SLA, efficiency, feedback), and operational health.
- Background email delivery with log mode by default, SMTP configuration, retries, approach-stage updates, and no-show grace handling.
- English/Hindi/Gujarati locale files, accessibility text/contrast controls, responsive React UI, and a concurrent load script.

Demo and synthetic historical records are labelled `DEMO`; they are not government data. Prediction confidence is derived from available evaluated model metrics or conservative sample-based confidence, not presented as a validated government accuracy claim.

## Architecture

```text
Browser (React / TypeScript / Vite)
          | REST + WebSocket
FastAPI instances (stateless request handling)
          |                  \
PostgreSQL source of truth   Redis cache / rate limits / PubSub / email queue
          |
Background worker (email delivery + no-show/stage sweeps)
```

Compose provisions Postgres, Redis, a one-shot idempotent seed job, API, worker, and frontend. The API can be run as multiple replicas behind a load balancer; all durable state is in PostgreSQL, Redis carries cross-instance realtime events, and token numbers are allocated under a database transaction/row lock. SQLite is intended only for isolated tests and lightweight local development.

## Run locally

Requirements: Docker Desktop with Compose. From the repository root:

```bash
docker compose up --build
```

The seed job creates labelled demo offices, history, and accounts on an empty database. Visit <http://localhost:5173>; Swagger is at <http://localhost:8000/docs>.

Demo accounts use password `Demo@1234`:

| Role | Email |
|---|---|
| Admin | `admin@queueless.demo` |
| Staff | `staff@queueless.demo` |
| Citizen | `citizen@queueless.demo` |

To seed a directly-run backend, set `DATABASE_URL`, install `backend/requirements.txt`, then run `python -m app.seed` from `backend`. Seed skips a non-empty database; `python -m app.seed --force` clears and recreates demo data and should only be used when you intend to erase that database.

## Environment

Copy `.env.example` to `.env` and configure values as needed. Core variables include `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `CORS_ORIGINS`, `EMAIL_MODE` (`log` or `smtp`), `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_STARTTLS`, `SMTP_USE_SSL`, and `FRONTEND_BASE_URL`. Registration uses `OTP_EXPIRY_MIN`, `OTP_RESEND_COOLDOWN_SEC`, `OTP_MAX_SENDS_PER_HOUR`, and `OTP_MAX_VERIFY_ATTEMPTS`; notifications use `ARRIVAL_BUFFER_MIN` and office incident-response settings. In development log mode, email bodies are written to the backend log so OTP registration can be exercised without a provider. Sensitive email bodies are redacted from production logs. Compose uses a development-only Postgres password by default; replace it and the JWT secret for any shared deployment. Never put secrets in frontend variables.

## Prediction and fairness

The queue estimate decomposes the wait into people ahead, counter capacity, service handling, congestion, and expected no-shows. Completed live services record service duration and actual token wait; the training pipeline reports validation error and only blends a learned model when it beats a baseline. Demo rows are kept distinguishable from live rows. Fairness-aware ordering tracks deferrals and waiting time; office administrators configure priority tags and boosts rather than relying on fixed eligibility rules.

## API and operations

FastAPI OpenAPI groups cover Authentication, Services, Queue, Tokens, Staff, Admin, Analytics, Notifications, System, and WebSocket. Main endpoints include `/api/auth/*`, `/api/offices`, `/api/services/{id}`, `/api/queue`, `/api/tokens`, `/api/staff/*`, `/api/admin/*`, `/api/analytics/*`, and `/ws/queue` / `/ws/tokens/{reference}`.

The dedicated worker uses the same PostgreSQL and Redis as the API. Email defaults to log mode; no paid provider is required. Health endpoints distinguish public API health from admin-only operational detail. Database migrations are managed by Alembic; Compose bootstraps a fresh local database from SQLAlchemy metadata for demo convenience.

## Tests and load profile

Run backend tests from `backend` with `python -m pytest -q`; run the frontend production typecheck/build from `frontend` with `npm run build` (PowerShell users can use `npm.cmd`). The concurrent token/load script is `backend/scripts/load_test.py`, for example:

```bash
python scripts/load_test.py --base http://127.0.0.1:8000 --tokens 500 --concurrency 50 --poll
```

It reports throughput, p50/p95/p99 latency, queue-read latency, status codes, and duplicate-label correctness. `backend/scripts/multi_instance_check.py` verifies Redis WebSocket fan-out between two local API processes when Postgres and Redis are available. No load-test performance result is claimed until run against the target hardware and deployment configuration.

## Known limits

This is a hackathon-ready demonstration, not a certified government deployment. Offline operation is limited to browser connectivity/status handling; durable staff offline writes and conflict-safe synchronization are not implemented. Production rollout still needs deployment-specific privacy/retention policy, secret rotation, TLS/reverse-proxy configuration, and measured load/capacity results. No paid AI, SMS, map, or messaging API is required.
