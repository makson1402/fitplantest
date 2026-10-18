"""B-22: real-time meal suggestions against a real, seeded PostgreSQL (algorithms.md section 10, FR-N5).

The two promises of the task: a suggestion never exceeds the remaining kcal by more than 5 %, and never contains an
allergen (or an excluded food, or a food that breaks the diet type)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest_asyncio

from app.core.config import Settings
from app.main import create_app
from tests.db.test_analytics_api import _eat, _food, _user, day
from tests.support import NO_STORES

BASE = "/api/v1"
TOLERANCE = 1.05


@pytest_asyncio.fixture
async def client(seeded_engine):
    url = seeded_engine.url.render_as_string(hide_password=False)
    settings = Settings(jwt_secret="test-secret-" + "x" * 32, bcrypt_rounds=4, auth_rate_limit=10_000,
                        _env_file=None, **{**NO_STORES, "database_url": url})
    app = create_app(settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        yield http
    await app.state.db_engine.dispose()


async def _with_plan(client, diet_type: str | None = None) -> tuple[dict, dict]:
    """A user with an accepted diet plan that started today (so today is plan day 1)."""
    h = await _user(client)
    body = {"meals_per_day": 3, **({"diet_type": diet_type} if diet_type else {})}
    plan = (await client.post(f"{BASE}/diet-plans/generate", json=body, headers=h)).json()
    r = await client.post(f"{BASE}/diet-plans/{plan['id']}/accept", headers=h, json={"start_date": day().isoformat()})
    assert r.status_code == 200, r.text
    return h, r.json()


async def _suggest(client, h, query: str = "") -> dict:
    r = await client.get(f"{BASE}/nutrition/suggestions{query}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


async def _food_detail(client, h, food_id: int) -> dict:
    return (await client.get(f"{BASE}/foods/{food_id}", headers=h)).json()


def _kcal_over(s: dict, limit: float) -> list[dict]:
    return [x for x in s["suggestions"] if x["nutrition"]["kcal"] > limit]


async def test_authentication_a_plan_and_the_date_are_required(client):
    assert (await client.get(f"{BASE}/nutrition/suggestions")).status_code == 401
    h = await _user(client)
    r = await client.get(f"{BASE}/nutrition/suggestions", headers=h)
    assert r.status_code == 404 and r.json()["code"] == "not_found"          # no active diet plan
    plan = (await client.post(f"{BASE}/diet-plans/generate", json={"meals_per_day": 3}, headers=h)).json()
    assert plan["status"] == "draft"
    assert (await client.get(f"{BASE}/nutrition/suggestions", headers=h)).status_code == 404   # a draft is not active
    await client.post(f"{BASE}/diet-plans/{plan['id']}/accept", headers=h, json={"start_date": day().isoformat()})
    for query in ("?date=tomorrow", "?date=2026-13-40", "?date="):
        r = await client.get(f"{BASE}/nutrition/suggestions{query}", headers=h)
        assert r.status_code == 422 and r.json()["code"] == "validation_error", query
    assert (await client.get(f"{BASE}/nutrition/suggestions", headers=h)).status_code == 200


async def test_an_untouched_day_offers_the_best_five_within_the_tolerance(client):
    h, plan = await _with_plan(client)
    s = await _suggest(client, h)
    target = plan["daily_calorie_target"]
    assert s["message"] is None and len(s["suggestions"]) == 5
    assert s["remaining"]["kcal"] == target                                      # nothing eaten yet
    assert (s["remaining"]["protein"], s["remaining"]["fat"], s["remaining"]["carbs"]) == (
        plan["protein_target_g"], plan["fat_target_g"], plan["carbs_target_g"])
    assert not _kcal_over(s, target * TOLERANCE)
    scores = [x["score"] for x in s["suggestions"]]
    assert scores == sorted(scores) and all(score >= 0 for score in scores)      # best (lowest) first
    for x in s["suggestions"]:
        if x["type"] == "food":
            food, grams = x["food"], x["grams"]
            assert x["planned_meal_id"] is None and grams > 0
            assert abs(x["nutrition"]["kcal"] - food["calories_per_100g"] * grams / 100) <= 0.1   # grams match kcal
        else:
            assert x["food"] is None and x["grams"] is None and x["planned_meal_id"]


async def test_the_tolerance_holds_as_the_day_fills_up(client):
    h, plan = await _with_plan(client)
    oil = await _food(client, h, "Olive oil")                                    # 884 kcal / 100 g
    target = plan["daily_calorie_target"]
    eaten = 0.0
    seen_states = 0
    while eaten < target - 100:
        s = await _suggest(client, h)
        left = target - eaten
        assert abs(s["remaining"]["kcal"] - left) <= 0.1
        assert not _kcal_over(s, left * TOLERANCE), (left, s["suggestions"])
        seen_states += 1
        grams = min(left * 0.4, 400) / 8.84
        await _eat(client, h, 0, oil, round(grams))
        eaten += round(grams) * 8.84
    assert seen_states >= 3


async def test_under_100_kcal_left_is_target_reached_and_over_the_target_is_never_negative(client):
    h, plan = await _with_plan(client)
    oil = await _food(client, h, "Olive oil")
    target = plan["daily_calorie_target"]
    await _eat(client, h, 0, oil, round((target - 150) / 8.84))                  # about 150 kcal left
    assert (await _suggest(client, h))["message"] is None
    await _eat(client, h, 0, oil, round(100 / 8.84))                             # about 50 kcal left
    s = await _suggest(client, h)
    assert s["message"] == "target_reached" and s["suggestions"] == [] and 0 < s["remaining"]["kcal"] < 100
    await _eat(client, h, 0, oil, 100)                                            # 884 kcal over the target
    s = await _suggest(client, h)
    assert s["message"] == "target_reached" and s["suggestions"] == []
    assert s["remaining"]["kcal"] == 0.0 and s["remaining"]["fat"] == 0.0         # oil is all fat: over its target
    assert s["remaining"]["protein"] > 0 and all(v >= 0 for v in s["remaining"].values())   # never negative


async def test_other_days_start_from_their_own_logs(client):
    h, plan = await _with_plan(client)
    oil = await _food(client, h, "Olive oil")
    await _eat(client, h, 1, oil, 50)                                             # yesterday: 442 kcal
    yesterday = day(1).isoformat()
    assert abs((await _suggest(client, h, f"?date={yesterday}"))["remaining"]["kcal"]
               - (plan["daily_calorie_target"] - 442)) <= 0.1
    assert (await _suggest(client, h))["remaining"]["kcal"] == plan["daily_calorie_target"]   # today is untouched


async def test_no_suggestion_contains_an_allergen_or_an_excluded_food(client):
    h, _ = await _with_plan(client)
    allergens = (await client.get(f"{BASE}/allergens", headers=h)).json()
    # Every allergen in turn: the suggestions of that user must contain none of its foods (checked per food).
    for allergen in allergens:
        await client.put(f"{BASE}/users/me/allergies", headers=h, json={"allergen_ids": [allergen["id"]]})
        s = await _suggest(client, h)
        for x in s["suggestions"]:
            if x["type"] == "food":
                detail = await _food_detail(client, h, x["food"]["id"])
                assert allergen["id"] not in [a["id"] for a in detail["allergens"]], (allergen["name"], detail["name"])
    await client.put(f"{BASE}/users/me/allergies", headers=h, json={"allergen_ids": [a["id"] for a in allergens]})
    s = await _suggest(client, h)                                                 # allergic to everything listed
    for x in s["suggestions"]:
        if x["type"] == "food":
            assert not (await _food_detail(client, h, x["food"]["id"]))["allergens"]
        else:   # a planned meal is offered only when none of its foods is an allergen now
            plan_meals = (await client.get(f"{BASE}/diet-plans/active", headers=h)).json()["meals"]
            meal = next(m for m in plan_meals if m["id"] == x["planned_meal_id"])
            for item in meal["items"]:
                assert not (await _food_detail(client, h, item["food"]["id"]))["allergens"]

    # excluded foods: take the best food suggestion, exclude it, and it must not come back
    await client.put(f"{BASE}/users/me/allergies", headers=h, json={"allergen_ids": []})
    first = next(x for x in (await _suggest(client, h))["suggestions"] if x["type"] == "food")
    await client.put(f"{BASE}/users/me/excluded-foods", headers=h, json={"food_item_ids": [first["food"]["id"]]})
    after = await _suggest(client, h)
    assert first["food"]["id"] not in [x["food"]["id"] for x in after["suggestions"] if x["type"] == "food"]


async def test_a_vegan_plan_gets_vegan_suggestions_only(client):
    h, _ = await _with_plan(client, "vegan")
    s = await _suggest(client, h)
    assert s["suggestions"]
    for x in s["suggestions"]:
        if x["type"] == "food":
            assert (await _food_detail(client, h, x["food"]["id"]))["is_vegan"], x["food"]["name"]


async def test_a_logged_planned_meal_is_not_suggested_again(client):
    h, plan = await _with_plan(client)
    today_meals = [m for m in plan["meals"] if m["day_index"] == 1]
    offered = {x["planned_meal_id"] for x in (await _suggest(client, h))["suggestions"] if x["type"] == "planned_meal"}
    assert offered and offered <= {m["id"] for m in today_meals}                  # only today's planned meals
    meal = next(m for m in today_meals if m["id"] in offered)
    r = await client.post(f"{BASE}/nutrition-logs", headers=h, json={
        "log_date": day().isoformat(), "meal_type": meal["meal_type"], "planned_meal_id": meal["id"],
        "items": [{"food_item_id": i["food"]["id"], "grams": i["grams"]} for i in meal["items"]]})
    assert r.status_code == 201, r.text
    again = {x["planned_meal_id"] for x in (await _suggest(client, h))["suggestions"] if x["type"] == "planned_meal"}
    assert meal["id"] not in again


async def test_the_plan_day_follows_the_start_date(client):
    """A plan that started 3 days ago is on day 4 today; the planned meals offered are those of day 4."""
    h = await _user(client)
    plan = (await client.post(f"{BASE}/diet-plans/generate", json={"meals_per_day": 3}, headers=h)).json()
    plan = (await client.post(f"{BASE}/diet-plans/{plan['id']}/accept", headers=h,
                              json={"start_date": (datetime.now(UTC).date() - timedelta(days=3)).isoformat()})).json()
    ids = {x["planned_meal_id"] for x in (await _suggest(client, h))["suggestions"] if x["type"] == "planned_meal"}
    assert ids <= {m["id"] for m in plan["meals"] if m["day_index"] == 4}
    week_later = (datetime.now(UTC).date() + timedelta(days=4)).isoformat()      # 7 days after the start: day 1 again
    ids = {x["planned_meal_id"] for x in (await _suggest(client, h, f"?date={week_later}"))["suggestions"]
           if x["type"] == "planned_meal"}
    assert ids <= {m["id"] for m in plan["meals"] if m["day_index"] == 1}
