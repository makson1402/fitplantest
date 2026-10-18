"""Fixtures for the contract tests that need a running server (schemathesis, B-28)."""
from __future__ import annotations

import socket
import threading
import time
import uuid

import httpx
import pytest
import uvicorn

from app.core.config import Settings
from app.main import create_app
from tests.db.conftest import pg_engine, seeded_engine  # noqa: F401  (re-exported fixtures)
from tests.support import NO_STORES

PASSWORD = "Secret123"
PROFILE = {"age": 30, "sex": "male", "weight_kg": 80, "height_cm": 180, "activity_level_pal": 1.55,
           "goal": "muscle_gain", "experience_level": "intermediate", "equipment": "gym", "target_weight_kg": 75}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def live_api(seeded_engine):  # noqa: F811
    """The real application on a real port, backed by the seeded test database (own event loop, like production)."""
    url = seeded_engine.url.render_as_string(hide_password=False)
    settings = Settings(jwt_secret="test-secret-" + "x" * 32, bcrypt_rounds=4, auth_rate_limit=1_000_000,
                        _env_file=None, **{**NO_STORES, "database_url": url})
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}/api/v1"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        raise RuntimeError("the test server did not start")
    yield base
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(scope="session")
def auth_header(live_api) -> dict[str, str]:
    """A signed-in user with a finished profile, so that most endpoints get past the 'no profile' answers."""
    email = f"fuzz-{uuid.uuid4().hex[:8]}@example.com"
    pair = httpx.post(f"{live_api}/auth/register", json={"email": email, "password": PASSWORD}).json()
    header = {"Authorization": f"Bearer {pair['access_token']}"}
    assert httpx.put(f"{live_api}/users/me/profile", json=PROFILE, headers=header).status_code == 200
    return header
