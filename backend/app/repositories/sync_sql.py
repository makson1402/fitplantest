"""SQL helper shared by the three `changed_since` queries (B-27)."""
from __future__ import annotations

from sqlalchemy import ColumnElement, true, tuple_

from app.repositories.sync import SyncPosition


def after(updated_at, id_, position: SyncPosition | None, rank: int) -> ColumnElement[bool]:
    """Rows of the kind with `rank` that come after `position` in the order (updated_at, rank, id)."""
    if position is None:
        return true()
    if rank == position.rank:
        return tuple_(updated_at, id_) > (position.updated_at, position.id)
    if rank > position.rank:
        return updated_at >= position.updated_at
    return updated_at > position.updated_at
