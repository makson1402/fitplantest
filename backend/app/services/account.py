"""Account settings and deletion (B-05; FR-U4, FR-U5)."""
from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from pymongo.asynchronous.database import AsyncDatabase

from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError, unauthorized
from app.core.security import hash_password_async, verify_password_async
from app.repositories import EmailAlreadyExists, UnitOfWork, UserRecord
from app.repositories.recognitions import MongoRecognitionRepository
from app.schemas import account as s
from app.services.auth import normalize_email

log = logging.getLogger(__name__)


def remove_photos(photo_dir: str | None, user_id: int, paths: list[str]) -> None:
    """Delete the user's meal photos: the whole `meals/<user id>/` folder and any listed file below the photo root.
    Nothing outside the photo directory is ever touched."""
    if not photo_dir:
        return
    root = Path(photo_dir).resolve()
    folder = (root / "meals" / str(user_id)).resolve()
    if folder.is_relative_to(root):
        shutil.rmtree(folder, ignore_errors=True)
    for relative in paths:
        target = (root / relative).resolve()
        if target.is_relative_to(root) and target.is_file():
            target.unlink(missing_ok=True)


class AccountService:
    def __init__(self, uow: UnitOfWork, settings: Settings, clock: Clock, mongo_db: AsyncDatabase | None = None):
        self.uow, self.settings, self.clock, self.mongo_db = uow, settings, clock, mongo_db

    async def _user(self, record: UserRecord) -> s.User:
        has_profile = await self.uow.profile.get_profile(record.id) is not None
        return s.User(id=record.id, email=record.email, name=record.name, surname=record.surname,
                      timezone=record.timezone, has_profile=has_profile, created_at=record.created_at)

    @staticmethod
    async def _check_password(user: UserRecord, password: str) -> None:
        """Wrong current password: 401 `invalid_credentials`. Accounts without a password (social sign-in) cannot use
        the password-protected operations (docs/questions.md, B-05)."""
        if user.password_hash is None:
            raise AppError(422, "validation_error", "Invalid input", [
                {"field": "current_password", "code": "no_password",
                 "message": "This account has no password (social sign-in)"}])
        if not await verify_password_async(password, user.password_hash):
            raise unauthorized("invalid_credentials", "The current password is incorrect")

    async def me(self, user: UserRecord) -> s.User:
        return await self._user(user)

    async def update_me(self, user: UserRecord, body: s.UserUpdate) -> s.User:
        values = {}
        for key in body.model_fields_set:
            value = getattr(body, key)
            values[key] = (value.strip() or None) if isinstance(value, str) and key != "timezone" else value
        record = await self.uow.users.update_fields(user.id, values) if values else user
        await self.uow.commit()
        return await self._user(record)

    async def change_email(self, user: UserRecord, body: s.ChangeEmailRequest) -> s.User:
        await self._check_password(user, body.current_password)
        email = normalize_email(body.new_email)
        if email == user.email:  # nothing to change
            return await self._user(user)
        if await self.uow.users.get_by_email(email) is not None:
            raise AppError(409, "email_taken", "Email is already registered")
        try:
            record = await self.uow.users.set_email(user.id, email)
        except EmailAlreadyExists:  # concurrent change to the same address
            await self.uow.rollback()
            raise AppError(409, "email_taken", "Email is already registered") from None
        await self.uow.commit()
        log.info("email changed user=%s", user.id)
        return await self._user(record)

    async def change_password(self, user: UserRecord, body: s.ChangePasswordRequest) -> None:
        """Sets the new password and signs the user out everywhere: every refresh token is revoked (the access token
        of this device works until it expires, at most 15 minutes)."""
        await self._check_password(user, body.current_password)
        new_hash = await hash_password_async(body.new_password, self.settings.bcrypt_rounds)
        await self.uow.users.set_password_hash(user.id, new_hash)
        await self.uow.refresh_tokens.revoke_all_for_user(user.id, self.clock.now())
        await self.uow.commit()
        log.info("password changed user=%s", user.id)

    async def delete(self, user: UserRecord, body: s.DeleteAccountRequest) -> None:
        """Erase the account with all related data (FR-U5). PostgreSQL first: the user row cascades to every table
        that references it. MongoDB documents and photo files follow; if that step fails the data is only an expired
        buffer and unreferenced files, which the cleanup job removes."""
        if user.password_hash is not None:
            if not body.current_password:
                raise AppError(422, "validation_error", "Invalid input", [
                    {"field": "current_password", "code": "required", "message": "Required for this account"}])
            await self._check_password(user, body.current_password)
        await self.uow.training.lock_user(user.id)
        await self.uow.users.delete(user.id)
        await self.uow.commit()
        paths: list[str] = []
        if self.mongo_db is not None:
            try:
                paths = await MongoRecognitionRepository(self.mongo_db).delete_all_for_user(user.id)
            except Exception:  # noqa: BLE001
                log.exception("could not delete the recognition buffer of deleted user %s", user.id)
        await asyncio.to_thread(remove_photos, self.settings.photo_dir, user.id, paths)
        log.info("account deleted user=%s", user.id)
