"""Account and auth tables (FR-U1..U5, FR-U8)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, bigint_pk, created_at_col, oauth_provider_t


class User(Base):
    __tablename__ = "users"
    __table_args__ = (Index("users_email_key", "email", unique=True),)

    id: Mapped[bigint_pk]
    email: Mapped[str]
    password_hash: Mapped[str | None]
    name: Mapped[str | None]
    surname: Mapped[str | None]
    timezone: Mapped[str] = mapped_column(server_default="UTC")
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    email_verified_at: Mapped[datetime | None]
    created_at: Mapped[created_at_col]
    updated_at: Mapped[created_at_col]


class OAuthIdentity(Base):
    __tablename__ = "oauth_identity"
    __table_args__ = (UniqueConstraint("provider", "provider_subject"), Index("oauth_identity_user_idx", "user_id"))

    id: Mapped[bigint_pk]
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(oauth_provider_t)
    provider_subject: Mapped[str]
    email: Mapped[str | None]
    created_at: Mapped[created_at_col]


class RefreshToken(Base):
    __tablename__ = "refresh_token"
    __table_args__ = (Index("refresh_token_user_idx", "user_id"), Index("refresh_token_family_idx", "family_id"))

    id: Mapped[bigint_pk]
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    family_id: Mapped[uuid.UUID]
    token_hash: Mapped[str] = mapped_column(unique=True)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    device_label: Mapped[str | None]
    created_at: Mapped[created_at_col]


class PasswordResetToken(Base):
    __tablename__ = "password_reset_token"
    __table_args__ = (Index("password_reset_token_user_idx", "user_id"),)

    id: Mapped[bigint_pk]
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(unique=True)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
    created_at: Mapped[created_at_col]

