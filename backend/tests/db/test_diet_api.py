"""B-12: generate, read and accept diet plans against a real, seeded PostgreSQL."""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest_asyncio
from sqlalchemy import text

from app.core.config import Settings
from app.domain.constants import DAY_TOLERANCE, MEAL_SLOTS
from app.main import create_app
from tests.support import NO_STORES

BASE = "/api/v1"
PROFILE = {"age": 30, "sex": "male", "weight_kg": 80, "height_cm": 180, "activity_level_pal": 1.55,
           "goal": "maintenance", "experience_level": "beginner", "equipment": "gym"}


@pytest_asyncio.fixture
async def client(seeded_engine):
    url = seeded_engine.url.render_as_string(hide_password=False)
    settings = Settings(jwt_secret="test-secret-" + "x" * 32, bcrypt_rounds=4, auth_rate_limit=10_000,
                        _env_file=None, **{**NO_STORES, "database_url": url})
    app = create_app(settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        yield http
    await app.state.db_engine.dispose()


async def _user(client, profile: dict | None = PROFILE, timezone: str | None = None) -> dict:
    email = f"{uuid.uuid4().hex[:10]}@example.com"
    body = {"email": email, "password": "Secret123", **({"timezone": timezone} if timezone else {})}
    pair = (await client.post(f"{BASE}/auth/register", json=body)).json()
    headers = {"Authorization": f"Bearer {pair['access_token']}"}
    if profile is not None:
        assert (await client.put(f"{BASE}/users/me/profile", json=profile, headers=headers)).status_code == 200
    return headers


async def _food_ids(client, h, *names: str) -> list[int]:
    ids = []
    for name in names:
        items = (await client.get(f"{BASE}/foods?q={name}", headers=h)).json()["items"]
        ids.append(next(f["id"] for f in items if f["name"] == name))
    return ids


def _all_items(plan: dict) -> list[dict]:
    return [i for m in plan["meals"] for i in m["items"]]


# ------------------------------------------------------------------ generate

async def test_requires_authentication(client):
    for method, path in [("post", "/diet-plans/generate"), ("get", "/diet-plans/active"),
                         ("get", "/diet-plans/draft"), ("post", "/diet-plans/1/accept")]:
        assert (await client.request(method, BASE + path, json={})).status_code == 401, path


async def test_generate_needs_a_profile(client):
    h = await _user(client, None)
    r = await client.post(f"{BASE}/diet-plans/generate", json={"meals_per_day": 3}, headers=h)
    assert r.status_code == 404 and r.json()["code"] == "not_found"


async def test_generated_draft_meets_the_targets_every_day(client):
    h = await _user(client)
    r = await client.post(f"{BASE}/diet-plans/generate", json={"meals_per_day": 4}, headers=h)
    assert r.status_code == 201, r.text
    plan = r.json()
    targets = (await client.get(f"{BASE}/nutrition/targets", headers=h)).json()
    assert plan["status"] == "draft" and plan["goal"] == "maintenance" and plan["diet_type"] == "omnivore"
    assert plan["meals_per_day"] == 4 and plan["dietary_restrictions"] == ""
    assert plan["start_date"] is None and plan["end_date"] is None
    assert plan["daily_calorie_target"] == targets["target_kcal"]
    assert (plan["protein_target_g"], plan["fat_target_g"], plan["carbs_target_g"]) == (
        targets["protein_g"], targets["fat_g"], targets["carbs_g"])
    assert plan["name"] == "Maintenance diet, 4 meals per day"

    slots = [mt for mt, _ in MEAL_SLOTS[4]]
    assert len(plan["meals"]) == 28
    daily = {"kcal": plan["daily_calorie_target"], "protein": plan["protein_target_g"], "fat": plan["fat_target_g"],
             "carbs": plan["carbs_target_g"]}
    for day in range(1, 8):
        meals = [m for m in plan["meals"] if m["day_index"] == day]
        assert [m["meal_type"] for m in meals] == slots and [m["meal_order"] for m in meals] == [1, 2, 3, 4]
        for key, limit in DAY_TOLERANCE.items():  # the Done-when: the tolerances of algorithms.md 5.5
            total = sum(m["planned"][key] for m in meals)
            assert abs(total / daily[key] - 1) <= limit + 1e-6, (day, key, total, daily[key])
    for meal in plan["meals"]:
        assert meal["scheduled_time"] is None and meal["items"]
        for key, per100 in (("kcal", "calories_per_100g"), ("protein", "protein_per_100g"),
                            ("fat", "fat_per_100g"), ("carbs", "carbs_per_100g")):
            computed = sum(i["food"][per100] * i["grams"] / 100 for i in meal["items"])
            assert abs(computed - meal["planned"][key]) <= 0.6, (meal["id"], key)  # stored totals match the items
    assert (await client.get(f"{BASE}/diet-plans/draft", headers=h)).json() == plan


async def test_every_goal_and_meal_count_gives_a_plan(client):
    h = await _user(client)
    for goal in ("weight_loss", "muscle_gain", "strength", "general_fitness", "endurance"):
        await client.put(f"{BASE}/users/me/profile", json={**PROFILE, "goal": goal}, headers=h)
        for meals_per_day in (3, 5):
            r = await client.post(f"{BASE}/diet-plans/generate", json={"meals_per_day": meals_per_day}, headers=h)
            assert r.status_code == 201, (goal, meals_per_day, r.text)
            assert r.json()["goal"] == goal and len(r.json()["meals"]) == 7 * meals_per_day


async def test_diet_types_are_respected(client):
    h = await _user(client)
    for diet_type in ("vegetarian", "vegan"):
        plan = (await client.post(f"{BASE}/diet-plans/generate", headers=h,
                                  json={"meals_per_day": 3, "diet_type": diet_type,
                                        "dietary_restrictions": "no raw onion"})).json()
        assert plan["diet_type"] == diet_type and plan["dietary_restrictions"] == "no raw onion"
        assert plan["name"] == f"Maintenance diet ({diet_type}), 3 meals per day"
        for item in _all_items(plan):
            food = (await client.get(f"{BASE}/foods/{item['food']['id']}", headers=h)).json()
            assert food["is_vegetarian"] if diet_type == "vegetarian" else food["is_vegan"], food["name"]


async def test_allergens_and_excluded_foods_are_never_selected(client):
    """Done when (B-12): no product with a user's allergen is ever selected."""
    h = await _user(client)
    allergens = {a["name"]: a["id"] for a in (await client.get(f"{BASE}/allergens", headers=h)).json()}
    await client.put(f"{BASE}/users/me/allergies", headers=h,
                     json={"allergen_ids": [allergens["gluten"], allergens["milk"], allergens["lactose"]]})
    banned = await _food_ids(client, h, "Chicken breast, cooked", "White rice, cooked")
    await client.put(f"{BASE}/users/me/excluded-foods", headers=h, json={"food_item_ids": banned})
    plan = (await client.post(f"{BASE}/diet-plans/generate", json={"meals_per_day": 3}, headers=h)).json()
    assert len(plan["meals"]) == 21
    seen = set()
    for item in _all_items(plan):
        food = (await client.get(f"{BASE}/foods/{item['food']['id']}", headers=h)).json()
        assert not {"gluten", "milk", "lactose"} & {a["name"] for a in food["allergens"]}, food["name"]
        seen.add(food["id"])
    assert not set(banned) & seen


async def test_portions_respect_the_food_bounds(client):
    h = await _user(client)
    plan = (await client.post(f"{BASE}/diet-plans/generate", json={"meals_per_day": 3}, headers=h)).json()
    for item in _all_items(plan):
        food = (await client.get(f"{BASE}/foods/{item['food']['id']}", headers=h)).json()
        assert food["min_portion_g"] <= item["grams"] <= food["max_portion_g"], food["name"]
        assert item["grams"] % food["portion_step_g"] == 0, food["name"]


async def test_invalid_requests_give_field_errors(client):
    h = await _user(client)
    for body, field in [({}, "meals_per_day"), ({"meals_per_day": 2}, "meals_per_day"),
                        ({"meals_per_day": 6}, "meals_per_day"), ({"meals_per_day": "three"}, "meals_per_day"),
                        ({"meals_per_day": 3, "diet_type": "pescatarian"}, "diet_type"),
                        ({"meals_per_day": 3, "diet_type": None}, "diet_type"),
                        ({"meals_per_day": 3, "dietary_restrictions": "x" * 501}, "dietary_restrictions"),
                        ({"meals_per_day": 3, "dietary_restrictions": None}, "dietary_restrictions")]:
        r = await client.post(f"{BASE}/diet-plans/generate", json=body, headers=h)
        assert r.status_code == 422 and r.json()["details"][0]["field"] == field, body


async def test_unreachable_plan_is_a_clear_422_and_keeps_the_old_draft(client):
    h = await _user(client)
    first = (await client.post(f"{BASE}/diet-plans/generate", json={"meals_per_day": 3}, headers=h)).json()
    proteins = (await client.get(f"{BASE}/foods?role=protein&limit=100", headers=h)).json()["items"]
    await client.put(f"{BASE}/users/me/excluded-foods", headers=h,
                     json={"food_item_ids": [f["id"] for f in proteins]})
    r = await client.post(f"{BASE}/diet-plans/generate", json={"meals_per_day": 3}, headers=h)
    assert r.status_code == 422 and r.json()["code"] == "insufficient_foods"
    assert {"field": "food", "code": "no_eligible_food", "meal_type": "lunch", "role": "protein",
            "message": "No eligible food for protein at lunch"} in r.json()["details"]
    assert (await client.get(f"{BASE}/diet-plans/draft", headers=h)).json()["id"] == first["id"]  # nothing stored


# ------------------------------------------------------------------ lifecycle

async def test_regenerating_replaces_the_draft(client, seeded_engine):
    h = await _user(client)
    first = (await client.post(f"{BASE}/diet-plans/generate", json={"meals_per_day": 3}, headers=h)).json()
    second = (await client.post(f"{BASE}/diet-plans/generate", json={"meals_per_day": 5}, headers=h)).json()
    assert second["id"] != first["id"] and second["meals_per_day"] == 5
    assert (await client.get(f"{BASE}/diet-plans/draft", headers=h)).json()["id"] == second["id"]
    assert (await client.post(f"{BASE}/diet-plans/{first['id']}/accept", headers=h)).status_code == 404
    with seeded_engine.connect() as c:
        assert c.execute(text("select count(*) from meal where diet_plan_id = :i"), {"i": first["id"]}).scalar_one() == 0


async def test_concurrent_generation_leaves_exactly_one_draft(client, seeded_engine):
    h = await _user(client)
    results = await asyncio.gather(*[client.post(f"{BASE}/diet-plans/generate", json={"meals_per_day": m}, headers=h)
                                     for m in (3, 4, 5, 3)])
    assert all(r.status_code == 201 for r in results), [r.status_code for r in results]
    draft = (await client.get(f"{BASE}/diet-plans/draft", headers=h)).json()
    with seeded_engine.connect() as c:
        count = c.execute(text("select count(*) from diet_plan where status = 'draft' and user_id ="
                               " (select user_id from diet_plan where id = :i)"), {"i": draft["id"]}).scalar_one()
    assert count == 1


async def test_accept_activates_the_draft_and_archives_the_previous_plan(client, seeded_engine):
    h = await _user(client, timezone="Pacific/Kiritimati")
    assert (await client.get(f"{BASE}/diet-plans/active", headers=h)).status_code == 404
    first = (await client.post(f"{BASE}/diet-plans/generate", json={"meals_per_day": 3}, headers=h)).json()
    plan = (await client.post(f"{BASE}/diet-plans/{first['id']}/accept", headers=h)).json()
    today = datetime.now(ZoneInfo("Pacific/Kiritimati")).date()
    assert plan["status"] == "active" and plan["start_date"] == today.isoformat()
    assert plan["end_date"] == (today + timedelta(days=56)).isoformat()
    assert (await client.get(f"{BASE}/diet-plans/active", headers=h)).json() == plan
    assert (await client.get(f"{BASE}/diet-plans/draft", headers=h)).status_code == 404

    second = (await client.post(f"{BASE}/diet-plans/generate", json={"meals_per_day": 4}, headers=h)).json()
    assert (await client.get(f"{BASE}/diet-plans/active", headers=h)).json()["id"] == first["id"]  # untouched
    accepted = (await client.post(f"{BASE}/diet-plans/{second['id']}/accept", headers=h,
                                  json={"start_date": "2026-12-01"})).json()
    assert accepted["start_date"] == "2026-12-01" and accepted["end_date"] == "2027-01-26"
    with seeded_engine.connect() as c:
        status = c.execute(text("select status::text from diet_plan where id = :i"), {"i": first["id"]}).scalar_one()
    assert status == "archived"


async def test_only_a_draft_can_be_accepted_and_only_by_its_owner(client):
    a, b = await _user(client), await _user(client)
    plan = (await client.post(f"{BASE}/diet-plans/generate", json={"meals_per_day": 3}, headers=a)).json()
    assert (await client.post(f"{BASE}/diet-plans/{plan['id']}/accept", headers=b)).status_code == 404
    assert (await client.get(f"{BASE}/diet-plans/draft", headers=b)).status_code == 404
    assert (await client.post(f"{BASE}/diet-plans/{plan['id']}/accept", headers=a)).status_code == 200
    again = await client.post(f"{BASE}/diet-plans/{plan['id']}/accept", headers=a)
    assert again.status_code == 409 and again.json()["code"] == "conflict"
    assert (await client.post(f"{BASE}/diet-plans/999999/accept", headers=a)).status_code == 404
    assert (await client.post(f"{BASE}/diet-plans/0/accept", headers=a)).status_code == 422
    assert (await client.post(f"{BASE}/diet-plans/{plan['id']}/accept", json={"start_date": None},
                              headers=a)).status_code == 422


async def test_diet_and_training_plans_are_independent(client):
    h = await _user(client)
    training = (await client.post(f"{BASE}/training-plans/generate", headers=h,
                                  json={"goal": "strength", "training_days": 3})).json()
    await client.post(f"{BASE}/training-plans/{training['id']}/accept", headers=h)
    diet = (await client.post(f"{BASE}/diet-plans/generate", json={"meals_per_day": 3}, headers=h)).json()
    await client.post(f"{BASE}/diet-plans/{diet['id']}/accept", headers=h)
    assert (await client.get(f"{BASE}/training-plans/active", headers=h)).json()["status"] == "active"
    assert (await client.get(f"{BASE}/diet-plans/active", headers=h)).json()["status"] == "active"


# ------------------------------------------------------------------ performance

async def test_generation_time_is_reasonable(client):
    """Typical profiles: well within the 3 s of the plan NFR (95th percentile)."""
    h = await _user(client)
    durations = []
    for meals_per_day in (3, 4, 5) * 4:
        start = time.perf_counter()
        r = await client.post(f"{BASE}/diet-plans/generate", json={"meals_per_day": meals_per_day}, headers=h)
        durations.append(time.perf_counter() - start)
        assert r.status_code == 201
    durations.sort()
    assert durations[int(len(durations) * 0.95) - 1] < 3.0, durations[-3:]
