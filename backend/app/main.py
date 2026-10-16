"""FastAPI app factory. Run locally: `uv run uvicorn app.main:create_app --factory --reload`."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from functools import partial

from fastapi import FastAPI

from app.api.v1 import router as v1_router
from app.core.clock import Clock, SystemClock
from app.core.config import Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.rate_limit import RateLimiter
from app.db.mongo import create_mongo_client, ensure_indexes, mongo_probe
from app.db.session import create_engine_from_url
from app.repositories import UnitOfWorkFactory
from app.repositories.sql import postgres_probe, sql_uow_factory

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, *, uow_factory: UnitOfWorkFactory | None = None,
               clock: Clock | None = None,
               health_probes: dict[str, Callable[[], Awaitable[bool]]] | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    # Without an injected unit of work the app talks to PostgreSQL; tests inject an in-memory one instead.
    engine = None
    health_probes = dict(health_probes or {})
    database_url = settings.resolved_database_url
    if uow_factory is None and database_url:
        engine = create_engine_from_url(database_url)
        uow_factory = sql_uow_factory(engine)
        health_probes.setdefault("postgres", partial(postgres_probe, engine))

    mongo_client = mongo_db = None
    mongo_url = settings.resolved_mongo_url
    if mongo_url:
        mongo_client = create_mongo_client(mongo_url)
        mongo_db = mongo_client[settings.mongo_db]
        health_probes.setdefault("mongo", partial(mongo_probe, mongo_client))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if mongo_db is not None:
            try:
                await ensure_indexes(mongo_db)
            except Exception:  # noqa: BLE001  (MongoDB down: /health reports it, the API still starts)
                log.exception("could not create MongoDB indexes")
        yield
        if engine is not None:
            await engine.dispose()
        if mongo_client is not None:
            await mongo_client.close()

    app = FastAPI(title="FitPlan Pro API", version="1.0.0", lifespan=lifespan,
                  docs_url="/api/v1/docs", openapi_url="/api/v1/openapi.json", redoc_url=None)
    app.state.settings = settings
    app.state.clock = clock or SystemClock()
    app.state.uow_factory = uow_factory
    app.state.db_engine = engine
    app.state.mongo_client = mongo_client
    app.state.mongo_db = mongo_db
    app.state.health_probes = health_probes
    app.state.auth_rate_limiter = RateLimiter(settings.auth_rate_limit, settings.auth_rate_window_seconds)

    install_error_handlers(app)
    app.include_router(v1_router)
    return app
