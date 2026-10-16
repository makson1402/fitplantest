"""SQLAlchemy unit of work against a real PostgreSQL: repository contract plus the auth API end to end."""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core.config import Settings
from app.db.session import create_engine_from_url
from app.main import create_app
from app.repositories import EmailAlreadyExists
from app.repositories.sql import sql_uow_factory

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


def _email() -> str:
    return f"{uuid.uuid4().hex[:10]}@example.com"


@pytest_asyncio.fixture
async def engine(pg_engine):
    eng = create_engine_from_url(pg_engine.url.render_as_string(hide_password=False))
    yield eng
    await eng.dispose()


@pytest.fixture
def uow_factory(engine):
    return sql_uow_factory(engine)


async def test_user_add_get_and_server_defaults(uow_factory):
    email = _email()
    async with uow_factory() as uow:
        user = await uow.users.add(email=email, password_hash="h", timezone="Europe/Warsaw")
        await uow.commit()
    assert user.id > 0 and user.is_active and user.created_at.tzinfo is not None
    async with uow_factory() as uow:
        assert (await uow.users.get_by_id(user.id)).email == email
        assert (await uow.users.get_by_email(email)).timezone == "Europe/Warsaw"
        assert await uow.users.get_by_email("nobody@example.com") is None
        assert await uow.users.get_by_id(10**9) is None


async def test_duplicate_email_raises_and_session_recovers_after_rollback(uow_factory):
    email = _email()
    async with uow_factory() as uow:
        await uow.users.add(email=email, password_hash=None, timezone="UTC")
        await uow.commit()
    async with uow_factory() as uow:
        with pytest.raises(EmailAlreadyExists):
            await uow.users.add(email=email, password_hash=None, timezone="UTC")
        await uow.rollback()
        assert await uow.users.get_by_email(email) is not None  # the session is usable again


async def test_uncommitted_changes_are_discarded(uow_factory):
    email = _email()
    async with uow_factory() as uow:
        await uow.users.add(email=email, password_hash="h", timezone="UTC")
        # no commit
    async with uow_factory() as uow:
        assert await uow.users.get_by_email(email) is None


async def test_refresh_token_lifecycle(uow_factory):
    family = uuid.uuid4()
    async with uow_factory() as uow:
        user = await uow.users.add(email=_email(), password_hash="h", timezone="UTC")
        first = await uow.refresh_tokens.add(
            user_id=user.id, family_id=family, token_hash=uuid.uuid4().hex, expires_at=NOW + timedelta(days=30),
            device_label="pixel",
        )
        second = await uow.refresh_tokens.add(
            user_id=user.id, family_id=family, token_hash=uuid.uuid4().hex, expires_at=NOW + timedelta(days=30),
            device_label=None,
        )
        await uow.commit()
    assert first.revoked_at is None and first.device_label == "pixel"

    async with uow_factory() as uow:
        found = await uow.refresh_tokens.get_by_hash_for_update(first.token_hash)
        assert found.id == first.id and found.family_id == family
        assert await uow.refresh_tokens.get_by_hash_for_update("missing") is None
        await uow.refresh_tokens.revoke(first.id, NOW)
        await uow.commit()
    async with uow_factory() as uow:
        assert (await uow.refresh_tokens.get_by_hash_for_update(first.token_hash)).revoked_at == NOW
        assert (await uow.refresh_tokens.get_by_hash_for_update(second.token_hash)).revoked_at is None
        await uow.refresh_tokens.revoke_family(family, NOW + timedelta(hours=1))
        await uow.commit()
    async with uow_factory() as uow:
        # revoking never overwrites an earlier revocation time
        assert (await uow.refresh_tokens.get_by_hash_for_update(first.token_hash)).revoked_at == NOW
        assert (await uow.refresh_tokens.get_by_hash_for_update(second.token_hash)).revoked_at == NOW + timedelta(
            hours=1
        )


async def test_deleting_user_removes_tokens(uow_factory, engine):
    async with uow_factory() as uow:
        user = await uow.users.add(email=_email(), password_hash="h", timezone="UTC")
        await uow.refresh_tokens.add(
            user_id=user.id, family_id=uuid.uuid4(), token_hash=uuid.uuid4().hex, expires_at=NOW, device_label=None
        )
        await uow.commit()
    async with engine.begin() as connection:
        await connection.execute(text("delete from users where id = :id"), {"id": user.id})
        left = await connection.scalar(text("select count(*) from refresh_token where user_id = :id"), {"id": user.id})
    assert left == 0


# ------------------------------------------------------------------ the real app on PostgreSQL

@pytest_asyncio.fixture
async def client(pg_engine):
    url = pg_engine.url.render_as_string(hide_password=False)
    settings = Settings(
        jwt_secret="test-secret-" + "x" * 32, bcrypt_rounds=4, auth_rate_limit=1000, database_url=url, _env_file=None
    )
    app = create_app(settings)  # no injected unit of work: the app builds its own PostgreSQL one
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    await app.state.db_engine.dispose()  # ASGITransport does not run the lifespan shutdown


async def test_health_reports_postgres_up(client):
    body = (await client.get("/api/v1/health")).json()
    assert body == {"status": "ok", "postgres": "up"}


async def test_auth_flow_on_postgres(client):
    creds = {"email": _email(), "password": "Secret123"}
    registered = await client.post("/api/v1/auth/register", json=creds)
    assert registered.status_code == 201, registered.text
    assert (await client.post("/api/v1/auth/register", json=creds)).status_code == 409

    login = await client.post("/api/v1/auth/login", json=creds)
    assert login.status_code == 200
    assert (await client.post("/api/v1/auth/login", json={**creds, "password": "wrong-pass1"})).status_code == 401

    old = login.json()["refresh_token"]
    rotated = await client.post("/api/v1/auth/refresh", json={"refresh_token": old})
    assert rotated.status_code == 200
    new = rotated.json()["refresh_token"]
    assert new != old

    # Reusing a rotated token is theft: it fails and the whole family, including the new token, is revoked.
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": old})).status_code == 401
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": new})).status_code == 401


async def test_logout_revokes_refresh_token(client):
    creds = {"email": _email(), "password": "Secret123"}
    pair = (await client.post("/api/v1/auth/register", json=creds)).json()
    headers = {"Authorization": f"Bearer {pair['access_token']}"}
    out = await client.post("/api/v1/auth/logout", json={"refresh_token": pair["refresh_token"]}, headers=headers)
    assert out.status_code == 204
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})).status_code == 401


async def test_concurrent_registration_of_same_email_yields_one_account(client):
    creds = {"email": _email(), "password": "Secret123"}
    results = await asyncio.gather(*[client.post("/api/v1/auth/register", json=creds) for _ in range(4)])
    codes = sorted(r.status_code for r in results)
    assert codes == [201, 409, 409, 409], codes
