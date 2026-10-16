"""B-17: body measurements against a real, seeded PostgreSQL."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest_asyncio

from app.core.config import Settings
from app.domain.nutrition import tdee
from app.main import create_app
from tests.support import NO_STORES

BASE = "/api/v1"
PROFILE = {"age": 30, "sex": "male", "weight_kg": 80, "height_cm": 180, "activity_level_pal": 1.55,
           "goal": "maintenance", "experience_level": "beginner", "equipment": "gym"}


def day(offset: int = 0):
    return datetime.now(UTC).date() - timedelta(days=offset)


@pytest_asyncio.fixture
async def client(seeded_engine):
    url = seeded_engine.url.render_as_string(hide_password=False)
    settings = Settings(jwt_secret="test-secret-" + "x" * 32, bcrypt_rounds=4, auth_rate_limit=10_000,
                        _env_file=None, **{**NO_STORES, "database_url": url})
    app = create_app(settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        yield http
    await app.state.db_engine.dispose()


async def _user(client, profile: dict | None = PROFILE) -> dict:
    email = f"{uuid.uuid4().hex[:10]}@example.com"
    pair = (await client.post(f"{BASE}/auth/register", json={"email": email, "password": "Secret123"})).json()
    headers = {"Authorization": f"Bearer {pair['access_token']}"}
    if profile is not None:
        assert (await client.put(f"{BASE}/users/me/profile", json=profile, headers=headers)).status_code == 200
    return headers


async def _save(client, h, weight: float, offset: int = 0, **extra):
    return await client.post(f"{BASE}/body-metrics", headers=h,
                             json={"measured_on": day(offset).isoformat(), "weight_kg": weight, **extra})


async def _profile(client, h) -> dict:
    return (await client.get(f"{BASE}/users/me/profile", headers=h)).json()


async def test_requires_authentication(client):
    for method, path in [("post", "/body-metrics"), ("get", "/body-metrics"), ("delete", "/body-metrics/1")]:
        assert (await client.request(method, BASE + path)).status_code == 401, path


async def test_save_returns_the_measurement(client):
    h = await _user(client)
    r = await _save(client, h, 80.126, chest_cm=100, waist_cm=82.5, thigh_cm=58, bicep_cm=35, hip_cm=98, calf_cm=38,
                    body_fat_percent=15.5)
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["weight_kg"] == 80.13 and m["id"] > 0 and uuid.UUID(m["client_uuid"]) and m["updated_at"]
    assert (m["chest_cm"], m["waist_cm"], m["thigh_cm"], m["bicep_cm"], m["hip_cm"], m["calf_cm"],
            m["body_fat_percent"]) == (100.0, 82.5, 58.0, 35.0, 98.0, 38.0, 15.5)
    assert m["measured_on"] == day().isoformat()
    only_weight = (await _save(client, h, 81, offset=1)).json()
    assert only_weight["chest_cm"] is None and only_weight["body_fat_percent"] is None


async def test_a_second_save_for_the_same_day_updates_it(client):
    h = await _user(client)
    first = (await _save(client, h, 80, chest_cm=100)).json()
    second = (await _save(client, h, 79.5)).json()
    assert second["id"] == first["id"] and second["client_uuid"] == first["client_uuid"]
    assert second["weight_kg"] == 79.5 and second["chest_cm"] is None          # the save replaces the measurement
    assert len((await client.get(f"{BASE}/body-metrics", headers=h)).json()) == 1


async def test_history_keeps_several_measurements_newest_first(client):
    h = await _user(client)
    for offset, weight in [(30, 84), (14, 82), (7, 81), (0, 80)]:
        await _save(client, h, weight, offset)
    history = (await client.get(f"{BASE}/body-metrics", headers=h)).json()
    assert [m["weight_kg"] for m in history] == [80, 81, 82, 84]
    window = (await client.get(f"{BASE}/body-metrics?from={day(14)}&to={day(7)}", headers=h)).json()   # inclusive
    assert [m["weight_kg"] for m in window] == [81, 82]
    assert (await client.get(f"{BASE}/body-metrics?from=soon", headers=h)).status_code == 422
    other = await _user(client)
    assert (await client.get(f"{BASE}/body-metrics", headers=other)).json() == []


async def test_values_are_range_validated(client):
    h = await _user(client)
    cases = [("weight_kg", [29, 29.99, 300.01, 301, 0, -5], [30, 300]),
             ("body_fat_percent", [1.99, 70.01, 0, -1], [2, 70]),
             ("chest_cm", [0, -1, 1000], [0.01, 999.99]), ("waist_cm", [0, -3], [60]), ("thigh_cm", [0], [50]),
             ("bicep_cm", [0], [30]), ("hip_cm", [0], [90]), ("calf_cm", [0], [35])]
    for i, (field, bad, ok) in enumerate(cases):
        for value in bad:
            r = await client.post(f"{BASE}/body-metrics", headers=h, json={
                "measured_on": day(100 + i).isoformat(), "weight_kg": 80, **{field: value}} if field != "weight_kg"
                else {"measured_on": day(100 + i).isoformat(), "weight_kg": value})
            assert r.status_code == 422 and r.json()["details"][0]["field"] == field, (field, value, r.text)
        for value in ok:
            body = ({"measured_on": day(100 + i).isoformat(), "weight_kg": value} if field == "weight_kg"
                    else {"measured_on": day(100 + i).isoformat(), "weight_kg": 80, field: value})
            assert (await client.post(f"{BASE}/body-metrics", headers=h, json=body)).status_code == 200, (field, value)


async def test_other_invalid_input(client):
    h = await _user(client)
    for body, field in [({"weight_kg": 80}, "measured_on"), ({"measured_on": day().isoformat()}, "weight_kg"),
                        ({"measured_on": "yesterday", "weight_kg": 80}, "measured_on"),
                        ({"measured_on": (day() + timedelta(days=3)).isoformat(), "weight_kg": 80}, "measured_on"),
                        ({"measured_on": day().isoformat(), "weight_kg": 80, "client_uuid": None}, "client_uuid"),
                        ({"measured_on": day().isoformat(), "weight_kg": "heavy"}, "weight_kg")]:
        r = await client.post(f"{BASE}/body-metrics", headers=h, json=body)
        assert r.status_code == 422 and r.json()["details"][0]["field"] == field, body
    raw = '{"measured_on": "' + day().isoformat() + '", "weight_kg": NaN}'
    assert (await client.post(f"{BASE}/body-metrics", content=raw,
                              headers={**h, "content-type": "application/json"})).status_code == 422


async def test_client_uuid_makes_saves_idempotent(client):
    h = await _user(client)
    cid = str(uuid.uuid4())
    first = (await _save(client, h, 80, client_uuid=cid)).json()
    again = (await _save(client, h, 80, client_uuid=cid)).json()
    assert first["client_uuid"] == cid and again["id"] == first["id"]
    moved = (await _save(client, h, 79, offset=2, client_uuid=cid)).json()           # same uuid, another day: moved
    assert moved["id"] == first["id"] and moved["measured_on"] == day(2).isoformat()
    other_day = (await _save(client, h, 78, offset=0)).json()
    clash = await _save(client, h, 77, offset=0, client_uuid=cid)                    # that day belongs to another record
    assert clash.status_code == 409 and clash.json()["code"] == "conflict" and other_day["id"] != moved["id"]
    assert len((await client.get(f"{BASE}/body-metrics", headers=h)).json()) == 2


async def test_delete_and_tombstone(client):
    h = await _user(client)
    cid = str(uuid.uuid4())
    record = (await _save(client, h, 80, client_uuid=cid)).json()
    other = await _user(client)
    assert (await client.delete(f"{BASE}/body-metrics/{record['id']}", headers=other)).status_code == 404
    assert (await client.delete(f"{BASE}/body-metrics/{record['id']}", headers=h)).status_code == 204
    assert (await client.delete(f"{BASE}/body-metrics/{record['id']}", headers=h)).status_code == 404
    assert (await client.delete(f"{BASE}/body-metrics/0", headers=h)).status_code == 422
    assert (await client.get(f"{BASE}/body-metrics", headers=h)).json() == []
    assert (await _save(client, h, 80, client_uuid=cid)).status_code == 409           # a tombstone keeps its uuid
    assert (await _save(client, h, 81)).status_code == 200                            # the day itself is free again


async def test_the_newest_measurement_is_the_current_weight_in_the_profile(client):
    h = await _user(client)
    await _save(client, h, 78.5)
    profile = await _profile(client, h)
    assert profile["weight_kg"] == 78.5
    assert profile["tdee_kcal"] == tdee("male", 78.5, 180, 30, 1.55)                  # TDEE follows the weight
    await _save(client, h, 70, offset=10)                                              # older: the profile is unchanged
    assert (await _profile(client, h))["weight_kg"] == 78.5
    await _save(client, h, 78)                                                         # today's measurement edited
    assert (await _profile(client, h))["weight_kg"] == 78.0


async def test_deleting_the_newest_measurement_restores_the_previous_weight(client):
    h = await _user(client)
    await _save(client, h, 80, offset=5)
    newest = (await _save(client, h, 77, offset=0)).json()
    assert (await _profile(client, h))["weight_kg"] == 77
    await client.delete(f"{BASE}/body-metrics/{newest['id']}", headers=h)
    restored = await _profile(client, h)
    assert restored["weight_kg"] == 80 and restored["tdee_kcal"] == tdee("male", 80, 180, 30, 1.55)


async def test_measurements_work_without_a_profile(client):
    h = await _user(client, None)
    assert (await _save(client, h, 80)).status_code == 200
    assert (await client.get(f"{BASE}/users/me/profile", headers=h)).status_code == 404   # nothing created
