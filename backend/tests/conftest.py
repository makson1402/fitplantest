from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.fakes import FakeClock, Store, uow_factory

SECRET = "test-secret-" + "x" * 32


@pytest.fixture
def settings() -> Settings:
    return Settings(jwt_secret=SECRET, bcrypt_rounds=4, auth_rate_limit=1000, _env_file=None)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def store() -> Store:
    return Store()


@pytest.fixture
def app(settings, clock, store):
    return create_app(settings, uow_factory=uow_factory(store, clock), clock=clock)


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)
