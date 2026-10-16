"""B-11: generate, read, accept and regenerate training plans against a real, seeded PostgreSQL."""
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
from app.domain.constants import SPLITS
from app.main import create_app
from tests.support import NO_STORES

BASE = "/api/v1"
PROFILE = {"age": 30, "sex": "male", "weight_kg": 80, "height_cm": 180, "activity_level_pal": 1.55,
           "goal": "muscle_gain", "experience_level": "beginner", "equipment": "gym"}
GEN = {"goal": "muscle_gain", "training_days": 4}


@pytest_asyncio.fixture
async def client(seeded_engine):
    url = seeded_engine.url.render_as_string(hide_password=False)
    settings = Settings(jwt_secret="test-secret-" + "x" * 32, bcrypt_rounds=4, auth_rate_limit=10_000,
                        _env_file=None, **{**NO_STORES, "database_url": url})
    app = create_app(settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        yield http
    await app.state.db_engine.dispose()


async def _user(client, profile: dict | None = None, timezone: str | None = None) -> dict:
    email = f"{uuid.uuid4().hex[:10]}@example.com"
    body = {"email": email, "password": "Secret123", **({"timezone": timezone} if timezone else {})}
    pair = (await client.post(f"{BASE}/auth/register", json=body)).json()
    headers = {"Authorization": f"Bearer {pair['access_token']}"}
    if profile is not None:
        assert (await client.put(f"{BASE}/users/me/profile", json=profile, headers=headers)).status_code == 200
    return headers


async def _ids(client, h, path: str) -> dict[str, int]:
    return {x["name"]: x["id"] for x in (await client.get(f"{BASE}{path}", headers=h)).json()}


def _names(plan: dict) -> list[str]:
    return [e["exercise"]["name"] for s in plan["sessions"] for e in s["exercises"]]


# ------------------------------------------------------------------ generate

async def test_requires_authentication(client):
    for method, path in [("post", "/training-plans/generate"), ("get", "/training-plans/active"),
                         ("get", "/training-plans/draft"), ("post", "/training-plans/1/accept")]:
        assert (await client.request(method, BASE + path, json={})).status_code == 401, path


async def test_generate_needs_a_profile(client):
    h = await _user(client)
    r = await client.post(f"{BASE}/training-plans/generate", json=GEN, headers=h)
    assert r.status_code == 404 and r.json()["code"] == "not_found"


async def test_generated_draft_follows_the_specification(client):
    h = await _user(client, PROFILE)
    r = await client.post(f"{BASE}/training-plans/generate", json=GEN, headers=h)
    assert r.status_code == 201, r.text
    plan = r.json()
    assert plan["status"] == "draft" and plan["goal"] == "muscle_gain" and plan["num_training_days"] == 4
    assert plan["experience_level"] == "beginner" and plan["equipment"] == "gym"  # from the profile
    assert plan["start_date"] is None and plan["end_date"] is None and plan["skipped_groups"] == []
    assert plan["name"] == "Muscle gain, 4 days per week" and plan["generated_at"]

    # algorithms.md 4.5: 4 days = Upper A, Lower A, Upper B, Lower B on mon, tue, thu, fri
    assert [(s["name"], s["weekday"]) for s in plan["sessions"]] == [(n, w) for n, _k, w in SPLITS[4]]
    assert [s["session_order"] for s in plan["sessions"]] == [1, 2, 3, 4]
    for session in plan["sessions"]:
        assert session["estimated_duration_min"] % 5 == 0 and session["estimated_duration_min"] > 0
        assert [e["position"] for e in session["exercises"]] == list(range(1, len(session["exercises"]) + 1))
        assert len(session["exercises"]) >= 5  # beginner: 5 exercises per session or one per group
        for e in session["exercises"]:
            assert e["planned_weight_kg"] is None and e["original_exercise_id"] is None
            assert e["exercise"]["difficulty_level"] == "beginner"  # beginner level only
            # 4.7: muscle_gain compound 4x8 / 120 s, isolation 3x12 / 75 s; beginners get one set fewer
            compound = e["exercise"]["is_compound"]
            assert (e["planned_sets"], e["planned_reps"], e["rest_seconds"]) == ((3, 8, 120) if compound else (2, 12, 75))
    assert {e["exercise"]["main_muscle_group"]["name"] for s in plan["sessions"] for e in s["exercises"]} == {
        "chest", "back", "shoulders", "biceps", "triceps", "quadriceps", "hamstrings", "glutes", "calves", "core"}
    assert (await client.get(f"{BASE}/training-plans/draft", headers=h)).json() == plan


async def test_request_overrides_level_and_equipment_of_the_profile(client):
    h = await _user(client, PROFILE)
    plan = (await client.post(f"{BASE}/training-plans/generate", headers=h, json={
        **GEN, "goal": "strength", "training_days": 3, "experience_level": "advanced", "equipment": "none"})).json()
    assert plan["goal"] == "strength" and plan["experience_level"] == "advanced" and plan["equipment"] == "none"
    equipment = {e["exercise"]["equipment"] for s in plan["sessions"] for e in s["exercises"]}
    assert equipment == {"none"}
    assert [s["name"] for s in plan["sessions"]] == ["Full Body A", "Full Body B", "Full Body C"]


async def test_invalid_requests_give_field_errors(client):
    h = await _user(client, PROFILE)
    for body, field in [({**GEN, "training_days": 0}, "training_days"), ({**GEN, "training_days": 8}, "training_days"),
                        ({**GEN, "goal": "fly"}, "goal"), ({"goal": "strength"}, "training_days"),
                        ({**GEN, "equipment": "boat"}, "equipment"), ({**GEN, "experience_level": "god"},
                                                                       "experience_level")]:
        r = await client.post(f"{BASE}/training-plans/generate", json=body, headers=h)
        assert r.status_code == 422 and r.json()["details"][0]["field"] == field, body


async def test_regenerating_replaces_the_draft(client, seeded_engine):
    h = await _user(client, PROFILE)
    first = (await client.post(f"{BASE}/training-plans/generate", json=GEN, headers=h)).json()
    second = (await client.post(f"{BASE}/training-plans/generate", headers=h,
                                json={**GEN, "goal": "strength", "training_days": 5})).json()
    assert second["id"] != first["id"] and second["goal"] == "strength" and len(second["sessions"]) == 5
    assert (await client.get(f"{BASE}/training-plans/draft", headers=h)).json()["id"] == second["id"]
    assert (await client.post(f"{BASE}/training-plans/{first['id']}/accept", headers=h)).status_code == 404  # gone
    with seeded_engine.connect() as c:
        assert c.execute(text("select count(*) from training_plan where id = :i"), {"i": first["id"]}).scalar_one() == 0
        assert c.execute(text("select count(*) from training_session where training_plan_id = :i"),
                         {"i": first["id"]}).scalar_one() == 0  # cascade


async def test_concurrent_generation_leaves_exactly_one_draft(client, seeded_engine):
    h = await _user(client, PROFILE)
    results = await asyncio.gather(*[client.post(f"{BASE}/training-plans/generate", headers=h,
                                                 json={**GEN, "training_days": d}) for d in (2, 3, 4, 5, 6)])
    assert all(r.status_code == 201 for r in results), [r.status_code for r in results]
    draft = (await client.get(f"{BASE}/training-plans/draft", headers=h)).json()
    with seeded_engine.connect() as c:
        n = c.execute(text("select count(*) from training_plan where status = 'draft' and user_id ="
                           " (select user_id from training_plan where id = :i)"), {"i": draft["id"]}).scalar_one()
    assert n == 1


# ------------------------------------------------------------------ FR-P3: not enough exercises

async def test_insufficient_exercises_gives_suggestions_and_keeps_the_old_draft(client, seeded_engine):
    h = await _user(client, {**PROFILE, "equipment": "none"})
    ok = (await client.post(f"{BASE}/training-plans/generate", json={"goal": "strength", "training_days": 3},
                            headers=h)).json()
    # make the library lack calves exercises for a bodyweight user, then put it back
    with seeded_engine.begin() as c:
        c.execute(text("update exercise set equipment = 'gym' where main_muscle_group_id ="
                       " (select id from muscle_group where name = 'calves')"))
    try:
        r = await client.post(f"{BASE}/training-plans/generate", json=GEN, headers=h)  # muscle_gain needs calves
        assert r.status_code == 422, r.text
        body = r.json()
        assert body["code"] == "insufficient_exercises"
        details = {d["code"]: d for d in body["details"]}
        assert details["no_eligible_exercise"]["muscle_group"] == "calves"
        assert details["change_equipment"]["equipment"] == "gym"
        assert "strength" in details["change_goal"]["goals"] and "muscle_gain" not in details["change_goal"]["goals"]
        assert (await client.get(f"{BASE}/training-plans/draft", headers=h)).json()["id"] == ok["id"]  # nothing stored
    finally:
        with seeded_engine.begin() as c:
            c.execute(text(
                "update exercise set equipment = v.equipment::equipment_t from (values"
                " ('Bodyweight calf raise','none'),('Single-leg calf raise','none'),('Step calf raise','none'),"
                " ('Dumbbell standing calf raise','home'),('Single-leg dumbbell calf raise','home'),"
                " ('Standing calf raise machine','gym'),('Seated calf raise machine','gym'),"
                " ('Leg press calf raise','gym'),('Donkey calf raise','gym')) as v(name, equipment)"
                " where exercise.name = v.name"))


# ------------------------------------------------------------------ injuries (FR-P2)

async def test_blocked_group_is_skipped_and_reported(client):
    h = await _user(client, PROFILE)
    groups, types = await _ids(client, h, "/muscle-groups"), await _ids(client, h, "/injury-types")
    await client.post(f"{BASE}/users/me/injuries", headers=h, json={
        "injury_type_id": types["rib or chest wall strain"], "affected_muscle_group_id": groups["chest"],
        "severity": "moderate", "start_date": "2026-09-01"})
    plan = (await client.post(f"{BASE}/training-plans/generate", json=GEN, headers=h)).json()
    assert plan["skipped_groups"] == [{"muscle_group": {"id": groups["chest"], "name": "chest"}, "reason": "injury"}]
    assert "chest" not in {e["exercise"]["main_muscle_group"]["name"] for s in plan["sessions"] for e in s["exercises"]}
    assert (await client.get(f"{BASE}/training-plans/draft", headers=h)).json()["skipped_groups"] == plan["skipped_groups"]


async def test_plan_never_contains_exercises_excluded_by_the_injury(client):
    h = await _user(client, {**PROFILE, "experience_level": "advanced"})
    groups, types = await _ids(client, h, "/muscle-groups"), await _ids(client, h, "/injury-types")
    await client.post(f"{BASE}/users/me/injuries", headers=h, json={
        "injury_type_id": types["lower back strain"], "affected_muscle_group_id": groups["back"],
        "severity": "moderate", "start_date": "2026-09-01"})
    excluded = {"Conventional deadlift", "Barbell Romanian deadlift", "Bodyweight good morning",
                "Barbell bent-over row", "T-bar row", "Barbell back squat", "Barbell front squat", "Superman",
                "V-up", "Hollow body hold", "Ab wheel rollout", "Dumbbell Russian twist", "Hanging leg raise",
                "Lying leg raise"}
    for goal, days in (("muscle_gain", 4), ("strength", 6), ("weight_loss", 3)):
        plan = (await client.post(f"{BASE}/training-plans/generate", json={"goal": goal, "training_days": days},
                                  headers=h)).json()
        assert not excluded & set(_names(plan)), (goal, excluded & set(_names(plan)))
        assert "back" not in {e["exercise"]["main_muscle_group"]["name"] for s in plan["sessions"]
                              for e in s["exercises"]}


async def test_healed_injury_no_longer_restricts_the_plan(client):
    h = await _user(client, PROFILE)
    groups, types = await _ids(client, h, "/muscle-groups"), await _ids(client, h, "/injury-types")
    injury = (await client.post(f"{BASE}/users/me/injuries", headers=h, json={
        "injury_type_id": types["rib or chest wall strain"], "affected_muscle_group_id": groups["chest"],
        "severity": "mild", "start_date": "2026-09-01"})).json()
    assert (await client.post(f"{BASE}/training-plans/generate", json=GEN, headers=h)).json()["skipped_groups"]
    await client.patch(f"{BASE}/users/me/injuries/{injury['id']}", json={"is_active": False}, headers=h)
    assert (await client.post(f"{BASE}/training-plans/generate", json=GEN, headers=h)).json()["skipped_groups"] == []


# ------------------------------------------------------------------ accept (FR-P7)

async def test_accept_activates_the_draft_and_archives_the_previous_plan(client, seeded_engine):
    h = await _user(client, PROFILE, timezone="Pacific/Kiritimati")  # UTC+14: "today" differs from UTC for hours
    assert (await client.get(f"{BASE}/training-plans/active", headers=h)).status_code == 404
    first = (await client.post(f"{BASE}/training-plans/generate", json=GEN, headers=h)).json()
    accepted = (await client.post(f"{BASE}/training-plans/{first['id']}/accept", headers=h))
    assert accepted.status_code == 200, accepted.text
    plan = accepted.json()
    today = datetime.now(ZoneInfo("Pacific/Kiritimati")).date()
    assert plan["status"] == "active" and plan["start_date"] == today.isoformat()
    assert plan["end_date"] == (today + timedelta(days=56)).isoformat()  # 8 weeks
    assert (await client.get(f"{BASE}/training-plans/active", headers=h)).json() == plan
    assert (await client.get(f"{BASE}/training-plans/draft", headers=h)).status_code == 404  # draft became active

    # a second plan with an explicit start date replaces it; the first is archived, not deleted
    second = (await client.post(f"{BASE}/training-plans/generate", json={**GEN, "goal": "strength"}, headers=h)).json()
    assert (await client.get(f"{BASE}/training-plans/active", headers=h)).json()["id"] == first["id"]  # untouched
    accepted2 = (await client.post(f"{BASE}/training-plans/{second['id']}/accept", headers=h,
                                   json={"start_date": "2026-12-01"})).json()
    assert accepted2["start_date"] == "2026-12-01" and accepted2["end_date"] == "2027-01-26"
    assert (await client.get(f"{BASE}/training-plans/active", headers=h)).json()["id"] == second["id"]
    with seeded_engine.connect() as c:
        status = c.execute(text("select status::text from training_plan where id = :i"), {"i": first["id"]}).scalar_one()
    assert status == "archived"


async def test_only_a_draft_can_be_accepted(client):
    h = await _user(client, PROFILE)
    plan = (await client.post(f"{BASE}/training-plans/generate", json=GEN, headers=h)).json()
    assert (await client.post(f"{BASE}/training-plans/{plan['id']}/accept", headers=h)).status_code == 200
    again = await client.post(f"{BASE}/training-plans/{plan['id']}/accept", headers=h)
    assert again.status_code == 409 and again.json()["code"] == "conflict"
    assert (await client.post(f"{BASE}/training-plans/999999/accept", headers=h)).status_code == 404
    assert (await client.post(f"{BASE}/training-plans/0/accept", headers=h)).status_code == 422
    bad = await client.post(f"{BASE}/training-plans/{plan['id']}/accept", json={"start_date": "soon"}, headers=h)
    assert bad.status_code == 422 and bad.json()["details"][0]["field"] == "start_date"


async def test_a_user_cannot_see_or_accept_anothers_plan(client):
    a, b = await _user(client, PROFILE), await _user(client, PROFILE)
    plan = (await client.post(f"{BASE}/training-plans/generate", json=GEN, headers=a)).json()
    assert (await client.post(f"{BASE}/training-plans/{plan['id']}/accept", headers=b)).status_code == 404
    assert (await client.get(f"{BASE}/training-plans/draft", headers=b)).status_code == 404
    assert (await client.get(f"{BASE}/training-plans/draft", headers=a)).json()["id"] == plan["id"]  # still A's draft
    await client.post(f"{BASE}/training-plans/generate", json=GEN, headers=b)  # B's own draft does not touch A's
    assert (await client.get(f"{BASE}/training-plans/draft", headers=a)).json()["id"] == plan["id"]


# ------------------------------------------------------------------ NFR: 3 s

async def test_generation_answers_well_within_three_seconds(client):
    """NFR plan <= 3 s (95th percentile) on the seeded database."""
    h = await _user(client, PROFILE)
    durations = []
    for goal, days in [("muscle_gain", 4), ("strength", 6), ("weight_loss", 3), ("endurance", 7), ("maintenance", 5),
                       ("general_fitness", 2)] * 4:
        start = time.perf_counter()
        r = await client.post(f"{BASE}/training-plans/generate", json={"goal": goal, "training_days": days}, headers=h)
        durations.append(time.perf_counter() - start)
        assert r.status_code == 201
    durations.sort()
    assert durations[int(len(durations) * 0.95) - 1] < 3.0, durations[-3:]


async def test_optional_fields_are_absent_or_valid_but_never_null(client):
    """The contract's optional fields are not nullable: an explicit null is a 422, an absent field is fine."""
    h = await _user(client, PROFILE)
    for field in ("experience_level", "equipment"):
        r = await client.post(f"{BASE}/training-plans/generate", json={**GEN, field: None}, headers=h)
        assert r.status_code == 422 and r.json()["details"][0]["field"] == field, field
    plan = (await client.post(f"{BASE}/training-plans/generate", json=GEN, headers=h)).json()
    r = await client.post(f"{BASE}/training-plans/{plan['id']}/accept", json={"start_date": None}, headers=h)
    assert r.status_code == 422 and r.json()["details"][0]["field"] == "start_date"
    assert (await client.post(f"{BASE}/training-plans/{plan['id']}/accept", json={}, headers=h)).status_code == 200
