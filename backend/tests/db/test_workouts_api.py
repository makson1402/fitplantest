"""B-15 / B-16: workout logging, personal records and plan adaptation against a real, seeded PostgreSQL."""
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
           "goal": "muscle_gain", "experience_level": "advanced", "equipment": "gym"}
GEN = {"goal": "muscle_gain", "training_days": 4}
UPPER = {"chest", "back", "shoulders", "biceps", "triceps"}
LOWER = {"quadriceps", "hamstrings", "glutes", "calves"}


def today() -> datetime.date:
    return datetime.now(UTC).date()


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


async def _active_plan(client, h, body: dict | None = None, accept: bool = True) -> dict:
    plan = (await client.post(f"{BASE}/training-plans/generate", json=body or GEN, headers=h)).json()
    if accept:
        plan = (await client.post(f"{BASE}/training-plans/{plan['id']}/accept", headers=h)).json()
    return plan


def _pick(plan: dict, groups: set[str], bodyweight: bool = False) -> tuple[dict, dict]:
    for session in plan["sessions"]:
        for e in session["exercises"]:
            ex = e["exercise"]
            if ex["main_muscle_group"]["name"] in groups and ex["is_bodyweight"] == bodyweight:
                return session, e
    raise AssertionError((groups, bodyweight))


async def _plan_values(client, h, se_id: int) -> tuple:
    plan = (await client.get(f"{BASE}/training-plans/active", headers=h)).json()
    e = next(x for s in plan["sessions"] for x in s["exercises"] if x["id"] == se_id)
    return e["planned_sets"], e["planned_reps"], e["planned_weight_kg"]


async def _prescribe(client, h, se_id: int, sets: int, reps: int, weight: float | None) -> None:
    r = await client.patch(f"{BASE}/session-exercises/{se_id}", headers=h,
                           json={"planned_sets": sets, "planned_reps": reps, "planned_weight_kg": weight})
    assert r.status_code == 200, r.text


def _sets(planned: dict, n: int = 3, reps: int = 10, weight: float = 60, rpe: int | None = None,
          not_completed: tuple[int, ...] = ()) -> list[dict]:
    return [{"exercise_id": planned["exercise"]["id"], "session_exercise_id": planned["id"], "set_number": i,
             "reps": reps, "weight_kg": weight, "rpe": rpe, "completed": i not in not_completed}
            for i in range(1, n + 1)]


def _free(sets: list[dict]) -> list[dict]:
    """The same sets not tied to a planned exercise (a workout without a training session)."""
    return [{**x, "session_exercise_id": None} for x in sets]


def _body(session: dict | None, sets: list[dict], overall_rpe: int | None = None, performed_on=None, **extra) -> dict:
    return {"training_session_id": session["id"] if session else None,
            "performed_on": (performed_on or today()).isoformat(), "overall_rpe": overall_rpe, "sets": sets, **extra}


