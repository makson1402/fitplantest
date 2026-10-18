"""B-29 smoke load: 500 concurrent sessions through a deliberately small connection pool.

The point is that requests queue for a connection instead of failing: no 5xx, no pool timeout, and the pool never
opens more connections than `db_pool_size + db_max_overflow`.
"""
from __future__ import annotations

import asyncio
import uuid

import httpx

from app.core.config import Settings
from app.main import create_app
from tests.support import NO_STORES

BASE = "/api/v1"
SESSIONS = 500
POOL_SIZE, OVERFLOW = 5, 5


async def test_500_concurrent_sessions_do_not_exhaust_a_small_pool(seeded_engine):
    url = seeded_engine.url.render_as_string(hide_password=False)
    settings = Settings(jwt_secret="test-secret-" + "x" * 32, bcrypt_rounds=4, auth_rate_limit=1_000_000,
                        db_pool_size=POOL_SIZE, db_max_overflow=OVERFLOW, db_pool_timeout_seconds=60,
                        _env_file=None, **{**NO_STORES, "database_url": url})
    app = create_app(settings)
    pool = app.state.db_engine.pool
    peak = 0
    stop = False

    async def watch_pool():
        nonlocal peak
        while not stop:
            peak = max(peak, pool.checkedout())
            await asyncio.sleep(0.002)

    async def session(http: httpx.AsyncClient) -> list[int]:
        email = f"load-{uuid.uuid4().hex[:12]}@example.com"
        r = await http.post(f"{BASE}/auth/register", json={"email": email, "password": "Secret123"})
        statuses = [r.status_code]
        if r.status_code != 201:
            return statuses
        header = {"Authorization": f"Bearer {r.json()['access_token']}"}
        for path in ("/users/me", "/exercises?limit=20", "/foods?limit=20", "/health"):
            statuses.append((await http.get(BASE + path, headers=header)).status_code)
        return statuses

    limits = httpx.Limits(max_connections=None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", limits=limits,
                                 timeout=120) as http:
        watcher = asyncio.create_task(watch_pool())
        results = await asyncio.gather(*(session(http) for _ in range(SESSIONS)))
        stop = True
        await watcher
    await app.state.db_engine.dispose()

    flat = [s for statuses in results for s in statuses]
    assert len(flat) == SESSIONS * 5
    assert set(flat) == {201, 200}, {s: flat.count(s) for s in set(flat)}   # no 5xx, no 503 from the pool
    assert 0 < peak <= POOL_SIZE + OVERFLOW, peak
