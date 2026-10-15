"""Security primitives (B-02): bcrypt password hashing, JWT access tokens, opaque refresh tokens."""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

import bcrypt
import jwt

from app.core.errors import unauthorized

BCRYPT_MAX_BYTES = 72


def password_too_long(password: str) -> bool:
    return len(password.encode("utf-8")) > BCRYPT_MAX_BYTES


def hash_password(password: str, rounds: int) -> str:
    if password_too_long(password):
        raise ValueError("password longer than 72 bytes")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds)).decode("ascii")


# Verified against when the account does not exist, so that unknown emails cost the same time.
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password-for-timing", bcrypt.gensalt(12))


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_too_long(password):
        return False
    candidate = password_hash.encode("ascii") if password_hash else _DUMMY_HASH
    ok = bcrypt.checkpw(password.encode("utf-8"), candidate)
    return ok and password_hash is not None


@dataclass(frozen=True)
class AccessClaims:
    user_id: int
    expires_at: datetime


def create_access_token(user_id: int, now: datetime, ttl_seconds: int, secret: str, algorithm: str) -> str:
    claims = {"sub": str(user_id), "typ": "access", "iat": int(now.timestamp()),
              "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()), "jti": secrets.token_hex(8)}
    return jwt.encode(claims, secret, algorithm=algorithm)


def decode_access_token(token: str, now: datetime, secret: str, algorithm: str) -> AccessClaims:
    """Raise a 401 AppError for a tampered, malformed or expired token. Expiry uses the injected clock."""
    try:
        claims = jwt.decode(token, secret, algorithms=[algorithm],
                            options={"require": ["sub", "exp", "iat", "typ"], "verify_exp": False})
        if claims["typ"] != "access":
            raise jwt.InvalidTokenError("wrong token type")
        user_id, exp = int(claims["sub"]), int(claims["exp"])
    except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
        raise unauthorized() from exc
    if exp <= now.timestamp():
        raise unauthorized("token_expired", "Access token expired")
    return AccessClaims(user_id, datetime.fromtimestamp(exp, now.tzinfo))


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """Only the SHA-256 of a refresh token is stored (schema: refresh_token.token_hash)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
