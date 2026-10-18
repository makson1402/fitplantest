"""Queries only the scheduled jobs need (B-26)."""
from __future__ import annotations

from typing import Protocol


class JobRepository(Protocol):
    async def confirmed_photo_paths(self) -> set[str]:
        """`recognition_ai.image_url` of every user: confirmed photos are kept until the account is deleted."""
        ...
