"""Importing this package registers every table on `Base.metadata` (needed by Alembic)."""
from app.db.models import account, nutrition, profile, reference, reports, training
from app.db.models.base import Base

__all__ = ["Base", "account", "nutrition", "profile", "reference", "reports", "training"]
