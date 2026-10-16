"""B-06: biometric profile, injuries, allergies and excluded foods against a real, seeded PostgreSQL."""
from __future__ import annotations

import uuid

import httpx
import pytest
import pytest_asyncio

from app.core.config import Settings
from app.domain.nutrition import tdee
from app.main import create_app
from tests.support import NO_STORES

PASSWORD = "Secret123"
PROFILE = {"age": 30, "sex": "male", "weight_kg": 80, "height_cm": 180, "activity_level_pal": 1.55,
           "goal": "muscle_gain", "experience_level": "advanced", "equipment": "gym"}
BASE = "/api/v1/users/me"


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
    pair = (await client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})).json()
    return {"Authorization": f"Bearer {pair['access_token']}"}


async def _ids(client, h, path: str) -> dict[str, int]:
    return {x["name"]: x["id"] for x in (await client.get(f"/api/v1{path}", headers=h)).json()}


# ------------------------------------------------------------------ authentication and isolation

async def test_every_route_requires_a_token(client):
    for method, path in [("get", "/profile"), ("put", "/profile"), ("get", "/injuries"), ("post", "/injuries"),
                         ("patch", "/injuries/1"), ("delete", "/injuries/1"), ("get", "/allergies"),
                         ("put", "/allergies"), ("get", "/excluded-foods"), ("put", "/excluded-foods")]:
        r = await client.request(method, BASE + path, json={})
        assert r.status_code == 401, (method, path)


async def test_users_cannot_see_each_others_data(client):
    a, b = await _user(client), await _user(client)
    assert (await client.put(f"{BASE}/profile", json=PROFILE, headers=a)).status_code == 200
    assert (await client.get(f"{BASE}/profile", headers=b)).status_code == 404
    groups, types = await _ids(client, a, "/muscle-groups"), await _ids(client, a, "/injury-types")
    injury = (await client.post(f"{BASE}/injuries", headers=a, json={
        "injury_type_id": types["ankle sprain"], "affected_muscle_group_id": groups["calves"],
        "severity": "mild", "start_date": "2026-09-01"})).json()
    assert (await client.get(f"{BASE}/injuries", headers=b)).json() == []
    assert (await client.patch(f"{BASE}/injuries/{injury['id']}", json={"is_active": False}, headers=b)).status_code == 404
    assert (await client.delete(f"{BASE}/injuries/{injury['id']}", headers=b)).status_code == 404
    still = (await client.get(f"{BASE}/injuries", headers=a)).json()
    assert len(still) == 1 and still[0]["is_active"] is True  # untouched by B

    allergens = await _ids(client, a, "/allergens")
    await client.put(f"{BASE}/allergies", json={"allergen_ids": [allergens["gluten"]]}, headers=a)
    assert (await client.get(f"{BASE}/allergies", headers=b)).json() == []


# ------------------------------------------------------------------ profile

