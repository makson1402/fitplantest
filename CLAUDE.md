# FitPlan Pro

Engineering thesis project (Lublin University of Technology): mobile app for personalized training and diet plans with AI meal photo recognition. Built by three AI agents, one per role, supervised by three humans. Read this file fully before any work.

## Stack
- Backend: Python, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic. API prefix `/api/v1`.
- PostgreSQL 16 (all persistent data) + MongoDB (TTL buffer `meal_recognitions`, 6 h).
- `ai-service`: separate container, pretrained `BinhQuocNguyen/food-recognition-model` behind a `RecognitionProvider` interface.
- Mobile: React Native, Expo, TypeScript, expo-sqlite (offline), Android 10+ primary.
- Local environment: docker-compose. Never commit `.env`; extend `.env.example`.

## Source of truth (higher wins on conflict)
1. `docs/requirements.md` (binding requirement IDs)
2. `docs/decisions.md`
3. `docs/algorithms.md` (formulas, constants, test vectors) and `scripts/algorithms_reference.py`
4. `docs/database/schema_postgres.sql` / `schema_postgres.md` / `mongo_buffer.md`
5. `docs/api/openapi.yaml` (the API contract; frozen at G1, changed only through a contract change PR reviewed by API and APP)
6. `docs/tasks.md` (what to do and in which order)
Old files `scheme_mysql.sql` and `ERD.png` are obsolete. Do not use them.

## Ownership (do not edit outside your area)
- DATA: `database/`, `backend/app/db/`, `backend/alembic/`, seeds, `scripts/` for the DB.
- API: `backend/app/` except `db/`, `ai-service/`.
- APP: `mobile/`.
- `docs/` changes go in a `docs/` branch and need approval from every role whose area they touch.

## Workflow (Waterfall)
- Phases R, D, B/M, T, Z, W with gates G0-G5 (see `docs/tasks.md`). Do not start a task whose "Depends on" items are not merged. Do not work on a later phase before its gate is signed by the humans.
- One task = one branch (`db/`, `api/`, `app/`, `docs/` + task id, e.g. `api/B-11-training-generator`) = one pull request, one human approval.
- The PR title starts with the task id; the description lists the FR/NFR ids implemented and how "Done when" was verified.
- Every PR includes tests and passes CI. Never merge your own PR.

## When the spec is silent or contradictory
Do not invent behaviour. Append the question to `docs/questions.md` (task id, what is unclear, your proposed default), continue with other work, and mention it in the PR. A human answers by editing the docs.

## Rules that are easy to get wrong
- Algorithms: implement exactly `docs/algorithms.md`; its numeric vectors are the unit tests. Constants live in one module.
- Plans change only after an explicit signal (RPE >= 9 or an incomplete set, FR-A4). Never otherwise.
- Object-level authorization on every query: a user only reads and writes their own rows.
- Passwords: bcrypt, max 72 bytes (reject longer input). Tokens: access 15 min, refresh 30 days with rotation and reuse detection.
- Errors use the common model from the OpenAPI (`code`, `message`, `details[]`); validation is HTTP 422.
- Sync: client UUIDs, optimistic concurrency via `base_updated_at`, tombstones; logs are append-only.
- Code, identifiers and comments in English; thesis documentation in Polish. No secrets, tokens or full emails in logs.

## Definition of done (every task)
Code + tests green; linters clean; OpenAPI conformance (backend: `schemathesis` or contract tests; mobile: generated types unchanged); docs updated if behaviour changed; PR description cites FR ids.

## Commands
- Start data stores: `docker compose up -d`
- Schema check: `psql -d <db> -f docs/database/schema_postgres.sql && psql -d <db> -f scripts/test_schema.sql`
- Algorithm vectors: `python3 scripts/algorithms_reference.py --check`
- OpenAPI structural check: `python3 scripts/check_openapi.py docs/api/openapi.yaml`
- Agent kickoff prompts: `docs/agents/{data,api,app}.md`
