"""FastAPI app factory. Run locally: `uv run uvicorn app.main:create_app --factory --reload`."""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI

from app.api.v1 import router as v1_router
from app.core.clock import Clock, SystemClock
from app.core.config import Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.rate_limit import RateLimiter
from app.repositories import UnitOfWorkFactory


def create_app(settings: Settings | None = None, *, uow_factory: UnitOfWorkFactory | None = None,
               clock: Clock | None = None,
               health_probes: dict[str, Callable[[], Awaitable[bool]]] | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="FitPlan Pro API", version="1.0.0",
                  docs_url="/api/v1/docs", openapi_url="/api/v1/openapi.json", redoc_url=None)
    app.state.settings = settings
    app.state.clock = clock or SystemClock()
    app.state.uow_factory = uow_factory
    app.state.health_probes = health_probes or {}
    app.state.auth_rate_limiter = RateLimiter(settings.auth_rate_limit, settings.auth_rate_window_seconds)

    install_error_handlers(app)
    app.include_router(v1_router)
    return app
