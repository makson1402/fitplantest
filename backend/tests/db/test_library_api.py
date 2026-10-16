"""B-08 / B-09: reference data and library endpoints against a real, seeded PostgreSQL."""
from __future__ import annotations

import uuid

import httpx
import pytest_asyncio
from sqlalchemy import text

from app.core.config import Settings
from app.main import create_app
from tests.support import NO_STORES

PASSWORD = "Secret123"


@pytest_asyncio.fixture
async def client(seeded_engine):
    url = seeded_engine.url.render_as_string(hide_password=False)
    settings = Settings(jwt_secret="test-secret-" + "x" * 32, bcrypt_rounds=4, auth_rate_limit=10_000,
                        _env_file=None, **{**NO_STORES, "database_url": url})
    app = create_app(settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        yield http
    await app.state.db_engine.dispose()


async def _register(client) -> tuple[dict, str]:
    """Register a new user; returns the auth headers and the email."""
    email = f"{uuid.uuid4().hex[:10]}@example.com"
    pair = (await client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})).json()
    return {"Authorization": f"Bearer {pair['access_token']}"}, email


async def _auth(client) -> dict:
    return (await _register(client))[0]


def _user_id(engine, email: str) -> int:
    with engine.connect() as c:
        return c.execute(text("select id from users where email = :e"), {"e": email}).scalar_one()


def _set_profile(engine, user_id: int, level: str, equipment: str):
    with engine.begin() as c:
        c.execute(text(
            "insert into user_profile (user_id, age, sex, weight_kg, height_cm, activity_level_pal, goal,"
            " experience_level, equipment) values (:u, 30, 'male', 80, 180, 1.55, 'muscle_gain', :l, :e)"),
            {"u": user_id, "l": level, "e": equipment})


def _add_injury(engine, user_id: int, injury_type: str, group: str, severity: str = "moderate"):
    with engine.begin() as c:
        c.execute(text(
            "insert into injury (user_id, injury_type_id, affected_muscle_group_id, severity, start_date)"
            " select :u, it.id, mg.id, :s, current_date from injury_type it, muscle_group mg"
            " where it.name = :it and mg.name = :g"), {"u": user_id, "it": injury_type, "g": group, "s": severity})


# ------------------------------------------------------------------ authentication

async def test_every_library_route_requires_a_token(client):
    for path in ("/injury-types", "/allergens", "/muscle-groups", "/food-categories", "/exercises", "/exercises/1",
                 "/exercises/1/alternatives", "/foods", "/foods/1"):
        r = await client.get(f"/api/v1{path}")
        assert r.status_code == 401, path
        assert r.json()["code"] == "unauthorized"


# ------------------------------------------------------------------ dictionaries

async def test_dictionaries_return_the_seeded_data(client):
    h = await _auth(client)
    groups = (await client.get("/api/v1/muscle-groups", headers=h)).json()
    assert [g["name"] for g in groups] == ["chest", "back", "shoulders", "biceps", "triceps", "quadriceps",
                                           "hamstrings", "glutes", "calves", "core"]
    assert {g["body_region"] for g in groups} == {"upper", "lower", "core"}
    allergens = (await client.get("/api/v1/allergens", headers=h)).json()
    assert len(allergens) == 15 and {"gluten", "lactose", "peanuts"} <= {a["name"] for a in allergens}
    injuries = (await client.get("/api/v1/injury-types", headers=h)).json()
    assert len(injuries) == 17 and all(i["avg_healing_time_days"] > 0 for i in injuries)
    categories = (await client.get("/api/v1/food-categories", headers=h)).json()
    assert len(categories) == 16 and {"dairy", "fruit"} <= {c["name"] for c in categories}


# ------------------------------------------------------------------ exercises

async def test_exercise_list_is_paginated_with_stable_order(client):
    h = await _auth(client)
    first = (await client.get("/api/v1/exercises?limit=10&offset=0", headers=h)).json()
    second = (await client.get("/api/v1/exercises?limit=10&offset=10", headers=h)).json()
    assert first["limit"] == 10 and first["offset"] == 0 and first["total"] >= 100
    names = [e["name"] for e in first["items"]] + [e["name"] for e in second["items"]]
    together = (await client.get("/api/v1/exercises?limit=20&offset=0", headers=h)).json()
    # pages tile the list without overlap or gaps; the order does not depend on the database collation
    assert len(set(names)) == 20 and names == [e["name"] for e in together["items"]]
    item = first["items"][0]
    assert set(item) == {"id", "name", "main_muscle_group", "difficulty_level", "equipment", "is_compound",
                         "is_bodyweight"}
    default = (await client.get("/api/v1/exercises", headers=h)).json()
    assert default["limit"] == 20 and len(default["items"]) == 20


