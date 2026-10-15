from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.errors import AppError
from app.core.logging import redact
from app.core.rate_limit import RateLimiter
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)

SECRET = "s" * 40
NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


def test_bcrypt_roundtrip_and_wrong_password():
    h = hash_password("abc12345", rounds=4)
    assert h.startswith("$2b$04$")
    assert verify_password("abc12345", h)
    assert not verify_password("abc12346", h)


def test_passwords_over_72_bytes_are_rejected():
    long_pw = "ż" * 37  # 37 characters, 74 bytes
    with pytest.raises(ValueError):
        hash_password(long_pw, rounds=4)
    assert not verify_password(long_pw, hash_password("abc12345", rounds=4))


def test_unknown_user_never_verifies():
    assert not verify_password("anything1", None)


def test_access_token_roundtrip():
    token = create_access_token(42, NOW, 900, SECRET, "HS256")
    assert decode_access_token(token, NOW + timedelta(seconds=899), SECRET, "HS256").user_id == 42


def test_expired_access_token():
    token = create_access_token(42, NOW, 900, SECRET, "HS256")
    with pytest.raises(AppError) as e:
        decode_access_token(token, NOW + timedelta(seconds=900), SECRET, "HS256")
    assert (e.value.status, e.value.code) == (401, "token_expired")


@pytest.mark.parametrize("make", [
    lambda t: t[:-2] + ("AA" if not t.endswith("AA") else "BB"),                       # tampered signature
    lambda t: create_access_token(42, NOW, 900, "other-secret" * 4, "HS256"),          # wrong key
    lambda t: jwt.encode({"sub": "42", "typ": "access", "iat": 0, "exp": 2**40}, None, algorithm="none"),
    lambda t: jwt.encode({"sub": "42", "typ": "refresh", "iat": 0, "exp": 2**40}, SECRET, algorithm="HS256"),
    lambda t: jwt.encode({"sub": "42", "typ": "access", "iat": 0}, SECRET, algorithm="HS256"),  # no exp
    lambda t: "not-a-jwt",
])
def test_tampered_or_malformed_access_token(make):
    token = make(create_access_token(42, NOW, 900, SECRET, "HS256"))
    with pytest.raises(AppError) as e:
        decode_access_token(token, NOW, SECRET, "HS256")
    assert (e.value.status, e.value.code) == (401, "unauthorized")


def test_refresh_tokens_are_random_and_hashed():
    a, b = new_refresh_token(), new_refresh_token()
    assert a != b and len(a) >= 40
    assert hash_refresh_token(a) == hash_refresh_token(a) != a and len(hash_refresh_token(a)) == 64


def test_rate_limiter_sliding_window():
    t = [0.0]
    rl = RateLimiter(2, 60, clock=lambda: t[0])
    assert rl.hit("k") is None and rl.hit("k") is None
    assert rl.hit("k") == pytest.approx(60)
    assert rl.hit("other") is None
    t[0] = 60.0
    assert rl.hit("k") is None


def test_log_redaction():
    token = create_access_token(1, NOW, 900, SECRET, "HS256")
    out = redact(f"user jan.kowalski@pollub.edu.pl auth Bearer {token} password=Secret123 refresh_token: abc")
    assert "jan.kowalski" not in out and "j***@pollub.edu.pl" in out
    assert token not in out and "Secret123" not in out and "abc" not in out
