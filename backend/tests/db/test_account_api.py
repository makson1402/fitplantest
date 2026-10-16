"""B-05: account settings and the erasure of an account with all its data, against real PostgreSQL and MongoDB."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core.config import Settings
from app.core.security import create_access_token
from app.db.mongo import COLLECTION, create_mongo_client
from app.main import create_app
from app.repositories.recognitions import MongoRecognitionRepository
from tests.db.test_mongo_buffer import _item, _mongo_url
from tests.support import NO_STORES

BASE = "/api/v1"
PASSWORD = "Secret123"
SECRET = "test-secret-" + "x" * 32
PROFILE = {"age": 30, "sex": "male", "weight_kg": 80, "height_cm": 180, "activity_level_pal": 1.55,
           "goal": "muscle_gain", "experience_level": "advanced", "equipment": "gym"}


def _settings(seeded_engine, **extra) -> Settings:
    url = seeded_engine.url.render_as_string(hide_password=False)
    values = {"jwt_secret": SECRET, "bcrypt_rounds": 4, "auth_rate_limit": 10_000, **NO_STORES, "database_url": url}
    return Settings(_env_file=None, **{**values, **extra})


@pytest_asyncio.fixture
async def client(seeded_engine):
    app = create_app(_settings(seeded_engine))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        yield http
    await app.state.db_engine.dispose()


async def _register(client, email: str | None = None) -> tuple[dict, str, dict]:
    email = email or f"{uuid.uuid4().hex[:10]}@example.com"
    pair = (await client.post(f"{BASE}/auth/register", json={"email": email, "password": PASSWORD})).json()
    return {"Authorization": f"Bearer {pair['access_token']}"}, email, pair


# ------------------------------------------------------------------ GET and PATCH /users/me

async def test_every_route_requires_a_token(client):
    for method, path in [("get", "/users/me"), ("patch", "/users/me"), ("post", "/users/me/email"),
                         ("post", "/users/me/password"), ("post", "/users/me/delete")]:
        assert (await client.request(method, BASE + path, json={})).status_code == 401, path


async def test_me_shows_the_account_and_whether_onboarding_is_done(client):
    h, email, _ = await _register(client, "Jan.Kowalski@Example.com")
    me = (await client.get(f"{BASE}/users/me", headers=h)).json()
    assert me["email"] == "jan.kowalski@example.com" and me["timezone"] == "UTC" and me["has_profile"] is False
    assert me["name"] is None and me["surname"] is None and me["id"] > 0 and me["created_at"]
    assert set(me) == {"id", "email", "name", "surname", "timezone", "has_profile", "created_at"}  # no password hash
    await client.put(f"{BASE}/users/me/profile", json=PROFILE, headers=h)
    assert (await client.get(f"{BASE}/users/me", headers=h)).json()["has_profile"] is True


async def test_patch_changes_only_the_fields_sent(client):
    h, _, _ = await _register(client)
    r = await client.patch(f"{BASE}/users/me", headers=h, json={"name": "  Jan ", "surname": "Kowalski",
                                                                "timezone": "Europe/Warsaw"})
    assert r.status_code == 200 and (r.json()["name"], r.json()["surname"], r.json()["timezone"]) == (
        "Jan", "Kowalski", "Europe/Warsaw")
    r = await client.patch(f"{BASE}/users/me", headers=h, json={"surname": None})            # cleared
    assert r.json()["surname"] is None and r.json()["name"] == "Jan" and r.json()["timezone"] == "Europe/Warsaw"
    assert (await client.patch(f"{BASE}/users/me", headers=h, json={"name": "   "})).json()["name"] is None
    assert (await client.patch(f"{BASE}/users/me", headers=h, json={})).status_code == 200   # nothing to change
    assert (await client.get(f"{BASE}/users/me", headers=h)).json()["timezone"] == "Europe/Warsaw"


async def test_patch_validation(client):
    h, _, _ = await _register(client)
    for body, field in [({"timezone": "Mars/Olympus"}, "timezone"), ({"timezone": None}, "timezone"),
                        ({"timezone": 5}, "timezone"), ({"name": "x" * 101}, "name"),
                        ({"surname": "x" * 101}, "surname"), ({"name": 5}, "name")]:
        r = await client.patch(f"{BASE}/users/me", headers=h, json=body)
        assert r.status_code == 422 and r.json()["details"][0]["field"] == field, body
    assert (await client.patch(f"{BASE}/users/me", headers=h, json={"name": "x" * 100})).status_code == 200


async def test_the_time_zone_drives_the_users_today(client):
    """A stored time zone is used for 'today' (accepting a plan): Kiritimati is a day ahead of most of the world."""
    h, _, _ = await _register(client)
    await client.put(f"{BASE}/users/me/profile", json=PROFILE, headers=h)
    await client.patch(f"{BASE}/users/me", headers=h, json={"timezone": "Pacific/Kiritimati"})
    plan = (await client.post(f"{BASE}/training-plans/generate", headers=h,
                              json={"goal": "strength", "training_days": 2})).json()
    accepted = (await client.post(f"{BASE}/training-plans/{plan['id']}/accept", headers=h)).json()
    from zoneinfo import ZoneInfo
    assert accepted["start_date"] == datetime.now(ZoneInfo("Pacific/Kiritimati")).date().isoformat()


# ------------------------------------------------------------------ change email

async def test_change_email(client):
    h, old, pair = await _register(client)
    wrong = await client.post(f"{BASE}/users/me/email", headers=h,
                              json={"new_email": "new@example.com", "current_password": "Wrong123x"})
    assert wrong.status_code == 401 and wrong.json()["code"] == "invalid_credentials"
    assert (await client.get(f"{BASE}/users/me", headers=h)).json()["email"] == old        # unchanged
    new = f"New.{uuid.uuid4().hex[:8]}@Example.com"
    r = await client.post(f"{BASE}/users/me/email", headers=h, json={"new_email": new, "current_password": PASSWORD})
    assert r.status_code == 200 and r.json()["email"] == new.lower()
    assert (await client.post(f"{BASE}/auth/login", json={"email": new, "password": PASSWORD})).status_code == 200
    assert (await client.post(f"{BASE}/auth/login", json={"email": old, "password": PASSWORD})).status_code == 401
    assert (await client.post(f"{BASE}/auth/refresh", json={"refresh_token": pair["refresh_token"]})
            ).status_code == 200                                                              # sessions are kept


async def test_change_email_conflicts_and_validation(client):
    h, mine, _ = await _register(client)
    _, taken, _ = await _register(client)
    body = {"current_password": PASSWORD}
    r = await client.post(f"{BASE}/users/me/email", headers=h, json={**body, "new_email": taken.upper()})
    assert r.status_code == 409 and r.json()["code"] == "email_taken"
    same = await client.post(f"{BASE}/users/me/email", headers=h, json={**body, "new_email": mine})
    assert same.status_code == 200 and same.json()["email"] == mine                          # nothing to change
    for payload, field in [({"new_email": "not-an-email", **body}, "new_email"), ({"current_password": PASSWORD},
                           "new_email"), ({"new_email": "x@example.com"}, "current_password")]:
        r = await client.post(f"{BASE}/users/me/email", headers=h, json=payload)
        assert r.status_code == 422 and r.json()["details"][0]["field"] == field, payload


# ------------------------------------------------------------------ change password

async def test_change_password_signs_out_the_other_sessions(client):
    h, email, pair = await _register(client)
    wrong = await client.post(f"{BASE}/users/me/password", headers=h,
                              json={"current_password": "Wrong123x", "new_password": "Brand1New"})
    assert wrong.status_code == 401 and wrong.json()["code"] == "invalid_credentials"
    r = await client.post(f"{BASE}/users/me/password", headers=h,
                          json={"current_password": PASSWORD, "new_password": "Brand1New"})
    assert r.status_code == 204 and r.content == b""
    assert (await client.post(f"{BASE}/auth/login", json={"email": email, "password": PASSWORD})).status_code == 401
    assert (await client.post(f"{BASE}/auth/login", json={"email": email, "password": "Brand1New"})
            ).status_code == 200
    assert (await client.post(f"{BASE}/auth/refresh", json={"refresh_token": pair["refresh_token"]})
            ).status_code == 401                                                              # revoked
    assert (await client.get(f"{BASE}/users/me", headers=h)).status_code == 200              # until it expires


async def test_new_password_rules(client):
    h, _, _ = await _register(client)
    for new, why in [("short1", "too short"), ("nodigitsatall", "no digit"), ("12345678", "no letter"),
                     ("a1" * 40, "more than 72 characters"), ("é1" * 37, "73 bytes")]:
        r = await client.post(f"{BASE}/users/me/password", headers=h,
                              json={"current_password": PASSWORD, "new_password": new})
        assert r.status_code == 422 and r.json()["details"][0]["field"] == "new_password", why
    assert (await client.post(f"{BASE}/users/me/password", headers=h,
                              json={"current_password": PASSWORD, "new_password": "a1" * 36})).status_code == 204


async def test_password_checks_are_rate_limited(seeded_engine):
    app = create_app(_settings(seeded_engine, auth_rate_limit=3))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        h, _, _ = await _register(http)
        statuses = [(await http.post(f"{BASE}/users/me/password", headers=h,
                                     json={"current_password": "Wrong123x", "new_password": "Brand1New"})).status_code
                    for _ in range(5)]
    await app.state.db_engine.dispose()
    assert statuses[:2] == [401, 401] and 429 in statuses                                    # register used one hit


# ------------------------------------------------------------------ delete: input

async def test_delete_needs_confirmation_and_the_password(client):
    h, email, _ = await _register(client)
    url = f"{BASE}/users/me/delete"
    for body, field in [({}, "confirmation"), ({"confirmation": "delete", "current_password": PASSWORD}, "confirmation"),
                        ({"confirmation": "yes", "current_password": PASSWORD}, "confirmation"),
                        ({"confirmation": "DELETE"}, "current_password"),
                        ({"confirmation": "DELETE", "current_password": ""}, "current_password")]:
        r = await client.post(url, headers=h, json=body)
        assert r.status_code == 422 and r.json()["details"][0]["field"] == field, body
    wrong = await client.post(url, headers=h, json={"confirmation": "DELETE", "current_password": "Wrong123x"})
    assert wrong.status_code == 401
    assert (await client.get(f"{BASE}/users/me", headers=h)).status_code == 200              # still there
    assert (await client.post(f"{BASE}/auth/login", json={"email": email, "password": PASSWORD})).status_code == 200


# ------------------------------------------------------------------ delete: everything goes

USER_ID_TABLES_SQL = ("select table_name from information_schema.columns where table_schema = 'public'"
                      " and column_name = 'user_id' order by table_name")


async def _populate(client, h) -> dict:
    """Give the user rows in every part of the application."""
    await client.put(f"{BASE}/users/me/profile", json=PROFILE, headers=h)
    groups = {g["name"]: g["id"] for g in (await client.get(f"{BASE}/muscle-groups", headers=h)).json()}
    types = {t["name"]: t["id"] for t in (await client.get(f"{BASE}/injury-types", headers=h)).json()}
    allergens = {a["name"]: a["id"] for a in (await client.get(f"{BASE}/allergens", headers=h)).json()}
    await client.post(f"{BASE}/users/me/injuries", headers=h, json={
        "injury_type_id": types["wrist sprain"], "affected_muscle_group_id": groups["biceps"], "severity": "mild",
        "start_date": "2026-09-01"})
    await client.put(f"{BASE}/users/me/allergies", headers=h, json={"allergen_ids": [allergens["sesame"]]})
    foods = (await client.get(f"{BASE}/foods?q=Banana", headers=h)).json()["items"]
    await client.put(f"{BASE}/users/me/excluded-foods", headers=h, json={"food_item_ids": [foods[0]["id"]]})
    plan = (await client.post(f"{BASE}/training-plans/generate", headers=h,
                              json={"goal": "strength", "training_days": 3})).json()
    plan = (await client.post(f"{BASE}/training-plans/{plan['id']}/accept", headers=h)).json()
    await client.post(f"{BASE}/training-plans/generate", headers=h, json={"goal": "strength", "training_days": 2})
    session = plan["sessions"][0]
    planned = next(e for e in session["exercises"] if not e["exercise"]["is_bodyweight"])
    await client.patch(f"{BASE}/session-exercises/{planned['id']}", headers=h, json={"planned_weight_kg": 60})
    today = datetime.now(UTC).date().isoformat()
    sets = [{"exercise_id": planned["exercise"]["id"], "session_exercise_id": planned["id"], "set_number": i,
             "reps": 5, "weight_kg": 60, "rpe": 6} for i in (1, 2, 3)]
    workout = await client.post(f"{BASE}/workouts", headers=h, json={
        "training_session_id": session["id"], "performed_on": today, "overall_rpe": 9, "sets": sets})  # reduce signal
    assert workout.json()["adjustments"] and workout.json()["new_personal_records"]            # adaptation and a record
    await client.post(f"{BASE}/body-metrics", headers=h, json={"measured_on": today, "weight_kg": 79})
    diet = (await client.post(f"{BASE}/diet-plans/generate", json={"meals_per_day": 3}, headers=h)).json()
    await client.post(f"{BASE}/diet-plans/{diet['id']}/accept", headers=h)
    meal = diet["meals"][0]
    await client.post(f"{BASE}/nutrition-logs", headers=h, json={
        "log_date": today, "meal_type": meal["meal_type"], "planned_meal_id": meal["id"],
        "items": [{"food_item_id": i["food"]["id"], "grams": i["grams"]} for i in meal["items"]]})
    return {"plan_ids": [plan["id"]]}


def _insert_misc(engine, user_id: int) -> None:
    """Rows that no endpoint creates yet: reset token, social identity, reminder, notification, push token, report."""
    with engine.begin() as c:
        c.execute(text("insert into password_reset_token (user_id, token_hash, expires_at) values (:u, :h, now())"),
                  {"u": user_id, "h": uuid.uuid4().hex})
        c.execute(text("insert into oauth_identity (user_id, provider, provider_subject) values (:u, 'google', :s)"),
                  {"u": user_id, "s": uuid.uuid4().hex})
        c.execute(text("insert into reminder (user_id, type, weekdays, time_of_day) values (:u, 'training_reminder',"
                       " '{mon}', '07:00')"), {"u": user_id})
        c.execute(text("insert into notification (user_id, type, title, message) values (:u, 'achievement', 't', 'm')"),
                  {"u": user_id})
        c.execute(text("insert into device_push_token (user_id, token, platform) values (:u, :t, 'android')"),
                  {"u": user_id, "t": uuid.uuid4().hex})
        c.execute(text("insert into progress_report (user_id, report_type, period_start, period_end)"
                       " values (:u, 'weekly', current_date - 7, current_date)"), {"u": user_id})
        c.execute(text("insert into recognition_ai (user_id, image_url, model_name, uploaded_at, recognized_items,"
                       " estimated_calories, estimated_protein_g, estimated_fat_g, estimated_carbs_g, confidence_score,"
                       " was_edited) values (:u, 'x', 'm', now(), '[]', 1, 1, 1, 1, 0.9, false)"), {"u": user_id})


def _counts(engine, user_id: int) -> dict[str, int]:
    with engine.connect() as c:
        tables = [r[0] for r in c.execute(text(USER_ID_TABLES_SQL))]
        direct = {t: c.execute(text(f"select count(*) from {t} where user_id = :u"), {"u": user_id}).scalar_one()  # noqa: S608
                  for t in tables}
        indirect = {
            "training_session": "select count(*) from training_session s join training_plan p on p.id = s.training_plan_id where p.user_id = :u",
            "session_exercise": "select count(*) from session_exercise e join training_session s on s.id = e.training_session_id join training_plan p on p.id = s.training_plan_id where p.user_id = :u",
            "plan_adjustment": "select count(*) from plan_adjustment a join session_exercise e on e.id = a.session_exercise_id join training_session s on s.id = e.training_session_id join training_plan p on p.id = s.training_plan_id where p.user_id = :u",
            "workout_set_log": "select count(*) from workout_set_log s join workout_log w on w.id = s.workout_log_id where w.user_id = :u",
            "meal": "select count(*) from meal m join diet_plan p on p.id = m.diet_plan_id where p.user_id = :u",
            "meal_food_item": "select count(*) from meal_food_item i join meal m on m.id = i.meal_id join diet_plan p on p.id = m.diet_plan_id where p.user_id = :u",
            "nutrition_log_food_item": "select count(*) from nutrition_log_food_item i join nutrition_log n on n.id = i.nutrition_log_id where n.user_id = :u",
        }
        direct.update({name: c.execute(text(sql), {"u": user_id}).scalar_one() for name, sql in indirect.items()})
        direct["users"] = c.execute(text("select count(*) from users where id = :u"), {"u": user_id}).scalar_one()
    return direct


async def test_deleting_an_account_leaves_no_data_in_postgres(client, seeded_engine):
    """Done when (B-05): a data audit finds nothing for the user in any table, direct or indirect."""
    h, email, pair = await _register(client)
    other_h, _, _ = await _register(client)
    await _populate(client, other_h)                                                          # a neighbour who stays
    await _populate(client, h)
    user_id = (await client.get(f"{BASE}/users/me", headers=h)).json()["id"]
    other_id = (await client.get(f"{BASE}/users/me", headers=other_h)).json()["id"]
    _insert_misc(seeded_engine, user_id)

    before, neighbour = _counts(seeded_engine, user_id), _counts(seeded_engine, other_id)
    assert all(before[t] > 0 for t in (
        "users", "user_profile", "injury", "user_allergen", "user_excluded_food", "training_plan", "training_session",
        "session_exercise", "plan_adjustment", "workout_log", "workout_set_log", "personal_record", "body_metrics",
        "diet_plan", "meal", "meal_food_item", "nutrition_log", "nutrition_log_food_item", "refresh_token",
        "password_reset_token", "oauth_identity", "reminder", "notification", "device_push_token", "progress_report",
        "recognition_ai")), {k: v for k, v in before.items() if v == 0}                      # the audit has teeth

    r = await client.post(f"{BASE}/users/me/delete", headers=h, json={"confirmation": "DELETE",
                                                                      "current_password": PASSWORD})
    assert r.status_code == 204 and r.content == b""

    after = _counts(seeded_engine, user_id)
    assert all(v == 0 for v in after.values()), {k: v for k, v in after.items() if v}
    assert _counts(seeded_engine, other_id) == neighbour                                      # nobody else was touched
    # the account is gone for every credential
    assert (await client.get(f"{BASE}/users/me", headers=h)).status_code == 401
    assert (await client.post(f"{BASE}/auth/login", json={"email": email, "password": PASSWORD})).status_code == 401
    assert (await client.post(f"{BASE}/auth/refresh", json={"refresh_token": pair["refresh_token"]})
            ).status_code == 401
    again = await client.post(f"{BASE}/users/me/delete", headers=h, json={"confirmation": "DELETE",
                                                                         "current_password": PASSWORD})
    assert again.status_code == 401
    # the email is free again and the new account starts empty
    fresh_h, _, _ = await _register(client, email)
    fresh = (await client.get(f"{BASE}/users/me", headers=fresh_h)).json()
    assert fresh["id"] != user_id and fresh["has_profile"] is False
    assert (await client.get(f"{BASE}/training-plans/active", headers=fresh_h)).status_code == 404
    assert (await client.get(f"{BASE}/workouts", headers=fresh_h)).json()["total"] == 0


@pytest_asyncio.fixture
async def stores(seeded_engine, tmp_path):
    """An app with MongoDB and a photo directory, like production."""
    probe = create_mongo_client(_mongo_url())
    try:
        await probe.admin.command("ping")
    except Exception as exc:  # noqa: BLE001
        await probe.close()
        pytest.skip(f"MongoDB is not reachable: {exc.__class__.__name__}")
    await probe.close()
    database = f"fitplan_test_{uuid.uuid4().hex[:8]}"
    app = create_app(_settings(seeded_engine, mongo_url=_mongo_url(), mongo_db=database, photo_dir=str(tmp_path)))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        yield http, app, tmp_path
    await app.state.mongo_client.drop_database(database)
    await app.state.mongo_client.close()
    await app.state.db_engine.dispose()


async def test_deleting_an_account_removes_recognitions_and_photos(stores):
    client, app, photos = stores
    h, _, _ = await _register(client)
    other_h, _, _ = await _register(client)
    user_id = (await client.get(f"{BASE}/users/me", headers=h)).json()["id"]
    other_id = (await client.get(f"{BASE}/users/me", headers=other_h)).json()["id"]
    repo, now = MongoRecognitionRepository(app.state.mongo_db), datetime.now(UTC)

    async def pending(uid: int, name: str) -> str:
        relative = f"meals/{uid}/{name}.jpg"
        (photos / "meals" / str(uid)).mkdir(parents=True, exist_ok=True)
        (photos / relative).write_bytes(b"jpeg")
        await repo.create(user_id=uid, meal_type="lunch", photo_path=relative, model_name="m", model_version="1",
                          overall_confidence=0.9, items=[_item()], now=now)
        return relative

    mine = [await pending(user_id, "a"), await pending(user_id, "b")]
    theirs = await pending(other_id, "c")
    outside = photos.parent / f"{uuid.uuid4().hex}.keep"
    outside.write_bytes(b"not a photo")
    assert await app.state.mongo_db[COLLECTION].count_documents({"userId": user_id}) == 2

    r = await client.post(f"{BASE}/users/me/delete", headers=h, json={"confirmation": "DELETE",
                                                                      "current_password": PASSWORD})
    assert r.status_code == 204
    assert await app.state.mongo_db[COLLECTION].count_documents({"userId": user_id}) == 0   # the buffer is gone
    assert not any((photos / p).exists() for p in mine) and not (photos / "meals" / str(user_id)).exists()
    assert (photos / theirs).exists() and await app.state.mongo_db[COLLECTION].count_documents({"userId": other_id}) == 1
    assert outside.exists()                                                                   # nothing outside the root
    outside.unlink()


def test_photo_removal_never_leaves_the_photo_directory(tmp_path):
    from app.services.account import remove_photos
    root = tmp_path / "photos"
    (root / "meals" / "7").mkdir(parents=True)
    (root / "meals" / "7" / "a.jpg").write_bytes(b"x")
    (root / "meals" / "8").mkdir(parents=True)
    (root / "meals" / "8" / "b.jpg").write_bytes(b"x")
    secret = tmp_path / "secret.txt"
    secret.write_text("keep")
    remove_photos(str(root), 7, ["../secret.txt", "meals/8/b.jpg", "../../etc/passwd", "meals/7/missing.jpg"])
    assert not (root / "meals" / "7").exists() and secret.exists()
    assert not (root / "meals" / "8" / "b.jpg").exists()           # a listed file below the root is removed
    remove_photos(None, 7, ["x"])                                   # no photo directory configured: nothing happens
    remove_photos(str(tmp_path / "does-not-exist"), 7, [])          # a missing directory is not an error
    assert Path(root).exists()


# ------------------------------------------------------------------ accounts without a password

async def test_an_account_without_a_password(client, seeded_engine):
    """Social sign-in accounts have no password: they can delete themselves, but password changes do not apply."""
    email = f"{uuid.uuid4().hex[:10]}@example.com"
    with seeded_engine.begin() as c:
        user_id = c.execute(text("insert into users (email) values (:e) returning id"), {"e": email}).scalar_one()
    token = create_access_token(user_id, datetime.now(UTC), 900, SECRET, "HS256")
    h = {"Authorization": f"Bearer {token}"}
    assert (await client.get(f"{BASE}/users/me", headers=h)).json()["email"] == email
    for path, body in [("/users/me/email", {"new_email": "x@example.com", "current_password": "whatever1"}),
                       ("/users/me/password", {"current_password": "whatever1", "new_password": "Brand1New"})]:
        r = await client.post(BASE + path, headers=h, json=body)
        assert r.status_code == 422 and r.json()["details"][0]["code"] == "no_password", path
    assert (await client.post(f"{BASE}/users/me/delete", headers=h, json={"confirmation": "DELETE"})).status_code == 204
    assert (await client.get(f"{BASE}/users/me", headers=h)).status_code == 401
