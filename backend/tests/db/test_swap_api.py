"""B-13: swapping and editing planned exercises against a real, seeded PostgreSQL."""
from __future__ import annotations

import uuid

import httpx
import pytest_asyncio

from app.core.config import Settings
from app.main import create_app
from tests.support import NO_STORES

BASE = "/api/v1"
PROFILE = {"age": 30, "sex": "male", "weight_kg": 80, "height_cm": 180, "activity_level_pal": 1.55,
           "goal": "muscle_gain", "experience_level": "advanced", "equipment": "gym"}
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


async def _user(client, profile: dict | None = PROFILE) -> dict:
    email = f"{uuid.uuid4().hex[:10]}@example.com"
    pair = (await client.post(f"{BASE}/auth/register", json={"email": email, "password": "Secret123"})).json()
    headers = {"Authorization": f"Bearer {pair['access_token']}"}
    if profile is not None:
        await client.put(f"{BASE}/users/me/profile", json=profile, headers=headers)
    return headers


async def _plan(client, h, body: dict | None = None, accept: bool = False) -> dict:
    plan = (await client.post(f"{BASE}/training-plans/generate", json=body or GEN, headers=h)).json()
    if accept:
        plan = (await client.post(f"{BASE}/training-plans/{plan['id']}/accept", headers=h)).json()
    return plan


def _find(plan: dict, group: str) -> tuple[dict, dict]:
    """(session, planned exercise) of the first exercise for a muscle group."""
    for s in plan["sessions"]:
        for e in s["exercises"]:
            if e["exercise"]["main_muscle_group"]["name"] == group:
                return s, e
    raise AssertionError(group)


async def _exercises(client, h, group: str) -> dict[str, dict]:
    groups = {g["name"]: g["id"] for g in (await client.get(f"{BASE}/muscle-groups", headers=h)).json()}
    items = (await client.get(f"{BASE}/exercises?muscle_group_id={groups[group]}&limit=100", headers=h)).json()["items"]
    return {e["name"]: e for e in items}


async def _swap(client, h, se_id: int, exercise_id: int):
    return await client.put(f"{BASE}/session-exercises/{se_id}/swap", json={"exercise_id": exercise_id}, headers=h)


async def _current(client, h, se_id: int) -> dict:
    plan = (await client.get(f"{BASE}/training-plans/draft", headers=h))
    if plan.status_code != 200:
        plan = await client.get(f"{BASE}/training-plans/active", headers=h)
    return next(e for s in plan.json()["sessions"] for e in s["exercises"] if e["id"] == se_id)


# ------------------------------------------------------------------ swap

async def test_requires_authentication(client):
    assert (await client.put(f"{BASE}/session-exercises/1/swap", json={"exercise_id": 1})).status_code == 401
    assert (await client.patch(f"{BASE}/session-exercises/1", json={"planned_sets": 3})).status_code == 401


async def test_swap_keeps_the_prescription_and_remembers_the_original(client):
    h = await _user(client)
    plan = await _plan(client, h)
    session, planned = _find(plan, "chest")
    await client.patch(f"{BASE}/session-exercises/{planned['id']}", headers=h, json={"planned_weight_kg": 62.5})
    in_session = {e["exercise"]["id"] for e in session["exercises"]}
    target = next(e for e in (await _exercises(client, h, "chest")).values() if e["id"] not in in_session)

    r = await _swap(client, h, planned["id"], target["id"])
    assert r.status_code == 200, r.text
    swapped = r.json()
    assert swapped["exercise"]["id"] == target["id"] and swapped["original_exercise_id"] == planned["exercise"]["id"]
    assert (swapped["planned_sets"], swapped["planned_reps"], swapped["rest_seconds"], swapped["position"]) == (
        planned["planned_sets"], planned["planned_reps"], planned["rest_seconds"], planned["position"])
    assert swapped["planned_weight_kg"] == 62.5  # weight kept
    assert await _current(client, h, planned["id"]) == swapped  # persisted

    # swapping again keeps the ORIGINAL generated exercise, swapping back clears it
    others = [e for e in (await _exercises(client, h, "chest")).values()
              if e["id"] not in in_session | {target["id"]}]
    again = (await _swap(client, h, planned["id"], others[0]["id"])).json()
    assert again["original_exercise_id"] == planned["exercise"]["id"]
    back = (await _swap(client, h, planned["id"], planned["exercise"]["id"])).json()
    assert back["exercise"]["id"] == planned["exercise"]["id"] and back["original_exercise_id"] is None


