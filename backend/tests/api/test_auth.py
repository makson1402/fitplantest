import logging

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.fakes import uow_factory

EMAIL, PASSWORD = "Jan.Kowalski@Example.com", "Secret123"


def register(client, email=EMAIL, password=PASSWORD, **extra):
    return client.post("/api/v1/auth/register", json={"email": email, "password": password, **extra})


def login(client, email=EMAIL, password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def refresh(client, token):
    return client.post("/api/v1/auth/refresh", json={"refresh_token": token})


def bearer(pair):
    return {"Authorization": f"Bearer {pair['access_token']}"}


# ------------------------------------------------------------------ register

def test_register_returns_token_pair_and_stores_hash_only(client, store):
    r = register(client, timezone="Europe/Warsaw")
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"access_token", "refresh_token", "token_type", "expires_in"}
    assert body["token_type"] == "bearer" and body["expires_in"] == 900
    user = next(iter(store.users.values()))
    assert user.email == "jan.kowalski@example.com" and user.timezone == "Europe/Warsaw"
    assert user.password_hash.startswith("$2b$") and PASSWORD not in user.password_hash
    token = next(iter(store.tokens.values()))
    assert token.token_hash != body["refresh_token"]


def test_register_default_timezone_is_utc(client, store):
    register(client)
    assert next(iter(store.users.values())).timezone == "UTC"


def test_duplicate_email_gives_contract_error(client):
    register(client)
    r = register(client, email="JAN.kowalski@example.com")
    assert r.status_code == 409
    assert r.json() == {"code": "email_taken", "message": "Email is already registered"}


@pytest.mark.parametrize("payload, field, code", [
    ({"email": "not-an-email", "password": PASSWORD}, "email", None),
    ({"email": EMAIL, "password": "short1"}, "password", "too_short"),
    ({"email": EMAIL, "password": "lettersonly"}, "password", "invalid"),
    ({"email": EMAIL, "password": "12345678"}, "password", "invalid"),
    ({"email": EMAIL, "password": "a1" + "ż" * 36}, "password", "invalid"),  # 38 chars, 74 bytes
    ({"email": EMAIL, "password": "a1" * 37}, "password", "too_long"),
    ({"email": EMAIL, "password": PASSWORD, "timezone": "Mars/Base"}, "timezone", "invalid"),
    ({"password": PASSWORD}, "email", "required"),
])
def test_register_validation_is_422_with_field_details(client, payload, field, code):
    r = client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "validation_error"
    assert [d["field"] for d in body["details"]] == [field]
    if code:
        assert body["details"][0]["code"] == code
    assert "input" not in body["details"][0] and payload.get("password", "§") not in r.text


# ------------------------------------------------------------------ login

def test_login_success_is_case_insensitive_on_email(client):
    register(client)
    r = login(client, email="jan.KOWALSKI@example.com")
    assert r.status_code == 200 and r.json()["token_type"] == "bearer"


