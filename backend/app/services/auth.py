"""Registration, login, refresh-token rotation and logout (B-03, FR-U1, FR-U2).

Refresh tokens are opaque, stored as SHA-256, grouped in a family per login. Presenting a token that was
already rotated or revoked is treated as theft: the whole family is revoked (reuse detection).
"""
from __future__ import annotations

import logging
from datetime import timedelta
from uuid import UUID, uuid4

from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError, unauthorized
from app.core.security import create_access_token, hash_password, hash_refresh_token, new_refresh_token, verify_password
from app.repositories import EmailAlreadyExists, UnitOfWork, UserRecord
from app.schemas.auth import TokenPair

log = logging.getLogger(__name__)


def normalize_email(email: str) -> str:
    return email.strip().lower()


class AuthService:
    def __init__(self, uow: UnitOfWork, settings: Settings, clock: Clock):
        self.uow, self.settings, self.clock = uow, settings, clock

    async def register(self, email: str, password: str, timezone: str | None) -> TokenPair:
        email = normalize_email(email)
        if await self.uow.users.get_by_email(email) is not None:
            raise AppError(409, "email_taken", "Email is already registered")
        password_hash = hash_password(password, self.settings.bcrypt_rounds)
        try:
            user = await self.uow.users.add(email=email, password_hash=password_hash, timezone=timezone or "UTC")
        except EmailAlreadyExists:  # concurrent registration with the same email
            await self.uow.rollback()
            raise AppError(409, "email_taken", "Email is already registered") from None
        pair = await self._issue(user.id, uuid4(), device_label=None)
        await self.uow.commit()
        log.info("user registered id=%s", user.id)
        return pair

    async def login(self, email: str, password: str, device_label: str | None) -> TokenPair:
        user = await self.uow.users.get_by_email(normalize_email(email))
        # verify_password runs bcrypt even for unknown users, so both failures look and take the same.
        password_ok = verify_password(password, user.password_hash if user else None)
        if user is None or not password_ok or not user.is_active:
            raise unauthorized("invalid_credentials", "Invalid email or password")
        pair = await self._issue(user.id, uuid4(), device_label)
        await self.uow.commit()
        log.info("user logged in id=%s", user.id)
        return pair

    async def refresh(self, refresh_token: str) -> TokenPair:
        now = self.clock.now()
        record = await self.uow.refresh_tokens.get_by_hash_for_update(hash_refresh_token(refresh_token))
        if record is None:
            raise unauthorized()
        if record.revoked_at is not None:
            await self.uow.refresh_tokens.revoke_family(record.family_id, now)
            await self.uow.commit()
            log.warning("refresh token reuse detected user=%s family=%s", record.user_id, record.family_id)
            raise unauthorized()
        if record.expires_at <= now:
            raise unauthorized("token_expired", "Refresh token expired")
        user = await self.uow.users.get_by_id(record.user_id)
        if user is None or not user.is_active:
            await self.uow.refresh_tokens.revoke_family(record.family_id, now)
            await self.uow.commit()
            raise unauthorized()
        await self.uow.refresh_tokens.revoke(record.id, now)
        pair = await self._issue(user.id, record.family_id, record.device_label)
        await self.uow.commit()
        return pair

    async def logout(self, user: UserRecord, refresh_token: str) -> None:
        record = await self.uow.refresh_tokens.get_by_hash_for_update(hash_refresh_token(refresh_token))
        if record is None or record.user_id != user.id:
            raise unauthorized()
        await self.uow.refresh_tokens.revoke_family(record.family_id, self.clock.now())
        await self.uow.commit()

    async def _issue(self, user_id: int, family_id: UUID, device_label: str | None) -> TokenPair:
        now, s = self.clock.now(), self.settings
        refresh = new_refresh_token()
        await self.uow.refresh_tokens.add(user_id=user_id, family_id=family_id, token_hash=hash_refresh_token(refresh),
                                          expires_at=now + timedelta(days=s.refresh_token_ttl_days),
                                          device_label=device_label)
        access = create_access_token(user_id, now, s.access_token_ttl_seconds, s.jwt_secret, s.jwt_algorithm)
        return TokenPair(access_token=access, refresh_token=refresh, expires_in=s.access_token_ttl_seconds)