async def test_swap_works_on_the_active_plan_too(client):
    h = await _user(client)
    plan = await _plan(client, h, accept=True)
    session, planned = _find(plan, "back")
    in_session = {e["exercise"]["id"] for e in session["exercises"]}
    target = next(e for e in (await _exercises(client, h, "back")).values() if e["id"] not in in_session)
    assert (await _swap(client, h, planned["id"], target["id"])).status_code == 200
    active = (await client.get(f"{BASE}/training-plans/active", headers=h)).json()
    assert target["name"] in {e["exercise"]["name"] for s in active["sessions"] for e in s["exercises"]}


async def test_swap_rules_each_have_a_reason(client):
    h = await _user(client)
    plan = await _plan(client, h)
    session, planned = _find(plan, "chest")
    chest = await _exercises(client, h, "chest")
    in_session = [e["exercise"]["id"] for e in session["exercises"]]
    other_group = next(iter((await _exercises(client, h, "calves")).values()))
    cases = {
        "other_muscle_group": other_group["id"],
        "same_exercise": planned["exercise"]["id"],
        "unknown_exercise": 999999,
    }
    for code, exercise_id in cases.items():
        r = await _swap(client, h, planned["id"], exercise_id)
        assert r.status_code == 422 and r.json()["code"] == "invalid_swap", code
        assert r.json()["details"][0]["field"] == "exercise_id" and r.json()["details"][0]["code"] == code
    # a chest exercise that already sits in the same session (when the session has two chest exercises)
    siblings = [i for i in in_session if i != planned["exercise"]["id"] and i in {e["id"] for e in chest.values()}]
    for sibling in siblings:
        r = await _swap(client, h, planned["id"], sibling)
        assert r.status_code == 422 and r.json()["details"][0]["code"] == "already_in_session"
    assert (await _current(client, h, planned["id"]))["exercise"]["id"] == planned["exercise"]["id"]  # unchanged


async def test_swap_respects_the_level_and_equipment_of_the_plan(client):
    """The plan is for a beginner without equipment: harder or equipment-needing exercises are refused."""
    h = await _user(client)
    plan = await _plan(client, h, {**GEN, "experience_level": "beginner", "equipment": "none"})
    session, planned = _find(plan, "chest")
    chest = await _exercises(client, h, "chest")
    in_session = {e["exercise"]["id"] for e in session["exercises"]}
    expectations = {"Archer push-up": "above_level",  # advanced, bodyweight
                    "Decline push-up": "above_level",  # intermediate, bodyweight
                    "Machine chest press": "needs_equipment",  # beginner but gym
                    "Dumbbell floor press": "needs_equipment"}  # beginner but home
    checked = 0
    for name, code in expectations.items():
        if chest[name]["id"] in in_session:
            continue
        r = await _swap(client, h, planned["id"], chest[name]["id"])
        assert r.status_code == 422 and r.json()["details"][0]["code"] == code, (name, r.json())
        checked += 1
    assert checked >= 3  # the refusals really ran (a beginner/none session holds at most one other chest exercise)
    allowed = next(e for n, e in chest.items() if e["equipment"] == "none" and e["difficulty_level"] == "beginner"
                   and e["id"] not in in_session)
    assert (await _swap(client, h, planned["id"], allowed["id"])).status_code == 200


async def test_swap_respects_injuries_added_after_the_plan_was_made(client):
    h = await _user(client)
    plan = await _plan(client, h)
    session, planned = _find(plan, "chest")
    in_session = {e["exercise"]["id"] for e in session["exercises"]}
    groups = {g["name"]: g["id"] for g in (await client.get(f"{BASE}/muscle-groups", headers=h)).json()}
    types = {t["name"]: t["id"] for t in (await client.get(f"{BASE}/injury-types", headers=h)).json()}
    injury = (await client.post(f"{BASE}/users/me/injuries", headers=h, json={
        "injury_type_id": types["rotator cuff strain"], "affected_muscle_group_id": groups["shoulders"],
        "severity": "moderate", "start_date": "2026-09-01"})).json()
    chest = await _exercises(client, h, "chest")
    blocked = next(e for n, e in chest.items() if n in ("Dumbbell fly", "Cable crossover") and e["id"] not in in_session)
    r = await _swap(client, h, planned["id"], blocked["id"])
    assert r.status_code == 422 and r.json()["details"][0]["code"] == "excluded_by_injury"
    await client.patch(f"{BASE}/users/me/injuries/{injury['id']}", json={"is_active": False}, headers=h)  # healed
    assert (await _swap(client, h, planned["id"], blocked["id"])).status_code == 200


