# FitPlan Pro backend

Run locally: `docker compose up -d`, then `uv run uvicorn app.main:create_app --factory --reload` from `backend/`.
Domain notes are in [README_DOMAIN.md](README_DOMAIN.md).

## Hardening (B-29)

Every HTTP answer carries `X-Request-ID` (the client's value if it matches `[A-Za-z0-9._-]{1,64}`, otherwise a
generated one); the same id is in every JSON log line of the request (`request_id`), next to one access-log line per
request (method, path without query string, status, duration). Answers also carry `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` and a restrictive
`Content-Security-Policy` (not on the Swagger page). A body above the limit is refused with 413 `payload_too_large`;
an exhausted connection pool answers 503 with `Retry-After: 1` instead of 500.

| Variable | Default | Meaning |
|---|---|---|
| `DB_POOL_SIZE` | 10 | Connections kept open per worker process |
| `DB_MAX_OVERFLOW` | 10 | Extra connections per process under a burst |
| `DB_POOL_TIMEOUT_SECONDS` | 10 | How long a request waits for a free connection before the 503 |
| `DB_POOL_RECYCLE_SECONDS` | 1800 | Connections older than this are replaced (survives idle disconnects) |
| `MAX_BODY_BYTES` | 1048576 | Body limit of every route except the photo upload |
| `MAX_UPLOAD_BYTES` | 9437184 | Body limit of `POST /meals/recognitions` (the contract allows 8 MiB photos plus form overhead) |
| `CORS_ORIGINS` | empty (CORS off) | Comma separated origins; the mobile app does not need it |
| `HSTS_MAX_AGE_SECONDS` | 0 (off) | Set only behind HTTPS, e.g. 31536000 |

## Capacity: 500 concurrent sessions

A session is mostly idle (a person reading or training), so 500 sessions mean tens of requests per second at the
same moment, not 500 queries at once. A request holds a connection for a few milliseconds, so one connection serves
a hundred or more requests per second. What has to add up:

    workers x (DB_POOL_SIZE + DB_MAX_OVERFLOW)  <=  PostgreSQL max_connections - 10 (reserve for admin and migrations)

With PostgreSQL's default `max_connections = 100`, 4 workers x 20 = 80 fits. Recommended start:

    uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --workers 4

- **bcrypt** (about 250 ms of CPU at 12 rounds) runs in worker threads, so sign-ins and registrations never freeze
  the event loop that serves everyone else. Roughly one core per 4 sign-ins per second; this is what limits the
  number of logins per second, not the connection pool.
- **Rate limiter**: the sliding window of the auth routes (`AUTH_RATE_LIMIT`) lives in process memory, so the real
  limit is `workers x AUTH_RATE_LIMIT` per client IP. Put an IP limit at the reverse proxy for a hard guarantee.
- **Waiting is not failing**: when all connections are busy, requests queue for up to `DB_POOL_TIMEOUT_SECONDS`;
  only after that the client gets 503 and retries. `tests/db/test_load_smoke.py` runs 500 concurrent sessions
  (2500 requests) through a pool of 5 + 5 connections and requires zero 5xx and never more than 10 connections.
- To check a real deployment, watch `pg_stat_activity` (connections should stay below the sum above) and the
  `database connection pool exhausted` log line (it should never appear).

## Scheduler and push (B-26)

Scheduled work is not part of the web workers. Run **one** extra process next to the API:

    python -m app.jobs loop      # every SCHEDULER_INTERVAL_SECONDS (default 900 = 15 min); `once` runs a single pass

Each pass runs three idempotent jobs, each isolated from the others' failures:

1. **Weekly reports** (algorithms.md 12): for every active user whose local time is past Monday 07:00, create the
   report for the previous Monday-Sunday if the user has 7 days of history, plus a `progress_update` notification, in
   one transaction. A period that already has a report (made by hand or by an earlier pass) is skipped, so running
   it twice, concurrently, or after downtime (it catches up) never duplicates.
2. **Photo cleanup**: deletes files under `PHOTO_DIR/meals/` older than 6 h that no live MongoDB document and no
   `recognition_ai.image_url` refers to. Without MongoDB it deletes nothing.
3. **Push delivery**: every notification without `sent_at` is pushed through Expo to the user's devices and marked
   sent. Tokens that Expo reports as `DeviceNotRegistered` are deleted. When Expo cannot be reached the row stays
   queued and the next pass retries; after 24 h it is dropped from the queue (it remains in the inbox).

| Variable | Default | Meaning |
|---|---|---|
| `PUSH_ENABLED` | true | `false` skips push delivery (notifications still appear in the inbox) |
| `EXPO_PUSH_URL` | https://exp.host/--/api/v2/push/send | Expo push endpoint |
| `EXPO_ACCESS_TOKEN` | empty | Only if the Expo project enforces push security |
| `SCHEDULER_INTERVAL_SECONDS` | 900 | Pause between passes of `loop` |

## Container (B-01)

`backend/Dockerfile` builds one image (build context = repository root) that `docker-compose.yml` uses for four roles:
`migrate` (runs `alembic upgrade head` once and exits), `backend` (uvicorn, `WEB_WORKERS` workers, default 4,
published on `API_PORT`, default 8000), `scheduler` (`python -m app.jobs loop`, exactly one) and `seed`
(`docker compose --profile tools run --rm seed`). The image runs as an unprivileged user, holds no `.env` (settings
come from the compose environment) and keeps meal photos in the `photos` volume (`PHOTO_DIR=/data/photos`). CI builds
the stack, loads the seed data and calls the API (job "Docker stack starts and answers").
