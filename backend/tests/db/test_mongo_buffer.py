"""DB-02: MongoDB buffer for unconfirmed recognitions, against a real MongoDB (`docker compose up -d mongo`).

Each test uses its own throwaway database. Skipped when MongoDB is not reachable.
The TTL monitor (runs about once a minute) is deliberately not awaited: the point of the repository is that it
never returns an expired document before the monitor has removed it.
"""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from app.core.config import Settings
from app.db.mongo import COLLECTION, create_mongo_client, ensure_indexes
from app.main import create_app
from app.repositories.recognitions import DEFAULT_TTL, MongoRecognitionRepository

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[3]


def _mongo_url() -> str:
    env = dict(os.environ)
    dotenv = ROOT / ".env"
    if dotenv.exists():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env.setdefault(key.strip(), value.strip())
    return Settings(  # reuse the production URL building
        jwt_secret="x" * 32, mongo_initdb_root_username=env.get("MONGO_INITDB_ROOT_USERNAME"),
        mongo_initdb_root_password=env.get("MONGO_INITDB_ROOT_PASSWORD"), mongo_port=int(env.get("MONGO_PORT", "27017")),
        mongo_url=env.get("MONGO_URL"), _env_file=None,
    ).resolved_mongo_url or "mongodb://localhost:27017"


def _item(name: str = "pizza", grams: int = 250) -> dict:
    return {"name": name, "foodItemId": 1, "label": name, "labelCandidates": [], "grams": grams,
            "defaultPortionUsed": True, "confidence": 0.9, "lowConfidence": False, "allergyWarning": False,
            "allergens": [], "nutrition": {"kcal": 1, "protein": 1, "fat": 1, "carbs": 1}, "corrected": False}


@pytest_asyncio.fixture
async def db():
    client = create_mongo_client(_mongo_url())
    try:
        await client.admin.command("ping")
    except Exception as exc:  # noqa: BLE001
        await client.close()
        pytest.skip(f"MongoDB is not reachable: {exc.__class__.__name__}")
    database = client[f"fitplan_test_{uuid.uuid4().hex[:8]}"]
    await ensure_indexes(database)
    yield database
    await client.drop_database(database.name)
    await client.close()


@pytest.fixture
def repo(db) -> MongoRecognitionRepository:
    return MongoRecognitionRepository(db)


async def _create(repo, user_id=1, items=None, now=NOW):
    return await repo.create(user_id=user_id, meal_type="lunch", photo_path=f"meals/{user_id}/{uuid.uuid4()}.jpg",
                             model_name="food-model", model_version="1", overall_confidence=0.9,
                             items=items if items is not None else [_item("a"), _item("b"), _item("c")], now=now)


# ------------------------------------------------------------------ indexes

async def test_indexes_are_created_and_idempotent(db):
    await ensure_indexes(db)  # second call
    info = await db[COLLECTION].index_information()
    ttl = next(v for v in info.values() if v["key"] == [("expiresAt", 1)])
    assert ttl["expireAfterSeconds"] == 0
    assert any(v["key"] == [("userId", 1), ("status", 1)] for v in info.values())


# ------------------------------------------------------------------ create / get

async def test_create_sets_pending_status_and_six_hour_expiry(repo):
    rec = await _create(repo)
    assert rec.status == "pending" and rec.created_at == NOW
    assert rec.expires_at - rec.created_at == DEFAULT_TTL == timedelta(hours=6)
    got = await repo.get(1, rec.id, NOW)
    assert got is not None and got.id == rec.id and len(got.items) == 3 and got.photo_path == rec.photo_path


async def test_expired_but_not_yet_deleted_document_is_never_returned(repo, db):
    """The 'done when' of DB-02: the TTL monitor lags, so reads must filter on expiresAt themselves."""
    rec = await _create(repo)
    later = NOW + timedelta(hours=6, seconds=1)
    assert await db[COLLECTION].count_documents({}) == 1  # still physically there
    assert await repo.get(1, rec.id, later) is None
    assert await repo.add_item(1, rec.id, _item("x"), later) is False
    assert await repo.replace_item(1, rec.id, 0, _item("x"), later) is False
    assert await repo.delete_item(1, rec.id, 0, later) is False
    assert await repo.delete(1, rec.id, later) is False
    assert await repo.referenced_photo_paths(later) == set()
    assert await db[COLLECTION].count_documents({}) == 1  # none of the calls touched it
    assert await repo.get(1, rec.id, NOW + timedelta(hours=5, minutes=59)) is not None  # still live before expiry