async def test_swap_agrees_with_the_alternatives_endpoint(client):
    """Same rules as GET /exercises/{id}/alternatives when the plan uses the profile's level and equipment."""
    h = await _user(client, {**PROFILE, "experience_level": "intermediate", "equipment": "home"})
    plan = await _plan(client, h)
    session, planned = _find(plan, "quadriceps")
    alternatives = {a["id"] for a in (await client.get(
        f"{BASE}/exercises/{planned['exercise']['id']}/alternatives", headers=h)).json()}
    in_session = {e["exercise"]["id"] for e in session["exercises"]}
    accepted = refused = 0
    for name, candidate in (await _exercises(client, h, "quadriceps")).items():
        expected = candidate["id"] in alternatives and candidate["id"] not in in_session
        r = await _swap(client, h, planned["id"], candidate["id"])
        assert (r.status_code == 200) == expected, (name, r.status_code, r.text)
        if r.status_code == 200:  # put it back so the next candidate is judged against the same session
            accepted += 1
            await _swap(client, h, planned["id"], planned["exercise"]["id"])
        else:
            refused += 1
    assert accepted >= 2 and refused >= 2  # both outcomes were really exercised


async def test_swap_is_scoped_to_the_owner_and_to_live_plans(client):
    a, b = await _user(client), await _user(client)
    plan = await _plan(client, a)
    _, planned = _find(plan, "chest")
    target = next(e for e in (await _exercises(client, a, "chest")).values() if e["id"] != planned["exercise"]["id"])
    assert (await _swap(client, b, planned["id"], target["id"])).status_code == 404
    assert (await client.patch(f"{BASE}/session-exercises/{planned['id']}", json={"planned_sets": 2},
                               headers=b)).status_code == 404
    assert (await _swap(client, a, 999999, target["id"])).status_code == 404
    assert (await client.put(f"{BASE}/session-exercises/0/swap", json={"exercise_id": 1}, headers=a)).status_code == 422
    assert (await client.put(f"{BASE}/session-exercises/{planned['id']}/swap", json={}, headers=a)).status_code == 422

    # a plan that was replaced by a newer accepted plan is archived history
    first = await _plan(client, a, accept=True)
    await _plan(client, a, accept=True)
    _, old = _find(first, "chest")
    assert (await _swap(client, a, old["id"], target["id"])).status_code == 409
    assert (await client.patch(f"{BASE}/session-exercises/{old['id']}", json={"planned_sets": 2},
                               headers=a)).status_code == 409


# ------------------------------------------------------------------ edit

async def test_edit_changes_only_the_fields_sent(client):
    h = await _user(client)
    _, planned = _find(await _plan(client, h), "back")
    url = f"{BASE}/session-exercises/{planned['id']}"
    r = await client.patch(url, json={"planned_sets": 5}, headers=h)
    assert r.status_code == 200 and r.json()["planned_sets"] == 5
    assert r.json()["planned_reps"] == planned["planned_reps"] and r.json()["rest_seconds"] == planned["rest_seconds"]
    r = await client.patch(url, json={"planned_reps": 12, "rest_seconds": 90, "planned_weight_kg": 40.126}, headers=h)
    assert (r.json()["planned_sets"], r.json()["planned_reps"], r.json()["rest_seconds"]) == (5, 12, 90)
    assert r.json()["planned_weight_kg"] == 40.13  # two decimals, half up
    assert (await _current(client, h, planned["id"])) == r.json()
    cleared = await client.patch(url, json={"planned_weight_kg": None}, headers=h)  # the weight may be cleared
    assert cleared.status_code == 200 and cleared.json()["planned_weight_kg"] is None
    assert cleared.json()["planned_sets"] == 5


async def test_edit_validation_uses_the_contract_ranges(client):
    h = await _user(client)
    _, planned = _find(await _plan(client, h), "back")
    url = f"{BASE}/session-exercises/{planned['id']}"
    for field, ok, bad in [("planned_sets", [1, 10], [0, 11]), ("planned_reps", [1, 50], [0, 51]),
                           ("rest_seconds", [0, 600], [-1, 601]), ("planned_weight_kg", [0, 9999.99], [-0.5, 10000])]:
        for value in ok:
            assert (await client.patch(url, json={field: value}, headers=h)).status_code == 200, (field, value)
        for value in bad:
            r = await client.patch(url, json={field: value}, headers=h)
            assert r.status_code == 422 and r.json()["details"][0]["field"] == field, (field, value)
    for body in ({}, {"planned_sets": None}, {"planned_reps": "many"}, {"rest_seconds": 1.5}):
        assert (await client.patch(url, json=body, headers=h)).status_code == 422, body
