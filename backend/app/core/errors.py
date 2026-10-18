"""Common error model from the OpenAPI contract (`Error`: code, message, details[]) and its handlers."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, details: list[dict[str, Any]] | None = None,
                 headers: dict[str, str] | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details, self.headers = status, code, message, details, headers


def unauthorized(code: str = "unauthorized", message: str = "Missing or invalid credentials") -> AppError:
    return AppError(401, code, message, headers={"WWW-Authenticate": "Bearer"})


def not_found(message: str = "Not found") -> AppError:
    return AppError(404, "not_found", message)


def error_body(code: str, message: str, details: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if details:
        body["details"] = details
    return body


# Pydantic error types -> detail codes used by the contract (e.g. out_of_range, required, too_long).
_DETAIL_CODES = {
    "missing": "required",
    "string_too_long": "too_long", "too_long": "too_long",
    "string_too_short": "too_short", "too_short": "too_short",
    "greater_than": "out_of_range", "greater_than_equal": "out_of_range",
    "less_than": "out_of_range", "less_than_equal": "out_of_range",
    "value_error": "invalid", "enum": "invalid", "literal_error": "invalid",
    # wrong JSON type or unparsable value
    "int_parsing": "invalid", "int_type": "invalid", "int_from_float": "invalid", "float_parsing": "invalid",
    "float_type": "invalid", "finite_number": "invalid", "date_parsing": "invalid", "date_type": "invalid",
    "date_from_datetime_inexact": "invalid", "bool_parsing": "invalid", "bool_type": "invalid",
    "string_type": "invalid", "list_type": "invalid",
}


def _validation_details(exc: RequestValidationError) -> list[dict[str, Any]]:
    details = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ())]
        if loc and loc[0] in ("body", "query", "path", "header"):
            loc = loc[1:]
        message = str(err.get("msg", "")).removeprefix("Value error, ")
        # Never echo `input`: it may contain a password.
        err_type = err.get("type", "invalid")
        details.append({"field": ".".join(loc), "code": _DETAIL_CODES.get(err_type, err_type), "message": message})
    return details


_HTTP_CODES = {401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "not_found", 409: "conflict",
               413: "payload_too_large", 415: "unsupported_media_type", 429: "rate_limited"}


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.error("unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(error_body("internal_error", "Internal server error"), status_code=500)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(error_body(exc.code, exc.message, exc.details), status_code=exc.status, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(error_body("validation_error", "Invalid input", _validation_details(exc)), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "internal_error" if exc.status_code >= 500 else "validation_error")
        return JSONResponse(error_body(code, str(exc.detail)), status_code=exc.status_code,
                            headers=getattr(exc, "headers", None))

    @app.exception_handler(DBAPIError)
    async def _database_error(request: Request, exc: DBAPIError) -> JSONResponse:
        """PostgreSQL refused a value (out of range for the column, a NUL character in text, ...): that is the client's
        input, not a server fault, so answer 422 like a validation error. SQLSTATE class 22 is "data exception". The
        known cases are checked earlier with field paths (app/schemas/ids.py, the services); this is the safety net.
        Any other database error is a real fault and stays a 500."""
        sqlstate = str(getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None) or "")
        if not (isinstance(exc, DataError) or sqlstate.startswith("22")):
            return await _unhandled(request, exc)
        log.warning("database rejected a value on %s %s: %s", request.method, request.url.path, type(exc.orig).__name__)
        return JSONResponse(error_body("validation_error", "Invalid input", [
            {"code": "invalid_value", "message": "A value is outside what can be stored"}]), status_code=422)

    @app.exception_handler(PoolTimeoutError)
    async def _pool_exhausted(request: Request, exc: PoolTimeoutError) -> JSONResponse:
        """No connection became free within the pool timeout: the server is overloaded, the client may retry."""
        log.error("database connection pool exhausted on %s %s", request.method, request.url.path)
        return JSONResponse(error_body("internal_error", "The server is busy, try again shortly"), status_code=503,
                            headers={"Retry-After": "1"})

    app.add_exception_handler(Exception, _unhandled)
