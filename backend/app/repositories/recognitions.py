"""Buffer of unconfirmed meal recognitions in MongoDB (task DB-02, docs/database/mongo_buffer.md).

Rules enforced here, so no caller can forget them:
- every operation filters by `userId` (object-level authorization);
- every operation ignores documents whose `expiresAt` is not in the future, because the MongoDB TTL monitor only
  runs about once a minute and an expired document may still exist;
- item indexes are 0-based and updates are single atomic operations (no read-modify-write races).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.asynchronous.database import AsyncDatabase

from app.db.mongo import COLLECTION

DEFAULT_TTL = timedelta(hours=6)
_MAX_ITEMS = 10_000  # upper bound for the $slice used when deleting an item


@dataclass
class RecognitionRecord:
    id: str
    user_id: int
    status: str
    meal_type: str
    photo_path: str
    model_name: str
    model_version: str | None
    overall_confidence: float
    items: list[dict[str, Any]]  # camelCase keys exactly as in the document (see mongo_buffer.md)
    created_at: datetime
    expires_at: datetime


def _oid(value: str) -> ObjectId | None:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


def _record(doc: dict[str, Any]) -> RecognitionRecord:
    return RecognitionRecord(
        id=str(doc["_id"]), user_id=doc["userId"], status=doc["status"], meal_type=doc["mealType"],
        photo_path=doc["photoPath"], model_name=doc["modelName"], model_version=doc.get("modelVersion"),
        overall_confidence=doc["overallConfidence"], items=doc["recognisedItems"], created_at=doc["createdAt"],
        expires_at=doc["expiresAt"],
    )


class MongoRecognitionRepository:
    def __init__(self, db: AsyncDatabase, *, ttl: timedelta = DEFAULT_TTL):
        self.collection = db[COLLECTION]
        self.ttl = ttl

    def _live(self, user_id: int, recognition_id: str, now: datetime) -> dict[str, Any] | None:
        oid = _oid(recognition_id)
        if oid is None:
            return None
        return {"_id": oid, "userId": user_id, "expiresAt": {"$gt": now}}

    async def create(self, *, user_id: int, meal_type: str, photo_path: str, model_name: str,
                     model_version: str | None, overall_confidence: float, items: list[dict[str, Any]],
                     now: datetime) -> RecognitionRecord:
        doc = {
            "userId": user_id, "status": "pending", "mealType": meal_type, "photoPath": photo_path,
            "modelName": model_name, "modelVersion": model_version, "overallConfidence": overall_confidence,
            "recognisedItems": items, "createdAt": now, "expiresAt": now + self.ttl,
        }
        result = await self.collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        return _record(doc)

    async def get(self, user_id: int, recognition_id: str, now: datetime) -> RecognitionRecord | None:
        query = self._live(user_id, recognition_id, now)
        doc = await self.collection.find_one(query) if query else None
        return _record(doc) if doc else None

    async def add_item(self, user_id: int, recognition_id: str, item: dict[str, Any], now: datetime) -> bool:
        query = self._live(user_id, recognition_id, now)
        if query is None:
            return False
        result = await self.collection.update_one(query, {"$push": {"recognisedItems": item}})
        return result.matched_count == 1

    async def replace_item(self, user_id: int, recognition_id: str, index: int, item: dict[str, Any],
                           now: datetime) -> bool:
        """False when the recognition does not exist, is not the caller's, has expired or has no such index."""
        query = self._live(user_id, recognition_id, now)
        if query is None or index < 0:
            return False
        query[f"recognisedItems.{index}"] = {"$exists": True}
        result = await self.collection.update_one(query, {"$set": {f"recognisedItems.{index}": item}})
        return result.matched_count == 1

    async def delete_item(self, user_id: int, recognition_id: str, index: int, now: datetime) -> bool:
        query = self._live(user_id, recognition_id, now)
        if query is None or index < 0:
            return False
        query[f"recognisedItems.{index}"] = {"$exists": True}
        # One atomic pipeline update: keep everything before and after the index.
        pipeline = [{"$set": {"recognisedItems": {"$concatArrays": [
            {"$slice": ["$recognisedItems", index]},
            {"$slice": ["$recognisedItems", index + 1, _MAX_ITEMS]},
        ]}}}]
        result = await self.collection.update_one(query, pipeline)
        return result.matched_count == 1

    async def delete(self, user_id: int, recognition_id: str, now: datetime) -> bool:
        """Discard (user cancels) or remove after a successful confirm. True when a document was deleted."""
        query = self._live(user_id, recognition_id, now)
        if query is None:
            return False
        result = await self.collection.delete_one(query)
        return result.deleted_count == 1

    async def delete_all_for_user(self, user_id: int) -> list[str]:
        """Account deletion (FR-U5): remove every document of the user, expired or not, and return their photo
        paths so the caller can delete the files."""
        paths = [doc["photoPath"] async for doc in self.collection.find({"userId": user_id}, {"photoPath": 1})]
        await self.collection.delete_many({"userId": user_id})
        return paths

    async def referenced_photo_paths(self, now: datetime) -> set[str]:
        """Photos that must be kept by the cleanup job: those of documents that are still live."""
        cursor = self.collection.find({"expiresAt": {"$gt": now}}, {"photoPath": 1})
        return {doc["photoPath"] async for doc in cursor}
