"""B-10: GET /nutrition/targets. The worked examples of docs/algorithms.md section 2 must come out of the API."""
from __future__ import annotations

import uuid

import httpx
import pytest
import pytest_asyncio

from app.core.config import Settings
from app.main import create_app
from tests.support import NO_STORES

BASE = "/api/v1"
FIELDS = ("bmr_kcal", "tdee_kcal", "target_kcal", "protein_g", "fat_g", "carbs_g")


@pytest_asyncio.fixture
async def client(pg_engine):
    url = pg_engine.url.render_as_string(hide_password=False)
    settings = Settings(jwt_secret="test-secret-" + "x" * 32, bcrypt_rounds=4, auth_rate_limit=10_000,
                        _env_file=None, **{**NO_STORES, "database_url": url})
    app = create_app(settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        yield http
    await app.state.db_engine.dispose()


async def _user(client) -> dict:
    email = f"{uuid.uuid4().hex[:10]}@example.com"
    pair = (await client.post(f"{BASE}/auth/register", json={"email": email, "password": "Secret123"})).json()
    return {"Authorization": f"Bearer {pair['access_token']}"}


def _profile(sex, weight, height, age, pal, goal):
    return {"age": age, "sex": sex, "weight_kg": weight, "height_cm": height, "activity_level_pal": pal, "goal": goal,
            "experience_level": "beginner", "equipment": "none"}


# docs/algorithms.md section 2 test vectors: (inputs) -> (BMR, TDEE, target kcal, protein g, fat g, carbs g)
VECTORS = [
    (("male", 80, 180, 25, 1.55, "muscle_gain"), (1805.0, 2798, 3078, 144.0, 85.5, 433.1)),
    (("female", 60, 165, 30, 1.375, "weight_loss"), (1320.3, 1815, 1452, 120.0, 48.4, 134.1)),
    (("female", 55, 155, 60, 1.2, "weight_loss"), (1057.8, 1269, 1200, 105.0, 40.0, 105.0)),  # kcal floor applies
    (("male", 120, 185, 35, 1.375, "weight_loss"), (2186.3, 3006, 2405, 210.4, 80.2, 210.4)),  # protein cap applies
]


@pytest.mark.parametrize(("inputs", "expected"), VECTORS)
async def test_worked_examples_of_the_specification(client, inputs, expected):
    h = await _user(client)
    assert (await client.put(f"{BASE}/users/me/profile", json=_profile(*inputs), headers=h)).status_code == 200
    r = await client.get(f"{BASE}/nutrition/targets", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert tuple(body[f] for f in FIELDS) == expected
    assert body["goal"] == inputs[5]


async def test_targets_agree_with_the_stored_profile_tdee(client):
    h = await _user(client)
    profile = (await client.put(f"{BASE}/users/me/profile", json=_profile("male", 80, 180, 25, 1.725, "strength"),
                                headers=h)).json()
    targets = (await client.get(f"{BASE}/nutrition/targets", headers=h)).json()
    assert targets["tdee_kcal"] == profile["tdee_kcal"]


async def test_targets_follow_profile_changes(client):
    h = await _user(client)
    await client.put(f"{BASE}/users/me/profile", json=_profile("male", 80, 180, 25, 1.55, "maintenance"), headers=h)
    before = (await client.get(f"{BASE}/nutrition/targets", headers=h)).json()
    await client.put(f"{BASE}/users/me/profile", json=_profile("male", 80, 180, 25, 1.55, "muscle_gain"), headers=h)
    after = (await client.get(f"{BASE}/nutrition/targets", headers=h)).json()
    assert after["goal"] == "muscle_gain" and after["tdee_kcal"] == before["tdee_kcal"]  # goal changes the target only
    assert after["target_kcal"] > before["target_kcal"]


async def test_every_goal_gives_consistent_macros(client):
    """kcal from the macros adds up to the target (within rounding) for every goal and sex."""
    h = await _user(client)
    for sex in ("male", "female", "other"):
        for goal in ("weight_loss", "muscle_gain", "strength", "maintenance", "general_fitness", "endurance"):
            await client.put(f"{BASE}/users/me/profile", json=_profile(sex, 70, 172, 33, 1.55, goal), headers=h)
            t = (await client.get(f"{BASE}/nutrition/targets", headers=h)).json()
            assert abs(4 * t["protein_g"] + 9 * t["fat_g"] + 4 * t["carbs_g"] - t["target_kcal"]) <= 3, (sex, goal)
            assert t["carbs_g"] > 0 and t["target_kcal"] >= (1500 if sex == "male" else 1200)


async def test_no_profile_gives_404_and_no_token_gives_401(client):
    h = await _user(client)
    r = await client.get(f"{BASE}/nutrition/targets", headers=h)
    assert r.status_code == 404 and r.json()["code"] == "not_found"
    assert (await client.get(f"{BASE}/nutrition/targets")).status_code == 401


async def test_users_get_their_own_targets(client):
    a, b = await _user(client), await _user(client)
    await client.put(f"{BASE}/users/me/profile", json=_profile("male", 80, 180, 25, 1.55, "muscle_gain"), headers=a)
    await client.put(f"{BASE}/users/me/profile", json=_profile("female", 55, 155, 60, 1.2, "weight_loss"), headers=b)
    assert (await client.get(f"{BASE}/nutrition/targets", headers=a)).json()["target_kcal"] == 3078
    assert (await client.get(f"{BASE}/nutrition/targets", headers=b)).json()["target_kcal"] == 1200
