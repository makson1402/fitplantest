"""Position in the sync stream (B-27): the keyset (updated_at, kind rank, id) that orders every changed record of
a user. `rank` orders the three kinds when their `updated_at` is equal (workout 0, nutrition log 1, body metrics 2)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

WORKOUT, NUTRITION_LOG, BODY_METRICS = 0, 1, 2


@dataclass(frozen=True)
class SyncPosition:
    updated_at: datetime
    rank: int
    id: int
