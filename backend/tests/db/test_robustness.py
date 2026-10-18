"""Regressions for the inputs that made the API answer 500, found by the schemathesis run (task B-28).

A client can send anything: no input may produce a server error. Each case below was a real 500 once."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import httpx
import pytest_asyncio

from app.core.config import Settings
from app.core.timezones import is_valid_timezone, load_timezone
from app.main import create_app
from tests.support import NO_STORES

BASE = "/api/v1"
PASSWORD = "Secret123"


@pytest_asyncio.fixture
async def client(seeded_engine):
    url = seeded_engine.url.render_as_string(hide_password=False)
    settings = Settings(jwt_secret="test-secret-" + "x" * 32, bcrypt_rounds=4, auth_rate_limit=10_000,
                        _env_file=None, **{**NO_STORES, "database_url": url})
    app = create_app(settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        yield http
    await app.state.db_engine.dispose()


async def _user(client) -> dict:
    email = f"{uuid.uuid4().hex[:10]}@example.com"
    pair = (await client.post(f"{BASE}/auth/register", json={"email": email, "password": PASSWORD})).json()
    return {"Authorization": f"Bearer {pair['access_token']}"}


# ------------------------------------------------------------------ time zones

WEIRD = ["America", "Etc", "../../etc/passwd", "/etc/passwd", "UTC\x00", "Mars/Olympus", "", " ", "A" * 500,
         "Europe/Warsaw ", " Europe/Warsaw", "\udb38\udd74\u00a5J", "Europe//Warsaw", "Europe/Warsaw/", "..", ".",
         "Europe\\Warsaw", "C:\\Windows", "a/b/c/d/e", "Zażółć/Gęślą", "CON", "NUL", "%00", "Europe/Warsaw\n"]


def test_only_real_time_zone_names_are_valid():
    for name in ("UTC", "Europe/Warsaw", "America/Argentina/Buenos_Aires", "Etc/GMT+5", "Pacific/Kiritimati"):
        assert is_valid_timezone(name) and load_timezone(name) is not None, name
    for name in WEIRD:
        assert not is_valid_timezone(name) and load_timezone(name) is None, repr(name)
    assert load_timezone(None) is None and load_timezone(5) is None  # type: ignore[arg-type]


async def test_a_strange_time_zone_is_a_422_never_a_500(client):
    h = await _user(client)
    json_header = {"content-type": "application/json"}
    for name in WEIRD:  # sent as raw JSON with escaped characters: httpx cannot encode lone surrogates itself
        body = json.dumps({"email": f"{uuid.uuid4().hex[:8]}@example.com", "password": PASSWORD, "timezone": name})
        r = await client.post(f"{BASE}/auth/register", content=body, headers=json_header)
        assert r.status_code == 422 and r.json()["details"][0]["field"] == "timezone", repr(name)
        r = await client.patch(f"{BASE}/users/me", content=json.dumps({"timezone": name}), headers={**h, **json_header})
        assert r.status_code == 422 and r.json()["details"][0]["field"] == "timezone", repr(name)
    assert (await client.get(f"{BASE}/users/me", headers=h)).json()["timezone"] == "UTC"        # nothing was stored


# ------------------------------------------------------------------ text the database cannot store

async def test_a_nul_character_in_text_is_a_422(client):
    h = await _user(client)
    for body in ({"name": "a\x00b"}, {"surname": "\x00"}):
        r = await client.patch(f"{BASE}/users/me", headers=h, json=body)
        assert r.status_code == 422 and r.json()["code"] == "validation_error", body
    r = await client.post(f"{BASE}/users/me/injuries", headers=h, json={
        "injury_type_id": 1, "affected_muscle_group_id": 1, "severity": "mild", "start_date": "2026-09-01",
        "notes": "x\x00y"})
    assert r.status_code == 422
    assert (await client.get(f"{BASE}/users/me", headers=h)).status_code == 200                # the session still works


# ------------------------------------------------------------------ ids beyond the column range

HUGE = 2**40


async def test_ids_beyond_the_column_range_are_rejected_on_every_route(client):
    h = await _user(client)
    checks = [
        ("get", f"/exercises/{HUGE}", None), ("get", f"/exercises/{HUGE}/alternatives", None),
        ("get", f"/foods/{HUGE}", None), ("get", f"/foods?category_id={HUGE}", None),
        ("get", f"/exercises?muscle_group_id={-HUGE}", None), ("get", f"/foods?offset={2**70}", None),
        ("get", f"/workouts?offset={2**70}", None), ("get", f"/nutrition-logs?offset={2**70}", None),
        ("get", f"/workouts/{2**70}", None), ("delete", f"/workouts/{2**70}", None),
        ("get", f"/nutrition-logs/{2**70}", None), ("delete", f"/body-metrics/{2**70}", None),
        ("post", f"/training-plans/{2**70}/accept", {}), ("post", f"/diet-plans/{2**70}/accept", {}),
        ("patch", f"/session-exercises/{2**70}", {"planned_sets": 3}),
        ("put", f"/session-exercises/{2**70}/swap", {"exercise_id": 1}),
        ("put", "/session-exercises/1/swap", {"exercise_id": HUGE}),
        ("put", "/users/me/allergies", {"allergen_ids": [HUGE]}),
        ("put", "/users/me/excluded-foods", {"food_item_ids": [-HUGE]}),
        ("post", "/users/me/injuries", {"injury_type_id": HUGE, "affected_muscle_group_id": 1, "severity": "mild",
                                        "start_date": "2026-09-01"}),
        ("patch", f"/users/me/injuries/{2**70}", {}),
        ("post", "/nutrition-logs", {"log_date": "2026-10-01", "meal_type": "lunch",
                                     "items": [{"food_item_id": HUGE, "grams": 10}]}),
        ("post", "/nutrition-logs", {"log_date": "2026-10-01", "meal_type": "lunch", "planned_meal_id": 2**70,
                                     "items": [{"food_item_id": 1, "grams": 10}]}),
        ("post", "/workouts", {"performed_on": "2026-10-01", "training_session_id": 2**70,
                               "sets": [{"exercise_id": 1, "set_number": 1, "reps": 5}]}),
        ("post", "/workouts", {"performed_on": "2026-10-01", "sets": [{"exercise_id": HUGE, "set_number": 1,
                                                                        "reps": 5}]}),
    ]
    for method, path, body in checks:
        r = await client.request(method, BASE + path, headers=h, **({"json": body} if body is not None else {}))
        assert r.status_code in (404, 422), (method, path, r.status_code, r.text)
        assert r.json()["code"] in ("validation_error", "not_found")


async def test_a_set_number_beyond_smallint_is_a_422(client):
    h = await _user(client)
    r = await client.post(f"{BASE}/workouts", headers=h, json={
        "performed_on": datetime.now(UTC).date().isoformat(), "sets": [{"exercise_id": 1, "set_number": 40000,
                                                                       "reps": 5}]})
    assert r.status_code == 422 and r.json()["details"][0]["field"] == "sets.0.set_number"


async def test_a_circumference_that_rounds_to_zero_is_a_422(client):
    h = await _user(client)
    today = datetime.now(UTC).date().isoformat()
    for value in (5e-324, 0.001, 0.004):
        r = await client.post(f"{BASE}/body-metrics", headers=h, json={"measured_on": today, "weight_kg": 80,
                                                                       "bicep_cm": value})
        assert r.status_code == 422 and r.json()["details"][0]["field"] == "bicep_cm", value
    assert (await client.post(f"{BASE}/body-metrics", headers=h, json={"measured_on": today, "weight_kg": 80,
                                                                       "bicep_cm": 0.01})).status_code == 200


async def test_the_error_answer_keeps_the_contract_shape(client):
    """details/field/message are absent rather than null (the contract's Error schema is not nullable)."""
    h = await _user(client)
    missing = (await client.get(f"{BASE}/exercises/999999", headers=h)).json()
    assert set(missing) == {"code", "message"}
    invalid = (await client.get(f"{BASE}/exercises?limit=0", headers=h)).json()
    assert invalid["code"] == "validation_error" and all(v is not None for d in invalid["details"] for v in d.values())
