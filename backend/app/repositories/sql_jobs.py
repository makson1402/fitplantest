"""SQLAlchemy implementation of `JobRepository` (B-26)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.nutrition import RecognitionAI


class SqlJobRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def confirmed_photo_paths(self) -> set[str]:
        return set(await self.session.scalars(select(RecognitionAI.image_url)))
