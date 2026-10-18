"""Hardening middleware (B-29): request ids, access log, security headers, request body size limits, CORS.

Pure ASGI (no `BaseHTTPMiddleware`): it does not buffer bodies, does not copy contextvars between tasks and adds
no per-request task, which matters at the 500-concurrent-sessions target (NFR capacity).
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.logging import request_id_var

log = logging.getLogger("app.access")

REQUEST_ID_HEADER = "x-request-id"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
UPLOAD_PATH_SUFFIX = "/meals/recognitions"  # POST only: the photo upload has its own, larger limit


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope["headers"]:
        if key == name:
            return value.decode("latin-1")
    return None


def _with_header(headers: list[tuple[bytes, bytes]], name: bytes, value: bytes, *, replace: bool = True) -> None:
    for i, (key, _) in enumerate(headers):
        if key.lower() == name:
            if replace:
                headers[i] = (name, value)
            return
    headers.append((name, value))


class RequestIdMiddleware:
    """Takes the client's `X-Request-ID` when it is harmless, otherwise makes one; echoes it in the answer, puts it in
    every log line of the request, and writes one access-log line (method, path without query, status, duration)."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        supplied = _header(scope, REQUEST_ID_HEADER.encode())
        request_id = supplied if supplied and _VALID_REQUEST_ID.match(supplied) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = list(message.get("headers", []))
                _with_header(headers, REQUEST_ID_HEADER.encode(), request_id.encode("ascii"))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            log.info("%s %s -> %s in %d ms", scope["method"], scope["path"], status,
                     round((time.perf_counter() - started) * 1000))
            request_id_var.reset(token)


class SecurityHeadersMiddleware:
    """Headers for an API that returns JSON only: nothing is sniffed, framed, cached or leaked through the referrer."""

    def __init__(self, app: ASGIApp, *, hsts_max_age_seconds: int = 0, docs_prefix: str = "/api/v1/docs"):
        self.app = app
        self.docs_prefix = docs_prefix
        self.fixed = [
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"no-referrer"),
            (b"cross-origin-resource-policy", b"same-site"),
        ]
        if hsts_max_age_seconds:
            self.fixed.append((b"strict-transport-security", f"max-age={hsts_max_age_seconds}".encode()))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_docs = scope["path"].startswith(self.docs_prefix)

        async def send_secured(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                for name, value in self.fixed:
                    _with_header(headers, name, value)
                _with_header(headers, b"cache-control", b"no-store", replace=False)
                if not is_docs:  # the Swagger page loads its own scripts; JSON answers need no resources at all
                    _with_header(headers, b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'")
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_secured)


class _BodyTooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    """413 `payload_too_large` (the contract's error model) for a body above the limit. A declared `Content-Length`
    is refused before anything is read; a body without one (chunked) is counted while it streams."""

    def __init__(self, app: ASGIApp, *, max_body_bytes: int, max_upload_bytes: int):
        self.app, self.max_body_bytes, self.max_upload_bytes = app, max_body_bytes, max_upload_bytes

    def _limit(self, scope: Scope) -> int:
        if scope["method"] == "POST" and scope["path"].rstrip("/").endswith(UPLOAD_PATH_SUFFIX):
            return self.max_upload_bytes
        return self.max_body_bytes

    @staticmethod
    async def _reject(send: Send, limit: int) -> None:
        body = json.dumps({"code": "payload_too_large",
                           "message": f"The request body is larger than {limit} bytes"}).encode()
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                                (b"connection", b"close")]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS", "DELETE"):
            await self.app(scope, receive, send)
            return
        limit = self._limit(scope)
        declared = _header(scope, b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await self._reject(send, limit)
            return

        received = 0
        exceeded = False
        started = False

        async def counting_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise _BodyTooLarge
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal started
            if exceeded:  # the application failed on the cut-off body (a 400 or a 500): the client sees the real cause
                return
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except _BodyTooLarge:
            pass
        if exceeded and not started:
            await self._reject(send, limit)


def install_middleware(app: FastAPI, settings: Settings) -> None:
    """Outermost first: request id (so even a 413 or a CORS answer has one), CORS, security headers, body limit."""
    app.add_middleware(BodySizeLimitMiddleware, max_body_bytes=settings.max_body_bytes,
                       max_upload_bytes=settings.max_upload_bytes)
    app.add_middleware(SecurityHeadersMiddleware, hsts_max_age_seconds=settings.hsts_max_age_seconds)
    origins = settings.cors_origin_list
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins,
                           allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                           allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
                           expose_headers=["X-Request-ID", "Retry-After"], max_age=600)
    app.add_middleware(RequestIdMiddleware)
