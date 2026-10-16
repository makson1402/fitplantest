"""B-21: meal logging and the daily summary against a real, seeded PostgreSQL."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core.config import Settings
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


async def _food(client, h, name: str) -> dict:
    items = (await client.get(f"{BASE}/foods?q={name}", headers=h)).json()["items"]
    return next(f for f in items if f["name"] == name)


def _log(items: list[tuple[int, float]], offset: int = 0, meal_type: str = "lunch", **extra) -> dict:
    return {"log_date": day(offset).isoformat(), "meal_type": meal_type,
            "items": [{"food_item_id": f, "grams": g} for f, g in items], **extra}


async def _create(client, h, body: dict) -> dict:
    r = await client.post(f"{BASE}/nutrition-logs", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def _sum(log: dict, key: str) -> float:
    return sum(i["nutrition"][key] for i in log["items"])


async def test_requires_authentication(client):
    for method, path in [("post", "/nutrition-logs"), ("get", "/nutrition-logs"), ("get", "/nutrition-logs/1"),
                         ("patch", "/nutrition-logs/1"), ("delete", "/nutrition-logs/1"),
                         ("get", "/nutrition/daily-summary")]:
        assert (await client.request(method, BASE + path)).status_code == 401, path


# ------------------------------------------------------------------ create

async def test_totals_are_the_sum_of_the_items_computed_from_the_food_database(client, seeded_engine):
    """Done when (B-21): totals match the sum of logged items."""
    h = await _user(client)
    chicken, rice = await _food(client, h, "Chicken breast, cooked"), await _food(client, h, "White rice, cooked")
    log = await _create(client, h, _log([(chicken["id"], 150), (rice["id"], 200.5)], hunger_level_before=7,
                                        hunger_level_after=2))
    by_id = {i["food"]["id"]: i for i in log["items"]}
    # per 100 g x grams / 100: 150 g of chicken (165 kcal, 31 g protein, 3.6 g fat) and 200.5 g of rice
    assert by_id[chicken["id"]]["grams"] == 150 and by_id[chicken["id"]]["nutrition"] == {
        "kcal": 247.5, "protein": 46.5, "fat": 5.4, "carbs": 0.0}
    assert by_id[rice["id"]]["grams"] == 200.5 and by_id[rice["id"]]["nutrition"]["kcal"] == 260.65
    for key in ("kcal", "protein", "fat", "carbs"):
        assert log["totals"][key] == pytest.approx(_sum(log, key), abs=1e-9), key
    assert log["totals"]["kcal"] == 508.15
    assert (log["hunger_level_before"], log["hunger_level_after"]) == (7, 2)
    assert log["meal_type"] == "lunch" and log["log_date"] == day().isoformat()
    assert log["planned_meal_id"] is None and log["recognition_id"] is None and log["meal_photo_url"] is None
    assert uuid.UUID(log["client_uuid"]) and log["logged_at"] and log["updated_at"]
    with seeded_engine.connect() as c:  # the stored columns agree with the stored items
        row = c.execute(text(
            "select l.actual_calories, sum(i.calories) from nutrition_log l join nutrition_log_food_item i"
            " on i.nutrition_log_id = l.id where l.id = :i group by l.id"), {"i": log["id"]}).one()
    assert float(row[0]) == float(row[1]) == 508.15
    assert (await client.get(f"{BASE}/nutrition-logs/{log['id']}", headers=h)).json() == log


async def test_invalid_input_is_reported_per_field(client):
    h = await _user(client)
    chicken = await _food(client, h, "Chicken breast, cooked")
    cid = chicken["id"]
    oil = await _food(client, h, "Olive oil")
    cases = {
        "items.0.grams": [_log([(cid, 0)]), _log([(cid, -5)]), _log([(cid, 2000.5)]), _log([(cid, 0.04)])],
        "items.0.food_item_id": [_log([(999999, 100)])],
        "items.1.food_item_id": [_log([(cid, 100), (cid, 50)])],                                         # duplicate
        "items": [_log([]), _log([(oil["id"], 2000)])],                                                  # empty, 17 680 kcal
        "hunger_level_before": [_log([(cid, 100)], hunger_level_before=0), _log([(cid, 100)], hunger_level_before=11)],
        "hunger_level_after": [_log([(cid, 100)], hunger_level_after=0), _log([(cid, 100)], hunger_level_after=11)],
        "meal_type": [_log([(cid, 100)], meal_type="brunch")],
        "log_date": [_log([(cid, 100)], offset=-3), {**_log([(cid, 100)]), "log_date": "today"}],
        "planned_meal_id": [_log([(cid, 100)], planned_meal_id=999999)],
        "client_uuid": [_log([(cid, 100)], client_uuid=None)],
    }
    for field, bodies in cases.items():
        for body in bodies:
            r = await client.post(f"{BASE}/nutrition-logs", json=body, headers=h)
            assert r.status_code == 422, (field, body, r.text)
            assert field in {d["field"] for d in r.json()["details"]}, (field, r.json()["details"])
    for boundary in (1, 10):
        assert (await client.post(f"{BASE}/nutrition-logs", headers=h, json=_log(
            [(cid, 0.1)], hunger_level_before=boundary, hunger_level_after=boundary))).status_code == 201
    assert (await client.post(f"{BASE}/nutrition-logs", headers=h, json=_log([(cid, 2000)]))).status_code == 201
    assert (await client.get(f"{BASE}/nutrition-logs", headers=h)).json()["total"] == 3         # failures stored nothing


async def test_inactive_foods_cannot_be_logged(client, seeded_engine):
    h = await _user(client)
    honey = await _food(client, h, "Honey")
    with seeded_engine.begin() as c:
        c.execute(text("update food_item set is_active = false where id = :i"), {"i": honey["id"]})
    try:
        r = await client.post(f"{BASE}/nutrition-logs", json=_log([(honey["id"], 20)]), headers=h)
        assert r.status_code == 422 and r.json()["details"][0]["field"] == "items.0.food_item_id"
    finally:
        with seeded_engine.begin() as c:
            c.execute(text("update food_item set is_active = true where id = :i"), {"i": honey["id"]})


async def test_a_meal_from_the_plan_can_be_logged(client):
    h = await _user(client)
    plan = (await client.post(f"{BASE}/diet-plans/generate", json={"meals_per_day": 3}, headers=h)).json()
    meal = plan["meals"][0]
    items = [(i["food"]["id"], i["grams"]) for i in meal["items"]]
    log = await _create(client, h, _log(items, meal_type=meal["meal_type"], planned_meal_id=meal["id"]))
    assert log["planned_meal_id"] == meal["id"]
    assert log["totals"]["kcal"] == pytest.approx(meal["planned"]["kcal"], abs=1.0)  # eaten as planned
    other = await _user(client)
    r = await client.post(f"{BASE}/nutrition-logs", headers=other, json=_log(items, planned_meal_id=meal["id"]))
    assert r.status_code == 422 and r.json()["details"][0]["field"] == "planned_meal_id"  # another user's meal


async def test_client_uuid_makes_retries_idempotent(client):
    h = await _user(client)
    chicken = await _food(client, h, "Chicken breast, cooked")
    body = _log([(chicken["id"], 100)], client_uuid=str(uuid.uuid4()))
    first = await _create(client, h, body)
    assert await _create(client, h, body) == first
    assert (await client.get(f"{BASE}/nutrition-logs", headers=h)).json()["total"] == 1
    other = await _user(client)
    assert (await client.post(f"{BASE}/nutrition-logs", json=body, headers=other)).status_code == 201
    await client.delete(f"{BASE}/nutrition-logs/{first['id']}", headers=h)
    assert (await client.post(f"{BASE}/nutrition-logs", json=body, headers=h)).status_code == 409


# ------------------------------------------------------------------ list, get, update, delete

async def test_history_is_filtered_ordered_paginated_and_private(client):
    h = await _user(client)
    chicken = await _food(client, h, "Chicken breast, cooked")
    ids = {}
    for offset in (10, 5, 1, 0):
        ids[offset] = (await _create(client, h, _log([(chicken["id"], 100)], offset)))["id"]
    page = (await client.get(f"{BASE}/nutrition-logs", headers=h)).json()
    assert page["total"] == 4 and [x["id"] for x in page["items"]] == [ids[0], ids[1], ids[5], ids[10]]
    assert (page["limit"], page["offset"]) == (20, 0) and page["items"][0]["items"]
    window = (await client.get(f"{BASE}/nutrition-logs?from={day(5)}&to={day(1)}", headers=h)).json()
    assert [x["id"] for x in window["items"]] == [ids[1], ids[5]] and window["total"] == 2
    second = (await client.get(f"{BASE}/nutrition-logs?limit=2&offset=2", headers=h)).json()
    assert [x["id"] for x in second["items"]] == [ids[5], ids[10]] and second["total"] == 4
    other = await _user(client)
    assert (await client.get(f"{BASE}/nutrition-logs", headers=other)).json()["total"] == 0
    assert (await client.get(f"{BASE}/nutrition-logs/{ids[0]}", headers=other)).status_code == 404
    for query in ("limit=0", "limit=101", "offset=-1", "to=soon"):
        assert (await client.get(f"{BASE}/nutrition-logs?{query}", headers=h)).status_code == 422, query


async def test_update_items_and_hunger(client):
    h = await _user(client)
    chicken, rice = await _food(client, h, "Chicken breast, cooked"), await _food(client, h, "White rice, cooked")
    log = await _create(client, h, _log([(chicken["id"], 100)], hunger_level_before=8))
    url = f"{BASE}/nutrition-logs/{log['id']}"
    r = await client.patch(url, json={"items": [{"food_item_id": rice["id"], "grams": 300},
                                                {"food_item_id": chicken["id"], "grams": 120}]}, headers=h)
    assert r.status_code == 200, r.text
    changed = r.json()
    assert {i["food"]["id"] for i in changed["items"]} == {rice["id"], chicken["id"]}
    assert changed["totals"]["kcal"] == pytest.approx(300 * 1.30 + 120 * 1.65, abs=0.01)
    for key in ("kcal", "protein", "fat", "carbs"):
        assert changed["totals"][key] == pytest.approx(_sum(changed, key), abs=1e-9)
    assert changed["hunger_level_before"] == 8                                   # untouched
    only_hunger = (await client.patch(url, json={"hunger_level_after": 3}, headers=h)).json()
    assert only_hunger["hunger_level_after"] == 3 and only_hunger["totals"] == changed["totals"]
    cleared = (await client.patch(url, json={"hunger_level_before": None}, headers=h)).json()
    assert cleared["hunger_level_before"] is None and cleared["hunger_level_after"] == 3
    assert (await client.get(url, headers=h)).json() == cleared


async def test_update_validation_and_ownership(client):
    h = await _user(client)
    chicken = await _food(client, h, "Chicken breast, cooked")
    log = await _create(client, h, _log([(chicken["id"], 100)]))
    url = f"{BASE}/nutrition-logs/{log['id']}"
    for body, field in [({}, ""), ({"items": []}, "items"), ({"items": None}, "items"),
                        ({"items": [{"food_item_id": 999999, "grams": 10}]}, "items.0.food_item_id"),
                        ({"items": [{"food_item_id": chicken["id"], "grams": 0}]}, "items.0.grams"),
                        ({"hunger_level_before": 0}, "hunger_level_before"),
                        ({"hunger_level_after": 11}, "hunger_level_after")]:
        r = await client.patch(url, json=body, headers=h)
        assert r.status_code == 422, body
        assert field in {d["field"] for d in r.json()["details"]} or field == "", (body, r.json())
    assert (await client.get(url, headers=h)).json() == log                      # nothing changed
    other = await _user(client)
    assert (await client.patch(url, json={"hunger_level_after": 3}, headers=other)).status_code == 404
    assert (await client.patch(f"{BASE}/nutrition-logs/999999", json={"hunger_level_after": 3},
                               headers=h)).status_code == 404
    assert (await client.patch(f"{BASE}/nutrition-logs/0", json={"hunger_level_after": 3}, headers=h)).status_code == 422


async def test_delete_is_soft_and_private(client):
    h = await _user(client)
    chicken = await _food(client, h, "Chicken breast, cooked")
    log = await _create(client, h, _log([(chicken["id"], 100)]))
    other = await _user(client)
    assert (await client.delete(f"{BASE}/nutrition-logs/{log['id']}", headers=other)).status_code == 404
    assert (await client.delete(f"{BASE}/nutrition-logs/{log['id']}", headers=h)).status_code == 204
    assert (await client.delete(f"{BASE}/nutrition-logs/{log['id']}", headers=h)).status_code == 404
    assert (await client.get(f"{BASE}/nutrition-logs/{log['id']}", headers=h)).status_code == 404
    assert (await client.get(f"{BASE}/nutrition-logs", headers=h)).json()["total"] == 0


# ------------------------------------------------------------------ daily summary

async def test_summary_of_an_empty_day_without_a_diet_plan(client):
    h = await _user(client)
    r = await client.get(f"{BASE}/nutrition/daily-summary?date={day()}", headers=h)
    assert r.status_code == 200
    assert r.json() == {"date": day().isoformat(), "targets": None, "totals": {"kcal": 0.0, "protein": 0.0, "fat": 0.0,
                                                                              "carbs": 0.0}, "remaining": None,
                        "logs_count": 0, "avg_hunger_before": None, "avg_hunger_after": None}


async def test_summary_totals_targets_remaining_and_hunger(client):
    h = await _user(client)
    chicken, rice = await _food(client, h, "Chicken breast, cooked"), await _food(client, h, "White rice, cooked")
    plan = (await client.post(f"{BASE}/diet-plans/generate", json={"meals_per_day": 3}, headers=h)).json()
    await client.post(f"{BASE}/diet-plans/{plan['id']}/accept", headers=h)
    first = await _create(client, h, _log([(chicken["id"], 200)], hunger_level_before=8, hunger_level_after=3))
    second = await _create(client, h, _log([(rice["id"], 150)], meal_type="dinner", hunger_level_before=6))
    await _create(client, h, _log([(chicken["id"], 100)], offset=1))                 # another day: not counted
    third = await _create(client, h, _log([(rice["id"], 100)], meal_type="snack"))   # no hunger data at all
    await client.delete(f"{BASE}/nutrition-logs/{third['id']}", headers=h)           # deleted: not counted
    summary = (await client.get(f"{BASE}/nutrition/daily-summary?date={day()}", headers=h)).json()
    for key in ("kcal", "protein", "fat", "carbs"):
        assert summary["totals"][key] == pytest.approx(first["totals"][key] + second["totals"][key], abs=1e-9), key
    assert summary["logs_count"] == 2
    assert summary["targets"] == {"kcal": plan["daily_calorie_target"], "protein": plan["protein_target_g"],
                                  "fat": plan["fat_target_g"], "carbs": plan["carbs_target_g"]}
    for key in ("kcal", "protein", "fat", "carbs"):
        assert summary["remaining"][key] == pytest.approx(summary["targets"][key] - summary["totals"][key], abs=1e-9)
    assert summary["avg_hunger_before"] == 7.0 and summary["avg_hunger_after"] == 3.0   # nulls are ignored
    past = (await client.get(f"{BASE}/nutrition/daily-summary?date={day(1)}", headers=h)).json()
    assert past["logs_count"] == 1 and past["avg_hunger_before"] is None
    other = await _user(client)
    assert (await client.get(f"{BASE}/nutrition/daily-summary?date={day()}", headers=other)).json()["logs_count"] == 0


async def test_remaining_goes_negative_when_the_target_is_exceeded(client):
    h = await _user(client)
    plan = (await client.post(f"{BASE}/diet-plans/generate", json={"meals_per_day": 3}, headers=h)).json()
    await client.post(f"{BASE}/diet-plans/{plan['id']}/accept", headers=h)
    oil = await _food(client, h, "Olive oil")
    for meal_type in ("breakfast", "lunch", "dinner"):
        await _create(client, h, _log([(oil["id"], 200)], meal_type=meal_type))     # 1 768 kcal each
    summary = (await client.get(f"{BASE}/nutrition/daily-summary?date={day()}", headers=h)).json()
    assert summary["remaining"]["kcal"] < 0 and summary["remaining"]["fat"] < 0


async def test_summary_needs_a_valid_date(client):
    h = await _user(client)
    assert (await client.get(f"{BASE}/nutrition/daily-summary", headers=h)).status_code == 422
    r = await client.get(f"{BASE}/nutrition/daily-summary?date=tomorrow", headers=h)
    assert r.status_code == 422 and r.json()["details"][0]["field"] == "date"