async def test_profile_is_created_read_and_tdee_is_computed(client):
    h = await _user(client)
    assert (await client.get(f"{BASE}/profile", headers=h)).status_code == 404
    r = await client.put(f"{BASE}/profile", json=PROFILE, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tdee_kcal"] == tdee("male", 80, 180, 30, 1.55) == 2759  # 10*80 + 6.25*180 - 5*30 + 5 = 1780; * 1.55
    assert {k: body[k] for k in PROFILE} == PROFILE and body["target_weight_kg"] is None and body["updated_at"]
    assert (await client.get(f"{BASE}/profile", headers=h)).json() == body


async def test_put_replaces_the_profile_and_recomputes_tdee(client):
    h = await _user(client)
    first = (await client.put(f"{BASE}/profile", json=PROFILE, headers=h)).json()
    changed = {**PROFILE, "weight_kg": 90.5, "sex": "female", "goal": "weight_loss", "target_weight_kg": 70,
               "equipment": "home"}
    second = (await client.put(f"{BASE}/profile", json=changed, headers=h)).json()
    assert second["tdee_kcal"] == tdee("female", 90.5, 180, 30, 1.55) != first["tdee_kcal"]
    assert second["weight_kg"] == 90.5 and second["target_weight_kg"] == 70 and second["equipment"] == "home"
    assert second["updated_at"] >= first["updated_at"]
    assert (await client.get(f"{BASE}/profile", headers=h)).json() == second  # replaced, not merged


@pytest.mark.parametrize("pal", [1.2, 1.375, 1.55, 1.725, 1.9])
async def test_all_offered_pal_values_are_stored_exactly(client, pal):
    """The five levels the app offers (algorithms.md section 0), including the two with three decimals."""
    h = await _user(client)
    body = (await client.put(f"{BASE}/profile", json={**PROFILE, "activity_level_pal": pal}, headers=h)).json()
    assert body["activity_level_pal"] == pal and body["tdee_kcal"] == tdee("male", 80, 180, 30, pal)
    again = (await client.get(f"{BASE}/profile", headers=h)).json()
    assert again["activity_level_pal"] == pal and again["tdee_kcal"] == body["tdee_kcal"]


@pytest.mark.parametrize(("field", "ok", "bad"), [
    ("weight_kg", [30, 300, 30.01, 299.99], [29, 29.99, 300.01, 301, 0, -5]),
    ("target_weight_kg", [30, 300], [29, 301]),
    ("age", [16, 100], [15, 101, 0, -1]),
    ("height_cm", [120, 250], [119, 251]),
    ("activity_level_pal", [1.2, 2.4, 1.55], [1.19, 2.41, 0]),
])
async def test_range_boundaries(client, field, ok, bad):
    h = await _user(client)
    for value in ok:
        r = await client.put(f"{BASE}/profile", json={**PROFILE, field: value}, headers=h)
        assert r.status_code == 200, (field, value, r.text)
    for value in bad:
        r = await client.put(f"{BASE}/profile", json={**PROFILE, field: value}, headers=h)
        assert r.status_code == 422, (field, value)
        assert r.json()["code"] == "validation_error"
        assert r.json()["details"][0]["field"] == field and r.json()["details"][0]["code"] == "out_of_range"


async def test_missing_fields_are_reported_one_by_one(client):
    h = await _user(client)
    r = await client.put(f"{BASE}/profile", json={"age": 30}, headers=h)
    assert r.status_code == 422
    fields = {d["field"]: d["code"] for d in r.json()["details"]}
    assert fields == {k: "required" for k in PROFILE if k != "age"}


async def test_wrong_types_and_enums_give_field_errors(client):
    h = await _user(client)
    for field, value in [("sex", "robot"), ("goal", "fly"), ("experience_level", "god"), ("equipment", "boat"),
                         ("age", "thirty"), ("age", 30.5), ("weight_kg", "heavy"), ("height_cm", None)]:
        r = await client.put(f"{BASE}/profile", json={**PROFILE, field: value}, headers=h)
        assert r.status_code == 422 and r.json()["details"][0]["field"] == field, (field, value)
        assert r.json()["details"][0]["code"] in ("invalid", "required"), (field, value, r.json())


async def test_nan_and_infinity_are_rejected(client):
    h = await _user(client)
    for literal in ("NaN", "Infinity", "-Infinity"):
        raw = ('{"age":30,"sex":"male","weight_kg":' + literal + ',"height_cm":180,"activity_level_pal":1.55,'
               '"goal":"muscle_gain","experience_level":"advanced","equipment":"gym"}')
        r = await client.put(f"{BASE}/profile", content=raw, headers={**h, "content-type": "application/json"})
        assert r.status_code == 422, literal


async def test_failed_validation_does_not_change_the_stored_profile(client):
    h = await _user(client)
    good = (await client.put(f"{BASE}/profile", json=PROFILE, headers=h)).json()
    assert (await client.put(f"{BASE}/profile", json={**PROFILE, "weight_kg": 301}, headers=h)).status_code == 422
    assert (await client.get(f"{BASE}/profile", headers=h)).json() == good


# ------------------------------------------------------------------ injuries

async def test_injury_crud(client):
    h = await _user(client)
    groups, types = await _ids(client, h, "/muscle-groups"), await _ids(client, h, "/injury-types")
    payload = {"injury_type_id": types["shoulder impingement"], "affected_muscle_group_id": groups["shoulders"],
               "severity": "moderate", "start_date": "2026-09-01", "notes": "left side"}
    created = await client.post(f"{BASE}/injuries", json=payload, headers=h)
    assert created.status_code == 201, created.text
    injury = created.json()
    assert injury["is_active"] is True and injury["injury_type_name"] == "shoulder impingement"
    assert injury["affected_muscle_group_name"] == "shoulders" and injury["notes"] == "left side"

    # partial update: only the sent fields change
    r = await client.patch(f"{BASE}/injuries/{injury['id']}", json={"severity": "severe"}, headers=h)
    assert r.json()["severity"] == "severe" and r.json()["notes"] == "left side" and r.json()["is_active"] is True
    r = await client.patch(f"{BASE}/injuries/{injury['id']}", json={"is_active": False, "notes": None}, headers=h)
    assert r.json()["is_active"] is False and r.json()["notes"] is None and r.json()["severity"] == "severe"
    assert (await client.patch(f"{BASE}/injuries/{injury['id']}", json={}, headers=h)).json() == r.json()

    assert (await client.delete(f"{BASE}/injuries/{injury['id']}", headers=h)).status_code == 204
    assert (await client.delete(f"{BASE}/injuries/{injury['id']}", headers=h)).status_code == 404
    assert (await client.get(f"{BASE}/injuries", headers=h)).json() == []


async def test_injury_list_shows_active_first_then_newest(client):
    h = await _user(client)
    groups, types = await _ids(client, h, "/muscle-groups"), await _ids(client, h, "/injury-types")
    base = {"injury_type_id": types["wrist sprain"], "affected_muscle_group_id": groups["biceps"], "severity": "mild"}
    old = (await client.post(f"{BASE}/injuries", headers=h, json={**base, "start_date": "2026-01-01"})).json()
    healed = (await client.post(f"{BASE}/injuries", headers=h,
                                json={**base, "start_date": "2026-08-01", "is_active": False})).json()
    new = (await client.post(f"{BASE}/injuries", headers=h, json={**base, "start_date": "2026-09-01"})).json()
    assert [i["id"] for i in (await client.get(f"{BASE}/injuries", headers=h)).json()] == [new["id"], old["id"], healed["id"]]


async def test_injury_validation(client):
    h = await _user(client)
    groups, types = await _ids(client, h, "/muscle-groups"), await _ids(client, h, "/injury-types")
    good = {"injury_type_id": types["wrist sprain"], "affected_muscle_group_id": groups["biceps"],
            "severity": "mild", "start_date": "2026-09-01"}
    unknown = await client.post(f"{BASE}/injuries", headers=h,
                                json={**good, "injury_type_id": 999999, "affected_muscle_group_id": 999999})
    assert unknown.status_code == 422
    assert {d["field"]: d["code"] for d in unknown.json()["details"]} == {
        "injury_type_id": "not_found", "affected_muscle_group_id": "not_found"}
    for bad in ({"severity": "fatal"}, {"start_date": "yesterday"}, {"notes": "x" * 501}, {"injury_type_id": "a"}):
        r = await client.post(f"{BASE}/injuries", headers=h, json={**good, **bad})
        assert r.status_code == 422 and r.json()["details"][0]["field"] == next(iter(bad)), bad
    assert (await client.post(f"{BASE}/injuries", headers=h, json={})).status_code == 422
    created = (await client.post(f"{BASE}/injuries", headers=h, json=good)).json()
    for patch in ({"severity": None}, {"is_active": None}, {"severity": "fatal"}, {"notes": "x" * 501}):
        r = await client.patch(f"{BASE}/injuries/{created['id']}", json=patch, headers=h)
        assert r.status_code == 422, patch
    assert (await client.patch(f"{BASE}/injuries/0", json={}, headers=h)).status_code == 422
    assert (await client.patch(f"{BASE}/injuries/999999", json={}, headers=h)).status_code == 404


async def test_saved_injury_changes_the_exercise_alternatives(client):
    """Integration: the injury entered here is the one the exercise library (B-08) filters by."""
    h = await _user(client)
    await client.put(f"{BASE}/profile", json=PROFILE, headers=h)
    exercises = (await client.get("/api/v1/exercises?q=Barbell bench press", headers=h)).json()["items"]
    bench = exercises[0]["id"]
    before = {a["name"] for a in (await client.get(f"/api/v1/exercises/{bench}/alternatives", headers=h)).json()}
    assert {"Machine chest press", "Dumbbell fly"} <= before
    groups, types = await _ids(client, h, "/muscle-groups"), await _ids(client, h, "/injury-types")
    injury = (await client.post(f"{BASE}/injuries", headers=h, json={
        "injury_type_id": types["shoulder impingement"], "affected_muscle_group_id": groups["shoulders"],
        "severity": "moderate", "start_date": "2026-09-01"})).json()
    after = [a["name"] for a in (await client.get(f"/api/v1/exercises/{bench}/alternatives", headers=h)).json()]
    assert after == ["Cable crossover"]
    await client.patch(f"{BASE}/injuries/{injury['id']}", json={"is_active": False}, headers=h)  # healed
    healed = {a["name"] for a in (await client.get(f"/api/v1/exercises/{bench}/alternatives", headers=h)).json()}
    assert healed == before


# ------------------------------------------------------------------ allergies

async def test_allergies_are_replaced_as_a_whole(client):
    h = await _user(client)
    ids = await _ids(client, h, "/allergens")
    assert (await client.get(f"{BASE}/allergies", headers=h)).json() == []
    r = await client.put(f"{BASE}/allergies", headers=h, json={"allergen_ids": [ids["peanuts"], ids["gluten"],
                                                                                 ids["peanuts"]]})
    assert r.status_code == 200
    assert [a["name"] for a in r.json()] == ["gluten", "peanuts"]  # sorted by name, duplicates dropped
    assert [a["name"] for a in (await client.get(f"{BASE}/allergies", headers=h)).json()] == ["gluten", "peanuts"]
    r = await client.put(f"{BASE}/allergies", headers=h, json={"allergen_ids": [ids["milk"]]})
    assert [a["name"] for a in r.json()] == ["milk"]
    assert (await client.put(f"{BASE}/allergies", headers=h, json={"allergen_ids": []})).json() == []


async def test_unknown_allergen_changes_nothing(client):
    h = await _user(client)
    ids = await _ids(client, h, "/allergens")
    await client.put(f"{BASE}/allergies", headers=h, json={"allergen_ids": [ids["eggs"]]})
    r = await client.put(f"{BASE}/allergies", headers=h, json={"allergen_ids": [ids["milk"], 999999]})
    assert r.status_code == 422 and r.json()["details"][0] == {
        "field": "allergen_ids", "code": "not_found", "message": "Unknown id(s): [999999]"}
    assert [a["name"] for a in (await client.get(f"{BASE}/allergies", headers=h)).json()] == ["eggs"]
    for body in ({}, {"allergen_ids": "all"}, {"allergen_ids": ["a"]}):
        assert (await client.put(f"{BASE}/allergies", headers=h, json=body)).status_code == 422


# ------------------------------------------------------------------ excluded foods

async def test_excluded_foods_are_replaced_as_a_whole(client):
    h = await _user(client)
    async def food_id(name: str) -> int:
        items = (await client.get(f"/api/v1/foods?q={name}", headers=h)).json()["items"]
        return next(f["id"] for f in items if f["name"] == name)

    pick = [await food_id("Egg, whole, boiled"), await food_id("Peanuts")]
    assert (await client.get(f"{BASE}/excluded-foods", headers=h)).json() == []
    r = await client.put(f"{BASE}/excluded-foods", headers=h, json={"food_item_ids": pick})
    assert r.status_code == 200
    assert {f["name"] for f in r.json()} == {"Egg, whole, boiled", "Peanuts"}
    assert {"id", "name", "calories_per_100g", "role", "default_portion_g"} <= set(r.json()[0])
    r = await client.put(f"{BASE}/excluded-foods", headers=h, json={"food_item_ids": [999999]})
    assert r.status_code == 422 and r.json()["details"][0]["field"] == "food_item_ids"
    assert len((await client.get(f"{BASE}/excluded-foods", headers=h)).json()) == 2  # unchanged
    assert (await client.put(f"{BASE}/excluded-foods", headers=h, json={"food_item_ids": []})).json() == []
