"""B-23 / B-24: analytics, chart series and the goal prediction against a real, seeded PostgreSQL.

Every expectation is computed by hand from the data the test logs (dates are relative to today)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest_asyncio

from app.core.config import Settings
from app.main import create_app
from tests.support import NO_STORES

BASE = "/api/v1"
PROFILE = {"age": 30, "sex": "male", "weight_kg": 80, "height_cm": 180, "activity_level_pal": 1.55,
           "goal": "weight_loss", "experience_level": "beginner", "equipment": "gym"}


def day(offset: int = 0):
    """The date `offset` days before today."""
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


async def _weigh(client, h, offset: int, weight: float) -> None:
    r = await client.post(f"{BASE}/body-metrics", headers=h, json={"measured_on": day(offset).isoformat(),
                                                                    "weight_kg": weight})
    assert r.status_code == 200, r.text


async def _train(client, h, offset: int, sets: list[tuple[int, int, float, bool]], **extra) -> dict:
    """sets: (exercise_id, reps, weight_kg, completed); set numbers count per exercise."""
    numbers: dict[int, int] = {}
    body = []
    for exercise_id, reps, weight, completed in sets:
        numbers[exercise_id] = numbers.get(exercise_id, 0) + 1
        body.append({"exercise_id": exercise_id, "set_number": numbers[exercise_id], "reps": reps,
                     "weight_kg": weight, "completed": completed})
    r = await client.post(f"{BASE}/workouts", headers=h,
                          json={"performed_on": day(offset).isoformat(), "sets": body, **extra})
    assert r.status_code == 201, r.text
    return r.json()


async def _food(client, h, name: str) -> int:
    items = (await client.get(f"{BASE}/foods?q={name}", headers=h)).json()["items"]
    return next(f["id"] for f in items if f["name"] == name)


async def _eat(client, h, offset: int, food_id: int, grams: float, meal_type: str = "lunch") -> dict:
    r = await client.post(f"{BASE}/nutrition-logs", headers=h, json={
        "log_date": day(offset).isoformat(), "meal_type": meal_type, "items": [{"food_item_id": food_id, "grams": grams}]})
    assert r.status_code == 201, r.text
    return r.json()


async def _exercise_ids(client, h, count: int = 2) -> list[int]:
    return [e["id"] for e in (await client.get(f"{BASE}/exercises?limit={count}", headers=h)).json()["items"]]


async def _summary(client, h, period: str) -> dict:
    r = await client.get(f"{BASE}/analytics/summary?period={period}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


async def test_requires_authentication_and_valid_parameters(client):
    for path in ("/analytics/summary?period=week", "/analytics/charts/weight?period=week", "/analytics/goal-prediction"):
        assert (await client.get(BASE + path)).status_code == 401, path
    h = await _user(client)
    for path in ("/analytics/summary", "/analytics/summary?period=year", "/analytics/charts/steps?period=week",
                 "/analytics/charts/weight", "/analytics/charts/weight?period=day"):
        r = await client.get(BASE + path, headers=h)
        assert r.status_code == 422 and r.json()["code"] == "validation_error", path


# ------------------------------------------------------------------ minimum data (FR-R5)

async def test_six_days_of_history_are_not_enough_and_seven_are(client):
    """The 6-day and 7-day boundary of algorithms.md 8, counting distinct days across all kinds of records."""
    h = await _user(client)
    chicken = await _food(client, h, "Chicken breast, cooked")
    ex = (await _exercise_ids(client, h, 1))[0]
    await _weigh(client, h, 1, 80)
    await _weigh(client, h, 1, 79.5)                                    # the same day again: still one day
    await _eat(client, h, 2, chicken, 100)
    await _eat(client, h, 2, chicken, 50, "dinner")                     # same day
    await _train(client, h, 3, [(ex, 5, 50, True)])
    await _weigh(client, h, 4, 80)
    await _eat(client, h, 5, chicken, 100)
    await _train(client, h, 6, [(ex, 5, 50, True)])
    for period in ("week", "month", "3months"):
        s = await _summary(client, h, period)
        assert s["status"] == "insufficient_data", period              # 6 distinct days
        assert s["from"] and s["to"] == day().isoformat()
        assert all(s[k] is None for k in ("weight_change_kg", "total_workouts", "avg_workouts_per_week", "avg_calories",
                                          "tonnage_kg", "workout_compliance_pct", "diet_compliance_pct"))
        assert s["key_lifts"] == []
    chart = (await client.get(f"{BASE}/analytics/charts/weight?period=month", headers=h)).json()
    assert chart["status"] == "insufficient_data" and chart["points"] == []

    await _weigh(client, h, 7, 80)                                      # the 7th distinct day
    assert (await _summary(client, h, "month"))["status"] == "ok"
    chart = (await client.get(f"{BASE}/analytics/charts/weight?period=month", headers=h)).json()
    # one weigh-in per day: days 7 and 4 as logged, day 1 updated to its second value
    assert chart["status"] == "ok" and [(p["date"], p["value"]) for p in chart["points"]] == [
        (day(7).isoformat(), 80.0), (day(4).isoformat(), 80.0), (day(1).isoformat(), 79.5)]


async def test_deleted_records_do_not_count_as_history(client):
    h = await _user(client)
    for offset in range(1, 8):
        await _weigh(client, h, offset, 80)
    history = (await client.get(f"{BASE}/body-metrics", headers=h)).json()
    assert (await _summary(client, h, "week"))["status"] == "ok"
    await client.delete(f"{BASE}/body-metrics/{history[0]['id']}", headers=h)
    assert (await _summary(client, h, "week"))["status"] == "insufficient_data"


# ------------------------------------------------------------------ hand-computed summary

@pytest_asyncio.fixture
async def data(client):
    """Three workouts on exercises A and B, three weigh-ins and two eating days (8 distinct days of history)."""
    h = await _user(client)
    a, b = await _exercise_ids(client, h, 2)
    oil, rice = await _food(client, h, "Olive oil"), await _food(client, h, "White rice, cooked")
    await _weigh(client, h, 20, 85.0)
    await _weigh(client, h, 10, 83.5)
    await _weigh(client, h, 2, 82.0)
    await _train(client, h, 15, [(a, 5, 100, True), (a, 5, 100, True)])
    await _train(client, h, 8, [(a, 5, 105, True), (b, 8, 50, True)])
    await _train(client, h, 1, [(a, 3, 110, True), (a, 3, 200, False)])    # the failed set counts nowhere
    await _eat(client, h, 5, oil, 100)                                      # 884 kcal
    await _eat(client, h, 5, rice, 200, "dinner")                           # 260 kcal -> 1144 that day
    await _eat(client, h, 4, oil, 50)                                       # 442 kcal
    return h, a, b


async def test_month_summary_matches_the_hand_computed_values(client, data):
    h, a, b = data
    s = await _summary(client, h, "month")
    assert s["status"] == "ok" and s["period"] == "month"
    assert (s["from"], s["to"]) == (day(29).isoformat(), day().isoformat())            # the last 30 days incl. today
    assert s["weight_change_kg"] == -3.0                                                # 82.0 - 85.0
    assert s["total_workouts"] == 3 and s["avg_workouts_per_week"] == 0.7              # 3 / (30 / 7)
    assert s["tonnage_kg"] == 2255.0       # 2x5x100 + 5x105 + 8x50 + 3x110 = 1000 + 525 + 400 + 330
    assert s["avg_calories"] == 793.0                                                   # (1144 + 442) / 2 eating days
    assert s["workout_compliance_pct"] is None and s["diet_compliance_pct"] is None   # no active plans
    first_a, best_a = round(100 * (1 + 5 / 30), 2), round(105 * (1 + 5 / 30), 2)       # 116.67 and 122.5
    assert s["key_lifts"] == [
        {"exercise_id": a, "exercise_name": s["key_lifts"][0]["exercise_name"], "first_e1rm_kg": first_a,
         "best_e1rm_kg": best_a},
        {"exercise_id": b, "exercise_name": s["key_lifts"][1]["exercise_name"], "first_e1rm_kg": 63.33,
         "best_e1rm_kg": 63.33}]
    assert best_a == 122.5 and s["key_lifts"][0]["best_e1rm_kg"] == 122.5               # 105 x 5 beats 110 x 3 = 121.0


async def test_week_and_three_month_windows(client, data):
    h, a, _ = data
    week = await _summary(client, h, "week")
    assert (week["from"], week["to"]) == (day(6).isoformat(), day().isoformat())       # 7 days incl. today
    assert week["weight_change_kg"] is None                                             # one weigh-in (day 2) only
    assert week["total_workouts"] == 1 and week["avg_workouts_per_week"] == 1.0         # 1 / (7 / 7)
    assert week["tonnage_kg"] == 330.0                                                  # 3 x 110; the failed set is out
    assert week["avg_calories"] == 793.0                                                # days 5 and 4 are inside
    assert [(k["exercise_id"], k["first_e1rm_kg"], k["best_e1rm_kg"]) for k in week["key_lifts"]] == [(a, 121.0, 121.0)]
    quarter = await _summary(client, h, "3months")
    assert quarter["from"] == day(89).isoformat() and quarter["total_workouts"] == 3
    assert quarter["avg_workouts_per_week"] == 0.23                                     # 3 / (90 / 7)
    assert quarter["weight_change_kg"] == -3.0 and quarter["tonnage_kg"] == 2255.0


async def test_a_period_without_data_gives_null_metrics_but_status_ok(client, data):
    h, _, _ = data
    chicken = await _food(client, h, "Chicken breast, cooked")
    for offset in (30, 31, 32):  # extra history keeps the minimum-data rule satisfied for any window
        await _eat(client, h, offset, chicken, 100)
    empty = await _user(client)
    for offset in range(40, 47):
        await _weigh(client, empty, offset, 80)                                         # all older than a week
    s = await _summary(client, empty, "week")
    assert s["status"] == "ok" and s["weight_change_kg"] is None and s["total_workouts"] is None
    assert s["avg_workouts_per_week"] is None and s["avg_calories"] is None and s["tonnage_kg"] is None
    assert s["key_lifts"] == []


async def test_only_the_three_most_trained_exercises_are_key_lifts(client):
    h = await _user(client)
    ids = await _exercise_ids(client, h, 5)
    for offset in range(1, 8):
        await _weigh(client, h, offset, 80)
    # ids[0] in 3 workouts, ids[1] in 2, ids[2] and ids[3] in 1 (ids[2] with more sets), ids[4] only with 20 reps
    await _train(client, h, 2, [(ids[0], 5, 50, True), (ids[1], 5, 40, True), (ids[2], 5, 30, True),
                                (ids[2], 5, 30, True), (ids[3], 5, 20, True), (ids[4], 20, 10, True)])
    await _train(client, h, 3, [(ids[0], 5, 55, True), (ids[1], 5, 45, True)])
    await _train(client, h, 4, [(ids[0], 5, 60, True)])
    lifts = (await _summary(client, h, "month"))["key_lifts"]
    assert [k["exercise_id"] for k in lifts] == [ids[0], ids[1], ids[2]]       # by workouts, then sets; 20 reps do not count
    assert lifts[0]["first_e1rm_kg"] == round(60 * (1 + 5 / 30), 2)             # the oldest set is the one on day 4
    assert lifts[0]["best_e1rm_kg"] == round(60 * (1 + 5 / 30), 2)


# ------------------------------------------------------------------ plan compliance (section 7)

async def test_workout_compliance_against_the_active_plan(client):
    h = await _user(client)
    ex = (await _exercise_ids(client, h, 1))[0]
    plan = (await client.post(f"{BASE}/training-plans/generate", headers=h,
                              json={"goal": "strength", "training_days": 4})).json()
    await client.post(f"{BASE}/training-plans/{plan['id']}/accept", headers=h,
                      json={"start_date": day(13).isoformat()})                    # the plan started 13 days ago
    for offset in (1, 3, 5, 10):
        await _train(client, h, offset, [(ex, 5, 50, True)])
    for offset in range(11, 15):
        await _weigh(client, h, offset, 80)
    week = await _summary(client, h, "week")
    assert week["workout_compliance_pct"] == 75.0         # 3 workouts / (4 sessions x 7 days / 7) in the last 7 days
    month = await _summary(client, h, "month")
    assert month["workout_compliance_pct"] == 50.0        # 4 workouts / (4 x 14 plan days / 7 = 8): only plan days count
    chart = (await client.get(f"{BASE}/analytics/charts/workout_compliance?period=month", headers=h)).json()
    assert chart["status"] == "ok" and chart["points"] and all(0 <= p["value"] <= 100 for p in chart["points"])


async def test_diet_compliance_against_the_active_diet_plan(client):
    h = await _user(client)
    oil = await _food(client, h, "Olive oil")
    diet = (await client.post(f"{BASE}/diet-plans/generate", json={"meals_per_day": 3}, headers=h)).json()
    await client.post(f"{BASE}/diet-plans/{diet['id']}/accept", headers=h, json={"start_date": day(3).isoformat()})
    target = diet["daily_calorie_target"]
    exact = round(target / 8.84)                                                    # olive oil: 884 kcal / 100 g
    await _eat(client, h, 3, oil, exact)                                           # day 1 of the plan: on target
    await _eat(client, h, 2, oil, round(exact / 2))                                # half the target: misses +-10 %
    await _eat(client, h, 1, oil, round(exact * 1.05))                             # 5 % over: inside the tolerance
    for offset in range(8, 13):                                                     # history before the plan
        await _weigh(client, h, offset, 80)
    week = await _summary(client, h, "week")
    assert week["diet_compliance_pct"] == 50.0       # days 3 and 1 of 4 plan days (today has no log and fails)
    assert week["workout_compliance_pct"] is None    # no training plan
    chart = (await client.get(f"{BASE}/analytics/charts/diet_compliance?period=week", headers=h)).json()
    assert chart["points"] and all(0 <= p["value"] <= 100 for p in chart["points"])


# ------------------------------------------------------------------ chart series

async def test_chart_series_follow_the_logged_data(client, data):
    h, a, b = data

    async def series(metric: str) -> list[tuple[str, float]]:
        r = await client.get(f"{BASE}/analytics/charts/{metric}?period=month", headers=h)
        assert r.status_code == 200 and r.json()["metric"] == metric and r.json()["period"] == "month"
        return [(p["date"], p["value"]) for p in r.json()["points"]]

    assert await series("weight") == [(day(20).isoformat(), 85.0), (day(10).isoformat(), 83.5),
                                      (day(2).isoformat(), 82.0)]
    assert await series("tonnage") == [(day(15).isoformat(), 1000.0), (day(8).isoformat(), 925.0),
                                       (day(1).isoformat(), 330.0)]
    assert await series("calories") == [(day(5).isoformat(), 1144.0), (day(4).isoformat(), 442.0)]
    weekly = await series("workouts_per_week")
    assert sum(v for _, v in weekly) == 3 and all(datetime.fromisoformat(d).date().weekday() == 0
                                                  or d == day(29).isoformat() for d, _ in weekly)
    assert await series("workout_compliance") == [] and await series("diet_compliance") == []   # no plans


async def test_users_only_see_their_own_data(client, data):
    other = await _user(client)
    s = await _summary(client, other, "month")
    assert s["status"] == "insufficient_data" and s["total_workouts"] is None


# ------------------------------------------------------------------ B-24: goal prediction

async def _weigh_series(client, h, points: dict[int, float]) -> None:
    for offset, weight in points.items():
        await _weigh(client, h, offset, weight)


async def _target(client, h, kg: float | None) -> None:
    profile = {**PROFILE, **({"target_weight_kg": kg} if kg is not None else {})}
    assert (await client.put(f"{BASE}/users/me/profile", json=profile, headers=h)).status_code == 200


async def _prediction(client, h) -> dict:
    r = await client.get(f"{BASE}/analytics/goal-prediction", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


async def test_a_regular_weight_loss_gives_a_date(client):
    h = await _user(client)
    await _target(client, h, 78)
    await _weigh_series(client, h, {21: 81.5, 14: 81.0, 7: 80.5, 0: 80.0})   # exactly -0.5 kg per week
    p = await _prediction(client, h)
    assert p["status"] == "ok" and p["slope_kg_per_week"] == -0.5 and p["r2"] == 1.0
    assert p["target_weight_kg"] == 78.0 and p["warnings"] == []
    assert p["estimated_date"] == (day() + timedelta(days=28)).isoformat()    # (78 - 80.0) / (-0.5 / 7) = 28 days


async def test_weigh_ins_older_than_28_days_are_ignored(client):
    h = await _user(client)
    await _target(client, h, 78)
    await _weigh_series(client, h, {60: 100.0, 40: 95.0, 21: 81.5, 14: 81.0, 7: 80.5, 0: 80.0})
    p = await _prediction(client, h)
    assert p["status"] == "ok" and p["slope_kg_per_week"] == -0.5 and p["r2"] == 1.0


async def test_the_goal_is_reached_when_within_half_a_kilo(client):
    h = await _user(client)
    await _target(client, h, 80.3)
    await _weigh_series(client, h, {21: 81.5, 14: 81.0, 7: 80.5, 0: 80.0})
    p = await _prediction(client, h)
    assert p["status"] == "goal_reached" and p["estimated_date"] is None and p["slope_kg_per_week"] == -0.5


async def test_moving_away_from_the_goal(client):
    h = await _user(client)
    await _target(client, h, 75)
    await _weigh_series(client, h, {21: 80.0, 14: 80.5, 7: 81.0, 0: 81.5})   # gaining while the target is lower
    p = await _prediction(client, h)
    assert p["status"] == "moving_away" and p["estimated_date"] is None and p["slope_kg_per_week"] == 0.5


async def test_a_flat_trend_is_no_progress(client):
    h = await _user(client)
    await _target(client, h, 75)
    await _weigh_series(client, h, {14: 80.0, 7: 80.0, 0: 80.0})
    p = await _prediction(client, h)
    assert p["status"] == "no_progress" and p["estimated_date"] is None and p["slope_kg_per_week"] == 0.0


async def test_not_enough_weigh_ins_or_no_target(client):
    h = await _user(client)
    await _target(client, h, 78)
    assert (await _prediction(client, h))["status"] == "insufficient_data"          # no weigh-ins at all
    await _weigh_series(client, h, {10: 81.0, 0: 80.0})
    assert (await _prediction(client, h))["status"] == "insufficient_data"          # two weigh-ins
    await _weigh_series(client, h, {9: 80.8})                                        # three, but within 9 days: 9 >= 7
    assert (await _prediction(client, h))["status"] == "ok"
    short = await _user(client)
    await _target(client, short, 78)
    await _weigh_series(client, short, {6: 81.0, 3: 80.5, 0: 80.0})                  # three weigh-ins spanning 6 days
    assert (await _prediction(client, short))["status"] == "insufficient_data"
    no_target = await _user(client)
    await _weigh_series(client, no_target, {21: 81.5, 14: 81.0, 7: 80.5, 0: 80.0})
    p = await _prediction(client, no_target)
    assert p["status"] == "no_target" and p["target_weight_kg"] is None and p["warnings"] == []
    no_profile = await _user(client, None)
    assert (await _prediction(client, no_profile))["status"] == "no_target"


async def test_irregular_data_gets_warnings_and_still_a_date(client):
    h = await _user(client)
    await _target(client, h, 75)
    # scattered weigh-ins (low fit), a 20-day gap (gaps) and a plan that was not trained (low training compliance)
    await _weigh_series(client, h, {27: 84.0, 26: 79.0, 25: 85.0, 5: 80.0, 0: 81.0})
    plan = (await client.post(f"{BASE}/training-plans/generate", headers=h,
                              json={"goal": "strength", "training_days": 4})).json()
    await client.post(f"{BASE}/training-plans/{plan['id']}/accept", headers=h, json={"start_date": day(27).isoformat()})
    p = await _prediction(client, h)
    assert p["status"] in ("ok", "no_progress", "moving_away")
    assert {"low_fit", "gaps", "low_training_compliance"} <= set(p["warnings"])
    assert p["r2"] is not None and p["r2"] < 0.5


async def test_each_user_gets_their_own_prediction(client):
    a, b = await _user(client), await _user(client)
    await _target(client, a, 78)
    await _weigh_series(client, a, {21: 81.5, 14: 81.0, 7: 80.5, 0: 80.0})
    assert (await _prediction(client, a))["status"] == "ok"
    assert (await _prediction(client, b))["status"] == "no_target"
