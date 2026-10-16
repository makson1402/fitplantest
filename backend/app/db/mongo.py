"""MongoDB connection for the meal-recognition buffer (docs/database/mongo_buffer.md, decision D3)."""
from __future__ import annotations

from pymongo import ASCENDING, AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

COLLECTION = "meal_recognitions"


def create_mongo_client(url: str) -> AsyncMongoClient:
    return AsyncMongoClient(url, tz_aware=True, serverSelectionTimeoutMS=3000)


async def ensure_indexes(db: AsyncDatabase) -> None:
    """Idempotent. The TTL index removes documents after `expiresAt`; the (userId, status) index serves the
    per-owner queries. Call once at startup."""
    collection = db[COLLECTION]
    await collection.create_index([("expiresAt", ASCENDING)], expireAfterSeconds=0, name="expiresAt_ttl")
    await collection.create_index([("userId", ASCENDING), ("status", ASCENDING)], name="userId_status")


async def mongo_probe(client: AsyncMongoClient) -> bool:
    try:
        await client.admin.command("ping")
    except Exception:  # noqa: BLE001  (any failure means "down")
        return False
    return True
