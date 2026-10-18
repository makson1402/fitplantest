# FitPlan Pro backend image (B-01). Build context is the repository root:
#   docker build -f backend/Dockerfile -t fitplan-backend .
# The same image runs the API (default), the migrations (`alembic upgrade head`), the scheduler
# (`python -m app.jobs loop`) and the seed loader (`python /app/database/seed/load.py`).

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /usr/local/bin/uv
WORKDIR /app/backend
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH=/app/backend/.venv/bin:$PATH
RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin fitplan \
    && mkdir -p /data/photos && chown fitplan /data/photos
WORKDIR /app/backend
COPY --from=build /app/backend/.venv ./.venv
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
COPY database/seed /app/database/seed
USER fitplan
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"]
# Workers: see backend/README.md (workers x pool size must fit PostgreSQL max_connections).
CMD ["sh", "-c", "exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --workers ${WEB_WORKERS:-4}"]