async def test_exercise_filters(client):
    h = await _auth(client)
    groups = {g["name"]: g["id"] for g in (await client.get("/api/v1/muscle-groups", headers=h)).json()}
    r = (await client.get(f"/api/v1/exercises?muscle_group_id={groups['calves']}&limit=100", headers=h)).json()
    assert r["total"] >= 8 and all(e["main_muscle_group"]["name"] == "calves" for e in r["items"])
    r = (await client.get("/api/v1/exercises?equipment=none&difficulty_level=beginner&limit=100", headers=h)).json()
    assert r["total"] > 0 and all(e["equipment"] == "none" and e["difficulty_level"] == "beginner" for e in r["items"])
    r = (await client.get("/api/v1/exercises?q=SQUAT&limit=100", headers=h)).json()  # case-insensitive
    assert r["total"] >= 5 and all("squat" in e["name"].lower() for e in r["items"])
    assert (await client.get("/api/v1/exercises?q=zzzz-nothing", headers=h)).json()["items"] == []


async def test_search_text_is_not_a_wildcard_pattern(client):
    h = await _auth(client)
    assert (await client.get("/api/v1/exercises?q=%25", headers=h)).json()["total"] == 0  # a literal "%"
    assert (await client.get("/api/v1/exercises?q=_", headers=h)).json()["total"] == 0


async def test_exercise_detail_has_instruction_and_secondary_groups(client):
    h = await _auth(client)
    listing = (await client.get("/api/v1/exercises?q=Barbell back squat", headers=h)).json()["items"]
    assert len(listing) == 1
    detail = (await client.get(f"/api/v1/exercises/{listing[0]['id']}", headers=h)).json()
    assert detail["name"] == "Barbell back squat" and detail["instruction"] and detail["description"]
    assert {g["name"] for g in detail["secondary_muscle_groups"]} == {"glutes", "hamstrings", "core"}
    assert detail["main_muscle_group"]["name"] == "quadriceps"


async def test_missing_exercise_and_food_give_404(client):
    h = await _auth(client)
    for path in ("/exercises/999999", "/exercises/999999/alternatives", "/foods/999999"):
        r = await client.get(f"/api/v1{path}", headers=h)
        assert r.status_code == 404 and r.json()["code"] == "not_found", path


async def test_invalid_parameters_give_422_with_field_details(client):
    h = await _auth(client)
    for query in ("limit=0", "limit=101", "offset=-1", "equipment=boat", "difficulty_level=expert", "limit=abc"):
        r = await client.get(f"/api/v1/exercises?{query}", headers=h)
        assert r.status_code == 422 and r.json()["code"] == "validation_error" and r.json()["details"], query
    assert (await client.get("/api/v1/exercises/0", headers=h)).status_code == 422
    assert (await client.get("/api/v1/foods?role=snack", headers=h)).status_code == 422


# ------------------------------------------------------------------ alternatives (FR-A1)

async def _exercise_id(client, h, name: str) -> int:
    items = (await client.get(f"/api/v1/exercises?q={name}&limit=100", headers=h)).json()["items"]
    return next(e["id"] for e in items if e["name"] == name)


async def test_alternatives_without_profile_apply_only_the_injury_rule(client):
    h = await _auth(client)
    bench = await _exercise_id(client, h, "Barbell bench press")
    alts = (await client.get(f"/api/v1/exercises/{bench}/alternatives", headers=h)).json()
    assert alts and all(a["main_muscle_group"]["name"] == "chest" and a["id"] != bench for a in alts)
    assert any(a["equipment"] == "gym" for a in alts)  # no equipment to respect without a profile


async def test_alternatives_respect_level_and_equipment(client, seeded_engine):
    h, email = await _register(client)
    _set_profile(seeded_engine, _user_id(seeded_engine, email), "beginner", "none")
    bench = await _exercise_id(client, h, "Barbell bench press")
    alts = (await client.get(f"/api/v1/exercises/{bench}/alternatives", headers=h)).json()
    assert alts and all(a["equipment"] == "none" and a["difficulty_level"] == "beginner" for a in alts)
    assert {a["name"] for a in alts} == {"Push-up", "Incline push-up"}


async def test_alternatives_never_include_injury_excluded_exercises(client, seeded_engine):
    """Done when (B-08): alternatives never include an exercise excluded by the user's injuries."""
    h, email = await _register(client)
    uid = _user_id(seeded_engine, email)
    _set_profile(seeded_engine, uid, "advanced", "gym")
    _add_injury(seeded_engine, uid, "shoulder impingement", "shoulders", "moderate")

    # Rule 2 (main group = injured group): every shoulder exercise is blocked, so nothing is offered.
    front_raise = await _exercise_id(client, h, "Dumbbell front raise")
    assert (await client.get(f"/api/v1/exercises/{front_raise}/alternatives", headers=h)).json() == []

    # Rule 3 (secondary group at moderate severity) and the explicit list for the injury type leave exactly one
    # chest alternative: every other chest exercise loads the shoulders or is listed for shoulder impingement.
    bench = await _exercise_id(client, h, "Barbell bench press")
    chest = (await client.get(f"/api/v1/exercises/{bench}/alternatives", headers=h)).json()
    assert [a["name"] for a in chest] == ["Cable crossover"]