def test_wrong_password_and_unknown_email_look_the_same(client):
    register(client)
    wrong, unknown = login(client, password="Wrong1234"), login(client, email="nobody@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"code": "invalid_credentials", "message": "Invalid email or password"}
    assert wrong.headers.get("www-authenticate") == unknown.headers.get("www-authenticate") == "Bearer"


def test_login_with_too_long_password_is_plain_invalid_credentials(client):
    register(client)
    assert login(client, password="ż" * 40).json()["code"] == "invalid_credentials"


def test_inactive_user_cannot_log_in(client, store):
    register(client)
    next(iter(store.users.values())).is_active = False
    assert login(client).json()["code"] == "invalid_credentials"


def test_password_is_never_logged_or_returned(client, caplog):
    with caplog.at_level(logging.DEBUG):
        responses = [register(client), login(client), login(client, password="Wrong1234")]
    assert "user registered" in caplog.text and "user logged in" in caplog.text
    text = caplog.text + "".join(r.text for r in responses)
    assert PASSWORD not in text and "Wrong1234" not in text
    assert "jan.kowalski@example.com" not in caplog.text.lower()


# ------------------------------------------------------------------ access token / current user

def test_logout_requires_valid_access_token(client, clock):
    pair = register(client).json()
    no_auth = client.post("/api/v1/auth/logout", json={"refresh_token": pair["refresh_token"]})
    assert no_auth.status_code == 401 and no_auth.json()["code"] == "unauthorized"
    tampered = {"Authorization": "Bearer " + pair["access_token"][:-3] + "abc"}
    r = client.post("/api/v1/auth/logout", json={"refresh_token": pair["refresh_token"]}, headers=tampered)
    assert r.status_code == 401 and r.json()["code"] == "unauthorized"
    clock.advance(minutes=15)
    r = client.post("/api/v1/auth/logout", json={"refresh_token": pair["refresh_token"]}, headers=bearer(pair))
    assert r.status_code == 401 and r.json()["code"] == "token_expired"


def test_access_token_of_deactivated_user_is_rejected(client, store):
    pair = register(client).json()
    next(iter(store.users.values())).is_active = False
    r = client.post("/api/v1/auth/logout", json={"refresh_token": pair["refresh_token"]}, headers=bearer(pair))
    assert r.status_code == 401


# ------------------------------------------------------------------ refresh rotation

def test_refresh_rotates_tokens(client, clock):
    first = register(client).json()
    clock.advance(minutes=20)
    r = refresh(client, first["refresh_token"])
    assert r.status_code == 200
    second = r.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert refresh(client, second["refresh_token"]).status_code == 200


def test_reused_refresh_token_revokes_the_whole_family(client, store):
    first = register(client).json()
    second = refresh(client, first["refresh_token"]).json()
    reuse = refresh(client, first["refresh_token"])  # attacker replays the rotated token
    assert reuse.status_code == 401 and reuse.json()["code"] == "unauthorized"
    assert all(t.revoked_at is not None for t in store.tokens.values())  # committed despite the 401
    assert refresh(client, second["refresh_token"]).status_code == 401  # legitimate holder is logged out too


def test_reuse_does_not_touch_other_families(client):
    register(client)
    a, b = login(client).json(), login(client).json()
    refresh(client, a["refresh_token"])
    refresh(client, a["refresh_token"])  # reuse in family a
    assert refresh(client, b["refresh_token"]).status_code == 200


def test_expired_refresh_token(client, clock):
    pair = register(client).json()
    clock.advance(days=30)
    r = refresh(client, pair["refresh_token"])
    assert r.status_code == 401 and r.json()["code"] == "token_expired"


def test_unknown_refresh_token(client):
    r = refresh(client, "garbage")
    assert r.status_code == 401 and r.json()["code"] == "unauthorized"


def test_refresh_keeps_device_label(client, store):
    register(client)
    pair = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD,
                                                    "device_label": "Pixel 8"}).json()
    refresh(client, pair["refresh_token"])
    assert [t.device_label for t in store.tokens.values()][-1] == "Pixel 8"


# ------------------------------------------------------------------ logout

def test_logout_revokes_family(client):
    pair = register(client).json()
    rotated = refresh(client, pair["refresh_token"]).json()
    r = client.post("/api/v1/auth/logout", json={"refresh_token": rotated["refresh_token"]}, headers=bearer(rotated))
    assert r.status_code == 204 and r.content == b""
    assert refresh(client, rotated["refresh_token"]).status_code == 401


def test_logout_with_another_users_refresh_token_is_401(client):
    mine = register(client).json()
    theirs = register(client, email="other@example.com").json()
    r = client.post("/api/v1/auth/logout", json={"refresh_token": theirs["refresh_token"]}, headers=bearer(mine))
    assert r.status_code == 401
    assert refresh(client, theirs["refresh_token"]).status_code == 200


# ------------------------------------------------------------------ rate limiting

def test_auth_routes_are_rate_limited(settings, clock, store):
    app = create_app(settings.model_copy(update={"auth_rate_limit": 3}), uow_factory=uow_factory(store, clock),
                     clock=clock)
    client = TestClient(app)
    codes = [login(client).status_code for _ in range(4)]
    assert codes == [401, 401, 401, 429]
    r = login(client)
    assert r.json()["code"] == "rate_limited" and int(r.headers["retry-after"]) >= 1
    assert register(client).status_code == 201  # separate bucket per route
    assert refresh(client, "x").status_code == 401  # refresh is not rate limited by contract
