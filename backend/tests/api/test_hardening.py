"""B-29: request ids, security headers, body limits, CORS, pool settings, and an event loop bcrypt cannot block."""
from __future__ import annotations

import asyncio
import time
import uuid

import httpx
from fastapi import APIRouter
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.core.config import Settings
from app.core.logging import JsonFormatter, request_id_var
from app.main import create_app
from tests.conftest import SECRET
from tests.fakes import FakeClock, Store, uow_factory
from tests.support import NO_STORES

BASE = "/api/v1"


def _app(**overrides):
    values = {"jwt_secret": SECRET, "bcrypt_rounds": 4, "auth_rate_limit": 100_000, "_env_file": None, **NO_STORES,
              **overrides}
    clock = FakeClock()
    return create_app(Settings(**values), uow_factory=uow_factory(Store(), clock), clock=clock)


def _http(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


# ------------------------------------------------------------------ request ids

async def test_every_answer_carries_a_request_id():
    async with _http(_app()) as http:
        first = await http.get(f"{BASE}/health")
        second = await http.get(f"{BASE}/health")
        missing = await http.get(f"{BASE}/nope")
    ids = {first.headers["x-request-id"], second.headers["x-request-id"], missing.headers["x-request-id"]}
    assert len(ids) == 3 and all(len(i) == 32 for i in ids)


async def test_a_harmless_client_request_id_is_echoed_and_a_harmful_one_replaced():
    async with _http(_app()) as http:
        good = await http.get(f"{BASE}/health", headers={"X-Request-ID": "mobile-7f3a.1"})
        bad = await http.get(f"{BASE}/health", headers={"X-Request-ID": "a b\"c<script>"})
        long = await http.get(f"{BASE}/health", headers={"X-Request-ID": "x" * 200})
    assert good.headers["x-request-id"] == "mobile-7f3a.1"
    assert bad.headers["x-request-id"] != "a b\"c<script>" and len(bad.headers["x-request-id"]) == 32
    assert len(long.headers["x-request-id"]) == 32


async def test_the_request_id_reaches_the_log_lines_of_the_request():
    app = _app()
    router = APIRouter()

    @router.get("/whoami")
    async def whoami():
        return {"request_id": request_id_var.get()}

    app.include_router(router)
    async with _http(app) as http:
        r = await http.get("/whoami", headers={"X-Request-ID": "trace-1"})
    assert r.json() == {"request_id": "trace-1"} and request_id_var.get() is None  # reset after the request

    import logging
    token = request_id_var.set("trace-2")
    try:
        record = logging.LogRecord("x", logging.INFO, __file__, 1, "hello", None, None)
        assert '"request_id": "trace-2"' in JsonFormatter().format(record)
    finally:
        request_id_var.reset(token)


# ------------------------------------------------------------------ security headers

async def test_security_headers_on_success_and_on_errors():
    async with _http(_app()) as http:
        for path in (f"{BASE}/health", f"{BASE}/nope", f"{BASE}/users/me"):
            r = await http.get(path)
            assert r.headers["x-content-type-options"] == "nosniff", path
            assert r.headers["x-frame-options"] == "DENY", path
            assert r.headers["referrer-policy"] == "no-referrer", path
            assert r.headers["cache-control"] == "no-store", path
            assert "frame-ancestors 'none'" in r.headers["content-security-policy"], path
            assert "strict-transport-security" not in r.headers, path


async def test_hsts_is_sent_only_when_configured_and_the_docs_page_keeps_working():
    async with _http(_app(hsts_max_age_seconds=31536000)) as http:
        r = await http.get(f"{BASE}/health")
        docs = await http.get(f"{BASE}/docs")
    assert r.headers["strict-transport-security"] == "max-age=31536000"
    assert docs.status_code == 200 and "content-security-policy" not in docs.headers


# ------------------------------------------------------------------ body size

def _register_body(padding: int = 0) -> dict:
    return {"email": f"{uuid.uuid4().hex[:8]}@example.com", "password": "Secret123", "name_hint": "x" * padding}


async def test_a_body_over_the_limit_is_413_in_the_error_model():
    async with _http(_app(max_body_bytes=2048)) as http:
        ok = await http.post(f"{BASE}/auth/register", json=_register_body(100))
        big = await http.post(f"{BASE}/auth/register", json=_register_body(5000))
    assert ok.status_code == 201
    assert big.status_code == 413 and big.json()["code"] == "payload_too_large" and "message" in big.json()
    assert big.headers["x-request-id"] and big.headers["x-content-type-options"] == "nosniff"


async def test_a_chunked_body_without_content_length_is_counted_while_it_streams():
    async def chunks():
        for _ in range(10):
            yield b"x" * 1024

    async with _http(_app(max_body_bytes=4096)) as http:
        r = await http.post(f"{BASE}/auth/register", content=chunks(), headers={"content-type": "application/json"})
    assert r.status_code == 413 and r.json()["code"] == "payload_too_large"


async def test_the_photo_upload_has_a_larger_limit_than_other_routes():
    async with _http(_app(max_body_bytes=2048, max_upload_bytes=20_000)) as http:
        photo = await http.post(f"{BASE}/meals/recognitions", content=b"x" * 10_000)
        huge = await http.post(f"{BASE}/meals/recognitions", content=b"x" * 30_000)
        other = await http.post(f"{BASE}/auth/login", content=b"x" * 10_000)
    assert photo.status_code != 413          # not implemented yet (404/405), but past the size check
    assert huge.status_code == 413 and other.status_code == 413


# ------------------------------------------------------------------ CORS

async def test_cors_is_off_by_default_and_allows_only_the_listed_origins():
    preflight = {"Origin": "https://app.example.com", "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "authorization"}
    async with _http(_app()) as http:
        plain = await http.options(f"{BASE}/auth/login", headers=preflight)
        assert "access-control-allow-origin" not in plain.headers
    async with _http(_app(cors_origins="https://app.example.com, https://admin.example.com")) as http:
        allowed = await http.options(f"{BASE}/auth/login", headers=preflight)
        denied = await http.options(f"{BASE}/auth/login", headers={**preflight, "Origin": "https://evil.example"})
        simple = await http.get(f"{BASE}/health", headers={"Origin": "https://admin.example.com"})
    assert allowed.status_code == 200 and allowed.headers["access-control-allow-origin"] == "https://app.example.com"
    assert "access-control-allow-origin" not in denied.headers
    assert simple.headers["access-control-allow-origin"] == "https://admin.example.com"
    assert "x-request-id" in allowed.headers
    assert "x-request-id" in simple.headers["access-control-expose-headers"].lower()


# ------------------------------------------------------------------ database pool

def test_pool_settings_reach_the_engine():
    settings = Settings(jwt_secret=SECRET, _env_file=None, **{**NO_STORES, "database_url": "postgresql://u:p@localhost/db"},
                        db_pool_size=7, db_max_overflow=3, db_pool_timeout_seconds=2.5, db_pool_recycle_seconds=600)
    app = create_app(settings)  # the engine connects lazily: nothing is contacted here
    pool = app.state.db_engine.pool
    assert (pool.size(), pool._max_overflow, pool._timeout, pool._recycle) == (7, 3, 2.5, 600)  # noqa: SLF001


async def test_an_exhausted_pool_is_a_503_with_retry_after_not_a_500():
    app = _app()
    router = APIRouter()

    @router.get("/busy")
    async def busy():
        raise PoolTimeoutError("QueuePool limit of size 1 overflow 0 reached, connection timed out")

    app.include_router(router)
    async with _http(app) as http:
        r = await http.get("/busy")
    assert r.status_code == 503 and r.headers["retry-after"] == "1"
    assert r.json()["code"] == "internal_error" and "QueuePool" not in r.text


# ------------------------------------------------------------------ bcrypt off the event loop

async def test_password_hashing_does_not_block_the_event_loop():
    """12 rounds cost ~250 ms of CPU each. Run on the loop thread, eight concurrent registrations would freeze it for
    seconds; in worker threads the loop keeps ticking (a ticker measures the longest pause)."""
    app = _app(bcrypt_rounds=12)
    longest = 0.0
    stop = False

    async def ticker():
        nonlocal longest
        last = time.perf_counter()
        while not stop:
            await asyncio.sleep(0.005)
            now = time.perf_counter()
            longest = max(longest, now - last)
            last = now

    async with _http(app) as http:
        task = asyncio.create_task(ticker())
        replies = await asyncio.gather(*(http.post(f"{BASE}/auth/register", json=_register_body()) for _ in range(8)))
        stop = True
        await task
    assert all(r.status_code == 201 for r in replies)
    assert longest < 0.15, f"the event loop stalled for {longest:.3f}s"
