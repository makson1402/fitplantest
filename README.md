# FitPlan Pro

Mobile application for training and nutrition planning (engineering thesis, Lublin University of Technology).

## Structure

- `backend/` – FastAPI application (Python)
- `database/` – PostgreSQL schema and seed data
- `mobile/` – React Native (Expo) application

## Local setup

1. `cp .env.example .env` (set `JWT_SECRET`)
2. `docker compose up -d --build` starts PostgreSQL, MongoDB, the migrations, the API (<http://localhost:8000/api/v1/docs>) and the scheduler
3. `docker compose --profile tools run --rm seed` loads the exercises and foods (idempotent)

Capacity and configuration of the backend: [backend/README.md](backend/README.md). For development without the
backend container run only `docker compose up -d postgres mongo` and start the API with uv.

## Workflow

Branch from `main` using a prefix (`db/`, `api/`, `app/`), open a Pull Request, get one approval, merge.