async def _log(client, h, body: dict) -> dict:
    r = await client.post(f"{BASE}/workouts", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


async def _scenario(client, groups: set[str], planned_weight: float | None = 60, sets: int = 3, reps: int = 10,
                    bodyweight: bool = False, profile: dict = PROFILE):
    h = await _user(client, profile)
    plan = await _active_plan(client, h)
    session, planned = _pick(plan, groups, bodyweight)
    await _prescribe(client, h, planned["id"], sets, reps, planned_weight)
    return h, plan, session, planned


# ------------------------------------------------------------------ authentication

async def test_every_route_requires_a_token(client):
    for method, path in [("get", "/sessions/next"), ("post", "/workouts"), ("get", "/workouts"),
                         ("get", "/workouts/1"), ("put", "/workouts/1"), ("delete", "/workouts/1"),
                         ("get", "/personal-records")]:
        assert (await client.request(method, BASE + path)).status_code == 401, (method, path)


# ------------------------------------------------------------------ B-16: the worked examples of algorithms.md 6

async def test_example_a_progression_for_an_upper_body_exercise(client):
    h, _, session, planned = await _scenario(client, UPPER, 60)
    result = await _log(client, h, _body(session, _sets(planned, weight=60, rpe=6)))
    [adj] = result["adjustments"]
    assert (adj["reason"], adj["new_sets"], adj["new_reps"], adj["new_weight_kg"]) == ("progression", 3, 10, 62.5)
    assert (adj["old_sets"], adj["old_reps"], adj["old_weight_kg"]) == (3, 10, 60.0)
    assert adj["session_exercise_id"] == planned["id"] and adj["exercise_name"] == planned["exercise"]["name"]
    assert await _plan_values(client, h, planned["id"]) == (3, 10, 62.5)


async def test_example_b_progression_is_five_kilos_for_lower_body(client):
    h, _, session, planned = await _scenario(client, LOWER, 100)
    result = await _log(client, h, _body(session, _sets(planned, weight=100, rpe=7)))
    [adj] = result["adjustments"]
    assert (adj["reason"], adj["new_sets"], adj["new_reps"], adj["new_weight_kg"]) == ("progression", 3, 10, 105.0)
    assert await _plan_values(client, h, planned["id"]) == (3, 10, 105.0)


async def test_example_c_high_overall_rpe_reduces_the_load(client):
    h, _, session, planned = await _scenario(client, UPPER, 60)
    result = await _log(client, h, _body(session, _sets(planned, weight=60), overall_rpe=9))
    [adj] = result["adjustments"]
    assert (adj["reason"], adj["new_sets"], adj["new_reps"], adj["new_weight_kg"]) == ("reduce_high_rpe", 3, 10, 55.0)
    assert await _plan_values(client, h, planned["id"]) == (3, 10, 55.0)


async def test_example_d_an_incomplete_set_reduces_the_load(client):
    h, _, session, planned = await _scenario(client, UPPER, 60)
    result = await _log(client, h, _body(session, _sets(planned, weight=60, not_completed=(3,)), overall_rpe=8))
    [adj] = result["adjustments"]
    assert (adj["reason"], adj["new_sets"], adj["new_reps"], adj["new_weight_kg"]) == (
        "reduce_incomplete_set", 3, 10, 55.0)


async def test_example_e_no_signal_changes_nothing(client):
    h, plan, session, planned = await _scenario(client, UPPER, 60)
    result = await _log(client, h, _body(session, _sets(planned, weight=60), overall_rpe=8))
    assert result["adjustments"] == []
    assert await _plan_values(client, h, planned["id"]) == (3, 10, 60.0)


# ------------------------------------------------------------------ B-16: FR-A4, no explicit signal = no change

async def test_a_plan_never_changes_without_an_explicit_signal(client, seeded_engine):
    """Whatever is logged without a reduce or a reserve signal leaves the whole plan and the adjustments untouched."""
    h, plan, session, planned = await _scenario(client, UPPER, 60)
    before = (await client.get(f"{BASE}/training-plans/active", headers=h)).json()
    quiet = [
        _body(session, _sets(planned, weight=60), overall_rpe=8),                     # moderate effort
        _body(session, _sets(planned, weight=60), overall_rpe=None),                  # no effort data at all
        _body(session, _sets(planned, weight=60, reps=9, rpe=5)),                     # reps short of the plan
        _body(session, _sets(planned, n=2, weight=60, rpe=5)),                        # fewer sets than planned
        _body(session, _sets(planned, weight=60, rpe=8)),                             # a set RPE above the reserve limit
        _body(None, _free(_sets(planned, weight=60)), overall_rpe=10),                # not tied to a session
        _body(None, _free(_sets(planned, weight=60, not_completed=(1, 2))), overall_rpe=10),
    ]
    for body in quiet:
        assert (await _log(client, h, body))["adjustments"] == [], body
    assert (await client.get(f"{BASE}/training-plans/active", headers=h)).json() == before
    with seeded_engine.connect() as c:
        n = c.execute(text("select count(*) from plan_adjustment where session_exercise_id = :i"),
                      {"i": planned["id"]}).scalar_one()
    assert n == 0


async def test_reduce_signal_only_touches_the_logged_exercises(client):
    h = await _user(client)
    plan = await _active_plan(client, h)
    session, planned = _pick(plan, UPPER, False)
    others = [e for e in session["exercises"] if e["id"] != planned["id"]]
    await _prescribe(client, h, planned["id"], 3, 10, 60)
    for e in others:
        await _prescribe(client, h, e["id"], 3, 10, 40)
    result = await _log(client, h, _body(session, _sets(planned, weight=60), overall_rpe=10))  # RPE 10, one exercise
    assert [a["session_exercise_id"] for a in result["adjustments"]] == [planned["id"]]
    for e in others:
        assert await _plan_values(client, h, e["id"]) == (3, 10, 40.0)  # not logged: untouched


async def test_an_incomplete_set_only_reduces_its_own_exercise(client):
    h = await _user(client)
    plan = await _active_plan(client, h)
    session = next(s for s in plan["sessions"] if sum(not e["exercise"]["is_bodyweight"] for e in s["exercises"]) >= 2)
    first, second = [e for e in session["exercises"] if not e["exercise"]["is_bodyweight"]][:2]
    for e in (first, second):
        await _prescribe(client, h, e["id"], 3, 10, 50)
    sets = _sets(first, weight=50, not_completed=(2,)) + _sets(second, weight=50, rpe=8)
    result = await _log(client, h, _body(session, sets, overall_rpe=8))
    assert [(a["session_exercise_id"], a["reason"]) for a in result["adjustments"]] == [
        (first["id"], "reduce_incomplete_set")]
    assert await _plan_values(client, h, second["id"]) == (3, 10, 50.0)


async def test_baseline_weight_after_the_first_workout(client):
    h, _, session, planned = await _scenario(client, UPPER, None)  # a fresh plan knows no weight
    assert planned["planned_weight_kg"] is None
    result = await _log(client, h, _body(session, _sets(planned, weight=61, rpe=6)))
    [adj] = result["adjustments"]
    assert (adj["reason"], adj["old_weight_kg"], adj["new_weight_kg"]) == ("baseline", None, 60.0)  # nearest 2.5
    assert await _plan_values(client, h, planned["id"]) == (3, 10, 60.0)  # nothing else happens in that step


async def test_baseline_after_a_reduce_signal_starts_lower(client):
    h, _, session, planned = await _scenario(client, UPPER, None)
    result = await _log(client, h, _body(session, _sets(planned, weight=100), overall_rpe=9))
    assert result["adjustments"][0]["new_weight_kg"] == 90.0 and result["adjustments"][0]["reason"] == "baseline"


async def test_sets_without_a_weight_give_no_baseline(client):
    h, _, session, planned = await _scenario(client, UPPER, None)
    result = await _log(client, h, _body(session, _sets(planned, weight=0)))
    assert result["adjustments"] == []
    assert (await _plan_values(client, h, planned["id"]))[2] is None


async def test_bodyweight_exercises_lose_a_set_or_gain_a_rep(client):
    h, _, session, planned = await _scenario(client, UPPER | LOWER | {"core"}, None, 4, 10, True,
                                             {**PROFILE, "equipment": "none"})
    assert planned["exercise"]["is_bodyweight"]
    reduced = await _log(client, h, _body(session, _sets(planned, n=4, weight=0), overall_rpe=9))
    assert [(a["reason"], a["new_sets"], a["new_reps"]) for a in reduced["adjustments"]] == [
        ("reduce_high_rpe", 3, 10)]
    grown = await _log(client, h, _body(session, _sets(planned, n=3, reps=10, weight=0, rpe=6)))
    assert [(a["reason"], a["new_sets"], a["new_reps"]) for a in grown["adjustments"]] == [("progression", 3, 11)]
    assert await _plan_values(client, h, planned["id"]) == (3, 11, None)


async def test_a_reduce_signal_that_changes_nothing_is_not_recorded(client, seeded_engine):
    h, _, session, planned = await _scenario(client, UPPER | LOWER | {"core"}, None, 2, 10, True,
                                             {**PROFILE, "equipment": "none"})
    result = await _log(client, h, _body(session, _sets(planned, n=2, weight=0), overall_rpe=10))  # already 2 sets
    assert result["adjustments"] == []
    with seeded_engine.connect() as c:
        assert c.execute(text("select count(*) from plan_adjustment where session_exercise_id = :i"),
                         {"i": planned["id"]}).scalar_one() == 0


async def test_adaptation_also_applies_to_a_draft_but_not_to_an_archived_plan(client):
    h = await _user(client)
    draft = await _active_plan(client, h, accept=False)
    session, planned = _pick(draft, UPPER, False)
    await _prescribe_any(client, h, planned["id"], 60)
    assert (await _log(client, h, _body(session, _sets(planned, weight=60), overall_rpe=9)))["adjustments"]

    old = await _active_plan(client, h)
    old_session, old_planned = _pick(old, UPPER, False)
    await _prescribe(client, h, old_planned["id"], 3, 10, 60)
    await _active_plan(client, h)  # a newer accepted plan archives `old`
    result = await _log(client, h, _body(old_session, _sets(old_planned, weight=60), overall_rpe=10))
    assert result["adjustments"] == []  # history is not adapted, but the workout itself is stored
    assert result["workout"]["training_session_id"] == old_session["id"]


async def _prescribe_any(client, h, se_id: int, weight: float) -> None:
    await _prescribe(client, h, se_id, 3, 10, weight)


async def test_logged_sets_map_to_planned_exercises_by_id_or_by_exercise(client):
    h = await _user(client)
    plan = await _active_plan(client, h)
    session, planned = _pick(plan, UPPER, False)
    await _prescribe(client, h, planned["id"], 3, 10, 60)
    by_exercise = [{**x, "session_exercise_id": None} for x in _sets(planned, weight=60, rpe=6)]
    result = await _log(client, h, _body(session, by_exercise))
    assert [a["reason"] for a in result["adjustments"]] == ["progression"]  # matched through the exercise id

    # an exercise done instead of the planned one: the explicit session_exercise_id decides which prescription adapts
    alternatives = (await client.get(f"{BASE}/exercises/{planned['exercise']['id']}/alternatives", headers=h)).json()
    instead = [{**x, "exercise_id": alternatives[0]["id"]} for x in _sets(planned, weight=62.5, not_completed=(3,))]
    again = await _log(client, h, _body(session, instead))
    assert [(a["session_exercise_id"], a["reason"]) for a in again["adjustments"]] == [
        (planned["id"], "reduce_incomplete_set")]


# ------------------------------------------------------------------ B-15: personal records

async def test_personal_records_are_stored_only_for_real_improvements(client):
    h, _, session, planned = await _scenario(client, UPPER, 60)
    ex = planned["exercise"]
    first = await _log(client, h, _body(session, _sets(planned, n=2, reps=5, weight=80)))
    [pr] = first["new_personal_records"]
    assert pr["exercise_id"] == ex["id"] and pr["exercise_name"] == ex["name"]
    assert (pr["max_weight_kg"], pr["max_reps"], pr["achieved_on"]) == (80.0, 5, today().isoformat())
    assert pr["estimated_1rm_kg"] == pytest.approx(80 * (1 + 5 / 30), abs=0.01)  # Epley

    same = await _log(client, h, _body(session, _sets(planned, n=2, reps=5, weight=80)))
    assert same["new_personal_records"] == []                                    # equal is not an improvement
    lower = await _log(client, h, _body(session, _sets(planned, n=3, reps=5, weight=70)))
    assert lower["new_personal_records"] == []                                   # worse
    better = await _log(client, h, _body(session, _sets(planned, n=1, reps=3, weight=95)))
    assert [r["max_weight_kg"] for r in better["new_personal_records"]] == [95.0]
    current = (await client.get(f"{BASE}/personal-records", headers=h)).json()
    assert [(r["exercise_id"], r["max_weight_kg"], r["max_reps"]) for r in current] == [(ex["id"], 95.0, 3)]


async def test_one_rep_record_equals_the_weight_and_uncounted_sets_are_ignored(client):
    h, _, session, planned = await _scenario(client, UPPER, 60)
    single = await _log(client, h, _body(session, _sets(planned, n=1, reps=1, weight=100)))
    assert single["new_personal_records"][0]["estimated_1rm_kg"] == 100.0
    ignored = [  # not completed, zero weight, more than 12 reps: none of them can be a record
        *_sets(planned, n=1, reps=1, weight=200, not_completed=(1,)),
        {**_sets(planned, n=1, reps=5, weight=0)[0], "set_number": 2},
        {**_sets(planned, n=1, reps=15, weight=150)[0], "set_number": 3},
    ]
    assert (await _log(client, h, _body(session, ignored)))["new_personal_records"] == []
    assert [r["max_weight_kg"] for r in (await client.get(f"{BASE}/personal-records", headers=h)).json()] == [100.0]


async def test_records_are_per_user_and_per_exercise(client):
    a, b = await _user(client), await _user(client)
    plan = await _active_plan(client, a)
    session, planned = _pick(plan, UPPER, False)
    await _log(client, a, _body(session, _sets(planned, n=1, reps=5, weight=50)))
    assert (await client.get(f"{BASE}/personal-records", headers=b)).json() == []
    exercise = {"exercise_id": planned["exercise"]["id"], "set_number": 1, "reps": 5, "weight_kg": 40}
    other = await _log(client, b, _body(None, [exercise]))  # user b has their own, lower record
    assert other["new_personal_records"][0]["max_weight_kg"] == 40.0
    assert [r["max_weight_kg"] for r in (await client.get(f"{BASE}/personal-records", headers=a)).json()] == [50.0]


# ------------------------------------------------------------------ B-15: validation

async def test_values_outside_the_ranges_are_rejected_per_field(client):
    h, _, session, planned = await _scenario(client, UPPER, 60)
    ok = _sets(planned)
    bad_sets = [("overall_rpe", {"overall_rpe": 0}), ("overall_rpe", {"overall_rpe": 11}),
                ("sets.0.rpe", {"sets": [{**ok[0], "rpe": 0}]}), ("sets.0.rpe", {"sets": [{**ok[0], "rpe": 11}]}),
                ("sets.0.reps", {"sets": [{**ok[0], "reps": -1}]}), ("sets.0.reps", {"sets": [{**ok[0], "reps": 201}]}),
                ("sets.0.weight_kg", {"sets": [{**ok[0], "weight_kg": -1}]}),
                ("sets.0.set_number", {"sets": [{**ok[0], "set_number": 0}]}),
                ("sets", {"sets": []}), ("notes", {"notes": "x" * 1001}), ("performed_on", {"performed_on": "today"}),
                ("client_uuid", {"client_uuid": None}), ("client_uuid", {"client_uuid": "not-a-uuid"})]
    for field, change in bad_sets:
        r = await client.post(f"{BASE}/workouts", json={**_body(session, ok), **change}, headers=h)
        assert r.status_code == 422, (field, r.text)
        assert r.json()["details"][0]["field"] == field, (field, r.json()["details"])
    for rpe in (1, 10):  # the boundaries themselves are fine
        assert (await client.post(f"{BASE}/workouts", json=_body(session, ok, overall_rpe=rpe), headers=h)
                ).status_code == 201


async def test_business_rules_are_reported_with_the_field_path(client):
    h, plan, session, planned = await _scenario(client, UPPER, 60)
    other_session = next(s for s in plan["sessions"] if s["id"] != session["id"])
    foreign = other_session["exercises"][0]["id"]
    tomorrow, later = today() + timedelta(days=1), today() + timedelta(days=3)
    cases = {
        "sets.1.set_number": _body(session, _sets(planned, n=1) + _sets(planned, n=1)),                  # duplicate
        "sets.0.exercise_id": _body(session, [{**_sets(planned, n=1)[0], "exercise_id": 999999}]),         # unknown
        "training_session_id": _body({"id": 999999}, _sets(planned)),                                      # unknown
        "sets.0.session_exercise_id": _body(session, [{**_sets(planned, n=1)[0], "session_exercise_id": foreign}]),
        "performed_on": _body(session, _sets(planned), performed_on=later),                                # future
        "finished_at": _body(session, _sets(planned), started_at="2026-10-16T10:00:00Z",
                             finished_at="2026-10-16T09:00:00Z"),
    }
    for field, body in cases.items():
        r = await client.post(f"{BASE}/workouts", json=body, headers=h)
        assert r.status_code == 422 and r.json()["code"] == "validation_error", (field, r.text)
        assert field in {d["field"] for d in r.json()["details"]}, (field, r.json()["details"])
    assert (await client.post(f"{BASE}/workouts", json=_body(session, _sets(planned), performed_on=tomorrow),
                              headers=h)).status_code == 201  # tomorrow is tolerated (time zones)
    no_session = _body(None, [{**_sets(planned, n=1)[0], "session_exercise_id": planned["id"]}])
    assert (await client.post(f"{BASE}/workouts", json=no_session, headers=h)).status_code == 422


async def test_a_failed_request_stores_nothing(client):
    h, _, session, planned = await _scenario(client, UPPER, 60)
    await client.post(f"{BASE}/workouts", headers=h, json=_body(session, _sets(planned) + [
        {**_sets(planned, n=1)[0], "exercise_id": 999999, "set_number": 9}], overall_rpe=10))
    assert (await client.get(f"{BASE}/workouts", headers=h)).json()["total"] == 0
    assert await _plan_values(client, h, planned["id"]) == (3, 10, 60.0)


async def test_another_users_session_cannot_be_used(client):
    a, b = await _user(client), await _user(client)
    plan = await _active_plan(client, a)
    session, planned = _pick(plan, UPPER, False)
    r = await client.post(f"{BASE}/workouts", json=_body(session, _sets(planned), overall_rpe=10), headers=b)
    assert r.status_code == 422 and r.json()["details"][0]["field"] == "training_session_id"
    assert await _plan_values(client, a, planned["id"]) == (planned["planned_sets"], planned["planned_reps"],
                                                           planned["planned_weight_kg"])


# ------------------------------------------------------------------ B-15: idempotent retries

async def test_a_retry_with_the_same_client_uuid_returns_the_first_answer(client, seeded_engine):
    h, _, session, planned = await _scenario(client, UPPER, 60)
    body = _body(session, _sets(planned, weight=60, rpe=6), client_uuid=str(uuid.uuid4()))
    first = await _log(client, h, body)
    again = await _log(client, h, body)
    assert again == first and first["adjustments"] and first["new_personal_records"]
    assert (await client.get(f"{BASE}/workouts", headers=h)).json()["total"] == 1
    assert await _plan_values(client, h, planned["id"]) == (3, 10, 62.5)       # adapted once, not twice
    with seeded_engine.connect() as c:
        assert c.execute(text("select count(*) from plan_adjustment where workout_log_id = :i"),
                         {"i": first["workout"]["id"]}).scalar_one() == 1
    other = await _user(client)
    free = _body(None, _free(_sets(planned, n=1)), client_uuid=body["client_uuid"])
    assert (await client.post(f"{BASE}/workouts", json=free, headers=other)).status_code == 201  # another user: new


async def test_a_deleted_workouts_uuid_cannot_be_reused(client):
    h, _, session, planned = await _scenario(client, UPPER, 60)
    body = _body(session, _sets(planned), client_uuid=str(uuid.uuid4()))
    workout = (await _log(client, h, body))["workout"]
    assert (await client.delete(f"{BASE}/workouts/{workout['id']}", headers=h)).status_code == 204
    r = await client.post(f"{BASE}/workouts", json=body, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "conflict"


# ------------------------------------------------------------------ B-15: history

async def test_history_is_filtered_ordered_paginated_and_private(client):
    h, _, session, planned = await _scenario(client, UPPER, 60)
    days = [today() - timedelta(days=n) for n in (10, 5, 1, 0)]
    ids = {}
    for day in days:
        ids[day] = (await _log(client, h, _body(None, _free(_sets(planned, n=1)), performed_on=day)))["workout"]["id"]
    page = (await client.get(f"{BASE}/workouts", headers=h)).json()
    assert page["total"] == 4 and [w["id"] for w in page["items"]] == [ids[d] for d in reversed(days)]
    assert (page["limit"], page["offset"]) == (20, 0) and page["items"][0]["sets"]
    window = (await client.get(f"{BASE}/workouts?from={days[1]}&to={days[2]}", headers=h)).json()  # inclusive
    assert [w["id"] for w in window["items"]] == [ids[days[2]], ids[days[1]]] and window["total"] == 2
    second = (await client.get(f"{BASE}/workouts?limit=2&offset=2", headers=h)).json()
    assert [w["id"] for w in second["items"]] == [ids[days[1]], ids[days[0]]] and second["total"] == 4
    other = await _user(client)
    assert (await client.get(f"{BASE}/workouts", headers=other)).json()["total"] == 0
    assert (await client.get(f"{BASE}/workouts/{ids[days[0]]}", headers=other)).status_code == 404
    for query in ("limit=0", "limit=101", "offset=-1", "from=yesterday"):
        assert (await client.get(f"{BASE}/workouts?{query}", headers=h)).status_code == 422, query


async def test_replace_and_delete(client):
    h, _, session, planned = await _scenario(client, UPPER, 60)
    created = await _log(client, h, _body(session, _sets(planned, weight=60, rpe=6), client_uuid=str(uuid.uuid4())))
    workout = created["workout"]
    assert await _plan_values(client, h, planned["id"]) == (3, 10, 62.5)
    # replacing does not run the adaptation again, even with a signal in the new data
    replacement = _body(session, _sets(planned, n=2, reps=8, weight=70), overall_rpe=10, notes="edited",
                        client_uuid=workout["client_uuid"])
    r = await client.put(f"{BASE}/workouts/{workout['id']}", json=replacement, headers=h)
    assert r.status_code == 200, r.text
    updated = r.json()
    assert updated["id"] == workout["id"] and updated["notes"] == "edited" and updated["overall_rpe"] == 10
    assert [(x["set_number"], x["reps"], x["weight_kg"]) for x in updated["sets"]] == [(1, 8, 70.0), (2, 8, 70.0)]
    assert (await client.get(f"{BASE}/workouts/{workout['id']}", headers=h)).json() == updated
    assert await _plan_values(client, h, planned["id"]) == (3, 10, 62.5)
    # the client uuid cannot change; unknown and other users' workouts are 404
    changed = await client.put(f"{BASE}/workouts/{workout['id']}", headers=h,
                               json={**replacement, "client_uuid": str(uuid.uuid4())})
    assert changed.status_code == 422 and changed.json()["details"][0]["field"] == "client_uuid"
    assert (await client.put(f"{BASE}/workouts/999999", json=replacement, headers=h)).status_code == 404
    other = await _user(client)
    assert (await client.put(f"{BASE}/workouts/{workout['id']}", json=_body(None, _free(replacement["sets"])),
                             headers=other)).status_code == 404
    assert (await client.put(f"{BASE}/workouts/{workout['id']}", json={**replacement, "sets": []},
                             headers=h)).status_code == 422

    assert (await client.delete(f"{BASE}/workouts/{workout['id']}", headers=other)).status_code == 404
    assert (await client.delete(f"{BASE}/workouts/{workout['id']}", headers=h)).status_code == 204
    assert (await client.get(f"{BASE}/workouts/{workout['id']}", headers=h)).status_code == 404
    assert (await client.delete(f"{BASE}/workouts/{workout['id']}", headers=h)).status_code == 404
    assert (await client.get(f"{BASE}/workouts", headers=h)).json()["total"] == 0
    assert await _plan_values(client, h, planned["id"]) == (3, 10, 62.5)       # the adaptation stays
    assert (await client.get(f"{BASE}/personal-records", headers=h)).json()    # and so do the records


# ------------------------------------------------------------------ GET /sessions/next

async def test_no_active_plan_means_no_next_session(client):
    h = await _user(client)
    assert (await client.get(f"{BASE}/sessions/next", headers=h)).status_code == 404
    await _active_plan(client, h, accept=False)  # a draft is not enough
    assert (await client.get(f"{BASE}/sessions/next", headers=h)).status_code == 404


async def test_next_session_is_the_nearest_weekday_with_current_values(client):
    h, plan, session, planned = await _scenario(client, UPPER, 60)
    weekdays = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    nxt = (await client.get(f"{BASE}/sessions/next", headers=h)).json()
    scheduled = datetime.fromisoformat(nxt["scheduled_date"]).date()
    assert scheduled >= today() and weekdays[scheduled.weekday()] == nxt["session"]["weekday"]
    distance = {s["id"]: (weekdays.index(s["weekday"]) - today().weekday()) % 7 for s in plan["sessions"]}
    assert (scheduled - today()).days == min(distance.values()) and distance[nxt["session"]["id"]] == min(distance.values())

    await _log(client, h, _body(session, _sets(planned, weight=60, rpe=6)))                # adapts to 62.5
    active = (await client.get(f"{BASE}/training-plans/active", headers=h)).json()
    after = (await client.get(f"{BASE}/sessions/next", headers=h)).json()
    # whichever session is next, it is shown with the current (adapted) values of the active plan
    assert after["session"] == next(s for s in active["sessions"] if s["id"] == after["session"]["id"])
    adapted = next(e for s in active["sessions"] for e in s["exercises"] if e["id"] == planned["id"])
    assert adapted["planned_weight_kg"] == 62.5
    # the session that was just trained is the one that comes round again when it is the only one in reach
    one_day = await _active_plan(client, h, {"goal": "strength", "training_days": 1})
    shown = (await client.get(f"{BASE}/sessions/next", headers=h)).json()["session"]
    assert shown == one_day["sessions"][0]


async def test_a_session_already_trained_on_its_date_is_skipped(client, seeded_engine):
    h = await _user(client)
    plan = await _active_plan(client, h, {"goal": "strength", "training_days": 1}, accept=False)
    session = plan["sessions"][0]
    weekday = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[today().weekday()]
    with seeded_engine.begin() as c:  # make the only session fall on today
        c.execute(text("update training_session set weekday = :w where id = :i"), {"w": weekday, "i": session["id"]})
    await client.post(f"{BASE}/training-plans/{plan['id']}/accept", headers=h, json={"start_date": today().isoformat()})
    nxt = (await client.get(f"{BASE}/sessions/next", headers=h)).json()
    assert nxt["scheduled_date"] == today().isoformat() and nxt["session"]["id"] == session["id"]
    exercise = nxt["session"]["exercises"][0]
    await _log(client, h, _body(session, _sets(exercise, n=1, weight=20)))
    nxt = (await client.get(f"{BASE}/sessions/next", headers=h)).json()
    assert nxt["scheduled_date"] == (today() + timedelta(days=7)).isoformat()                 # done today, next week


async def test_next_session_respects_the_plan_dates(client):
    h = await _user(client)
    plan = await _active_plan(client, h, accept=False)
    await client.post(f"{BASE}/training-plans/{plan['id']}/accept", headers=h, json={"start_date": "2035-01-01"})
    nxt = (await client.get(f"{BASE}/sessions/next", headers=h)).json()
    assert nxt["scheduled_date"] >= "2035-01-01"                                              # not before the plan starts
    plan = await _active_plan(client, h, accept=False)
    await client.post(f"{BASE}/training-plans/{plan['id']}/accept", headers=h, json={"start_date": "2020-01-01"})
    assert (await client.get(f"{BASE}/sessions/next", headers=h)).status_code == 404         # the plan has ended