async def test_expiry_boundary_is_exclusive(repo):
    rec = await _create(repo)
    assert await repo.get(1, rec.id, rec.expires_at) is None  # expiresAt == now counts as expired


async def test_invalid_id_returns_none_instead_of_raising(repo):
    assert await repo.get(1, "not-an-object-id", NOW) is None
    assert await repo.delete(1, "", NOW) is False
    assert await repo.add_item(1, "zzz", _item(), NOW) is False


# ------------------------------------------------------------------ object-level authorization

async def test_other_users_cannot_read_modify_or_delete(repo):
    rec = await _create(repo, user_id=1)
    assert await repo.get(2, rec.id, NOW) is None
    assert await repo.add_item(2, rec.id, _item("x"), NOW) is False
    assert await repo.replace_item(2, rec.id, 0, _item("x"), NOW) is False
    assert await repo.delete_item(2, rec.id, 0, NOW) is False
    assert await repo.delete(2, rec.id, NOW) is False
    untouched = await repo.get(1, rec.id, NOW)
    assert [i["name"] for i in untouched.items] == ["a", "b", "c"]


# ------------------------------------------------------------------ items

async def test_add_replace_and_delete_items(repo):
    rec = await _create(repo)
    assert await repo.add_item(1, rec.id, _item("d"), NOW)
    assert await repo.replace_item(1, rec.id, 1, {**_item("B2"), "corrected": True}, NOW)
    got = await repo.get(1, rec.id, NOW)
    assert [i["name"] for i in got.items] == ["a", "B2", "c", "d"] and got.items[1]["corrected"] is True

    assert await repo.delete_item(1, rec.id, 0, NOW)  # first
    assert [i["name"] for i in (await repo.get(1, rec.id, NOW)).items] == ["B2", "c", "d"]
    assert await repo.delete_item(1, rec.id, 2, NOW)  # last
    assert [i["name"] for i in (await repo.get(1, rec.id, NOW)).items] == ["B2", "c"]
    assert await repo.delete_item(1, rec.id, 0, NOW) and await repo.delete_item(1, rec.id, 0, NOW)
    assert (await repo.get(1, rec.id, NOW)).items == []  # the document itself survives with no items


async def test_item_index_out_of_range_changes_nothing(repo):
    rec = await _create(repo)
    assert await repo.replace_item(1, rec.id, 3, _item("x"), NOW) is False
    assert await repo.delete_item(1, rec.id, 3, NOW) is False
    assert await repo.replace_item(1, rec.id, -1, _item("x"), NOW) is False
    assert await repo.delete_item(1, rec.id, -1, NOW) is False
    assert [i["name"] for i in (await repo.get(1, rec.id, NOW)).items] == ["a", "b", "c"]


# ------------------------------------------------------------------ delete / cleanup

async def test_delete_removes_only_that_document(repo):
    one, two = await _create(repo), await _create(repo)
    assert await repo.delete(1, one.id, NOW) is True
    assert await repo.delete(1, one.id, NOW) is False  # already gone
    assert await repo.get(1, two.id, NOW) is not None


async def test_delete_all_for_user_returns_photo_paths_including_expired(repo):
    live, expired = await _create(repo, user_id=7), await _create(repo, user_id=7, now=NOW - timedelta(days=1))
    other = await _create(repo, user_id=8)
    paths = await repo.delete_all_for_user(7)
    assert sorted(paths) == sorted([live.photo_path, expired.photo_path])
    assert await repo.get(7, live.id, NOW) is None
    assert await repo.get(8, other.id, NOW) is not None  # other users untouched
    assert await repo.delete_all_for_user(7) == []


async def test_referenced_photo_paths_lists_live_documents_only(repo):
    live = await _create(repo)
    await _create(repo, now=NOW - timedelta(days=1))  # expired
    assert await repo.referenced_photo_paths(NOW) == {live.photo_path}


# ------------------------------------------------------------------ the app

async def test_app_reports_mongo_health_and_builds_indexes(db):
    url = _mongo_url()
    settings = Settings(jwt_secret="test-secret-" + "x" * 32, mongo_url=url, mongo_db=db.name, _env_file=None)
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/api/v1/health")).json() == {"status": "ok", "mongo": "up"}
    await app.state.mongo_client.close()


async def test_health_reports_mongo_down_when_unreachable():
    settings = Settings(jwt_secret="test-secret-" + "x" * 32, mongo_url="mongodb://127.0.0.1:1", _env_file=None)
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/api/v1/health")).json() == {"status": "degraded", "mongo": "down"}
    await app.state.mongo_client.close()