async def test_mild_injury_does_not_apply_the_secondary_group_rule(client, seeded_engine):
    h, email = await _register(client)
    uid = _user_id(seeded_engine, email)
    _set_profile(seeded_engine, uid, "advanced", "gym")
    _add_injury(seeded_engine, uid, "shoulder impingement", "shoulders", "mild")
    bench = await _exercise_id(client, h, "Barbell bench press")
    names = {a["name"] for a in (await client.get(f"/api/v1/exercises/{bench}/alternatives", headers=h)).json()}
    assert {"Machine chest press", "Incline dumbbell press", "Cable crossover"} <= names  # shoulders only secondary
    assert "Dumbbell fly" not in names  # but the explicit list for the injury type still applies


async def test_alternatives_of_another_users_injuries_are_not_applied(client, seeded_engine):
    _, other_email = await _register(client)
    _add_injury(seeded_engine, _user_id(seeded_engine, other_email), "shoulder impingement", "shoulders", "severe")
    h = await _auth(client)  # a different user without injuries
    bench = await _exercise_id(client, h, "Barbell bench press")
    names = {a["name"] for a in (await client.get(f"/api/v1/exercises/{bench}/alternatives", headers=h)).json()}
    assert "Dumbbell fly" in names and "Machine chest press" in names


# ------------------------------------------------------------------ foods

async def test_food_list_search_filters_and_pagination(client):
    h = await _auth(client)
    page = (await client.get("/api/v1/foods?limit=15", headers=h)).json()
    assert page["total"] >= 150 and len(page["items"]) == 15 and page["limit"] == 15
    next_page = (await client.get("/api/v1/foods?limit=15&offset=15", headers=h)).json()
    assert not {f["id"] for f in page["items"]} & {f["id"] for f in next_page["items"]}
    assert set(page["items"][0]) == {"id", "name", "calories_per_100g", "protein_per_100g", "fat_per_100g",
                                     "carbs_per_100g", "role", "default_portion_g"}
    r = (await client.get("/api/v1/foods?q=CHICKEN&limit=100", headers=h)).json()
    assert r["total"] >= 3 and all("chicken" in f["name"].lower() for f in r["items"])
    r = (await client.get("/api/v1/foods?role=fruit&limit=100", headers=h)).json()
    assert r["total"] >= 15 and all(f["role"] == "fruit" for f in r["items"])
    cats = {c["name"]: c["id"] for c in (await client.get("/api/v1/food-categories", headers=h)).json()}
    r = (await client.get(f"/api/v1/foods?category_id={cats['dairy']}&limit=100", headers=h)).json()
    assert r["total"] >= 10 and "Cheddar" in {f["name"] for f in r["items"]}
    r = (await client.get("/api/v1/foods?q=chicken&role=fruit", headers=h)).json()
    assert r["total"] == 0  # filters combine with AND


async def test_food_detail_has_per_100g_values_categories_and_allergens(client):
    h = await _auth(client)
    found = (await client.get("/api/v1/foods?q=Cheddar", headers=h)).json()["items"]
    food = (await client.get(f"/api/v1/foods/{found[0]['id']}", headers=h)).json()
    assert food["name"] == "Cheddar" and food["calories_per_100g"] == 403 and food["protein_per_100g"] == 25
    assert [a["name"] for a in food["allergens"]] == ["milk"]
    assert [c["name"] for c in food["categories"]] == ["dairy"]
    assert food["is_vegetarian"] is True and food["is_vegan"] is False
    assert food["min_portion_g"] <= food["default_portion_g"] <= food["max_portion_g"] and food["portion_step_g"] > 0
    vegan = (await client.get("/api/v1/foods?q=Tofu", headers=h)).json()["items"][0]
    assert (await client.get(f"/api/v1/foods/{vegan['id']}", headers=h)).json()["is_vegan"] is True


async def test_inactive_foods_are_hidden(client, seeded_engine):
    h = await _auth(client)
    item = (await client.get("/api/v1/foods?q=Honey", headers=h)).json()["items"][0]
    with seeded_engine.begin() as c:
        c.execute(text("update food_item set is_active = false where id = :i"), {"i": item["id"]})
    try:
        assert (await client.get(f"/api/v1/foods/{item['id']}", headers=h)).status_code == 404
        assert (await client.get("/api/v1/foods?q=Honey", headers=h)).json()["total"] == 0
    finally:
        with seeded_engine.begin() as c:
            c.execute(text("update food_item set is_active = true where id = :i"), {"i": item["id"]})
