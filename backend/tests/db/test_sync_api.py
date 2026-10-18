"""B-27: offline sync (push and pull) against a real, seeded PostgreSQL. Design: D-07, docs/api/openapi.yaml `sync`."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import pytest_asyncio

from app.core.config import Settings
from app.main import create_app
from app.repositories.sync import SyncPosition
from app.services.sync import decode_cursor, encode_cursor
from tests.db.test_analytics_api import _exercise_ids, _food, _user, day
from tests.support import NO_STORES

BASE = "/api/v1"
PROFILE = {"age": 30, "sex": "male", "weight_kg": 80, "height_cm": 180, "activity_level_pal": 1.55,
           "goal": "strength", "experience_level": "intermediate", "equipment": "gym"}


@pytest_asyncio.fixture
async def client(seeded_engine):
    url = seeded_engine.url.render_as_string(hide_password=False)
    settings = Settings(jwt_secret="test-secret-" + "x" * 32, bcrypt_rounds=4, auth_rate_limit=10_000,
                        _env_file=None, **{**NO_STORES, "database_url": url})
    app = create_app(settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        yield http
    await app.state.db_engine.dispose()


def new_id() -> str:
    return str(uuid.uuid4())


def workout(exercise_id: int, offset: int = 1, **extra) -> dict:
    return {"client_uuid": new_id(), "performed_on": day(offset).isoformat(),
            "sets": [{"exercise_id": exercise_id, "set_number": 1, "reps": 5, "weight_kg": 100}], **extra}


def meal(food_id: int, offset: int = 1, **extra) -> dict:
    return {"client_uuid": new_id(), "log_date": day(offset).isoformat(), "meal_type": "lunch",
            "items": [{"food_item_id": food_id, "grams": 100}], **extra}


def measurement(offset: int = 1, weight: float = 80.0, **extra) -> dict:
    return {"client_uuid": new_id(), "measured_on": day(offset).isoformat(), "weight_kg": weight, **extra}


async def push(client, h, *, workouts=None, logs=None, metrics=None, status: int = 200) -> dict:
    body = {k: v for k, v in (("workouts", workouts), ("nutrition_logs", logs), ("body_metrics", metrics))
            if v is not None}
    r = await client.post(f"{BASE}/sync/push", headers=h, json=body)
    assert r.status_code == status, r.text
    return r.json()


async def pull(client, h, cursor: str | None = None, limit: int | None = None) -> dict:
    params = {k: v for k, v in (("cursor", cursor), ("limit", limit)) if v is not None}
    r = await client.get(f"{BASE}/sync/pull", headers=h, params=params)
    assert r.status_code == 200, r.text
    return r.json()


async def pull_all(client, h, limit: int) -> tuple[list[dict], str]:
    """Pages through the whole stream; returns (all items as (kind, item), the last cursor)."""
    items, cursor = [], None
    for _ in range(50):
        page = await pull(client, h, cursor, limit)
        items += [("workout", x) for x in page["workouts"]] + [("log", x) for x in page["nutrition_logs"]]
        items += [("metrics", x) for x in page["body_metrics"]]
        cursor = page["cursor"]
        if not page["has_more"]:
            return items, cursor
    raise AssertionError("pull did not finish")


async def setup(client) -> tuple[dict, int, int]:
    h = await _user(client, PROFILE)
    return h, (await _exercise_ids(client, h, 1))[0], await _food(client, h, "Olive oil")


def statuses(response: dict) -> list[str]:
    return [r["status"] for r in response["results"]]


# ------------------------------------------------------------------ protocol basics

async def test_authentication_and_input_validation(client):
    assert (await client.post(f"{BASE}/sync/push", json={})).status_code == 401
    assert (await client.get(f"{BASE}/sync/pull")).status_code == 401
    h, ex, food = await setup(client)
    empty = await push(client, h)                                                    # an empty push is fine
    assert empty["results"] == [] and decode_cursor(empty["cursor"]).rank == 0
    bad_push = [{"workouts": [{"performed_on": day(1).isoformat(), "sets": [{"exercise_id": ex, "set_number": 1,
                                                                            "reps": 5}]}]},          # no client_uuid
                {"workouts": "all"}, {"body_metrics": [{"client_uuid": "nope", "measured_on": "2026-01-01",
                                                        "weight_kg": 80}]}]
    for body in bad_push:
        r = await client.post(f"{BASE}/sync/push", headers=h, json=body)
        assert r.status_code == 422 and r.json()["code"] == "validation_error", body
    too_many = [measurement(offset=i + 1) for i in range(201)]
    r = await client.post(f"{BASE}/sync/push", headers=h, json={"body_metrics": too_many})
    assert r.status_code == 422
    for query in ("?limit=0", "?limit=501", "?cursor=garbage", "?cursor=", "?cursor=e30"):
        r = await client.get(f"{BASE}/sync/pull{query}", headers=h)
        if query == "?cursor=":
            assert r.status_code == 200          # an empty cursor is no cursor
        else:
            assert r.status_code == 422, query


def test_cursors_round_trip_and_reject_forgeries():
    position = SyncPosition(datetime(2026, 10, 15, 12, 30, 45, 123456, tzinfo=UTC), 1, 42)
    assert decode_cursor(encode_cursor(position)) == position
    for forged in ("", "abc", "e30", encode_cursor(position)[:-4], "eyJ0IjoiMjAyNi0xMC0xNVQxMjowMDowMCIsInIiOjAsImkiOjF9"):
        try:
            decode_cursor(forged)
        except Exception as exc:  # noqa: BLE001
            assert type(exc).__name__ == "AppError", forged
        else:
            raise AssertionError(f"accepted {forged!r}")                    # the last one has no time zone


async def test_replaying_a_push_changes_nothing(client):
    h, ex, food = await setup(client)
    w, m, a = workout(ex), meal(food), measurement()
    first = await push(client, h, workouts=[w], logs=[m], metrics=[a])
    assert statuses(first) == ["applied"] * 3
    assert [r["type"] for r in first["results"]] == ["workout", "nutrition_log", "body_metrics"]
    assert all(r["server_id"] and r["server_updated_at"] and r["error"] is None and r["server_copy"] is None
               for r in first["results"])
    second = await push(client, h, workouts=[w], logs=[m], metrics=[a])
    assert statuses(second) == ["unchanged"] * 3
    assert [(r["server_id"], r["server_updated_at"]) for r in second["results"]] == [
        (r["server_id"], r["server_updated_at"]) for r in first["results"]]       # nothing was touched
    for _ in range(2):
        await push(client, h, workouts=[w], logs=[m], metrics=[a])
    assert (await client.get(f"{BASE}/workouts", headers=h)).json()["total"] == 1
    assert (await client.get(f"{BASE}/nutrition-logs", headers=h)).json()["total"] == 1
    assert len((await client.get(f"{BASE}/body-metrics", headers=h)).json()) == 1
    items, _ = await pull_all(client, h, 200)
    assert len(items) == 3


async def test_a_rejected_item_does_not_stop_the_others(client):
    h, ex, food = await setup(client)
    good_w, bad_w = workout(ex), workout(2**30)                                   # unknown exercise
    bad_m = measurement(offset=-30)                                               # in the future
    good_m = measurement()
    response = await push(client, h, workouts=[bad_w, good_w], metrics=[bad_m, good_m])
    assert statuses(response) == ["rejected", "applied", "rejected", "applied"]
    bad = response["results"][0]
    assert bad["error"]["code"] == "validation_error" and bad["error"]["details"][0]["field"] == "sets.0.exercise_id"
    assert bad["server_id"] is None and bad["server_copy"] is None
    assert response["results"][2]["error"]["details"][0]["field"] == "measured_on"
    items, _ = await pull_all(client, h, 200)
    assert len(items) == 2                                                        # only the valid ones are stored
    again = await push(client, h, workouts=[bad_w])                               # a rejected item may be retried
    assert statuses(again) == ["rejected"]


async def test_a_synced_workout_does_not_adapt_the_plan(client):
    h, ex, _ = await setup(client)
    plan = (await client.post(f"{BASE}/training-plans/generate", headers=h,
                              json={"goal": "strength", "training_days": 3})).json()
    await client.post(f"{BASE}/training-plans/{plan['id']}/accept", headers=h, json={})
    session = plan["sessions"][0]
    planned = session["exercises"][0]

    def failed_sets(offset: int) -> dict:
        return {"client_uuid": new_id(), "performed_on": day(offset).isoformat(), "training_session_id": session["id"],
                "overall_rpe": 10, "sets": [{"exercise_id": planned["exercise"]["id"],
                                              "session_exercise_id": planned["id"], "set_number": n, "reps": 3,
                                              "weight_kg": 50, "rpe": 10, "completed": n == 1} for n in (1, 2)]}

    before = (await client.get(f"{BASE}/training-plans/active", headers=h)).json()["sessions"][0]["exercises"][0]
    assert statuses(await push(client, h, workouts=[failed_sets(2)])) == ["applied"]
    after = (await client.get(f"{BASE}/training-plans/active", headers=h)).json()["sessions"][0]["exercises"][0]
    assert (after["planned_sets"], after["planned_reps"], after["planned_weight_kg"]) == (
        before["planned_sets"], before["planned_reps"], before["planned_weight_kg"])      # no adaptation by sync
    online = await client.post(f"{BASE}/workouts", headers=h, json=failed_sets(1))        # the same signal online
    assert online.status_code == 201 and online.json()["adjustments"]                     # does change the plan


# ------------------------------------------------------------------ conflicts (server wins) and convergence

async def test_two_devices_editing_a_measurement_converge(client):
    h, *_ = await setup(client)
    original = measurement(weight=80.0)
    created = (await push(client, h, metrics=[original]))["results"][0]
    t0 = created["server_updated_at"]                                              # both devices pull this version

    edit_a = {**original, "weight_kg": 79.0, "base_updated_at": t0}
    edit_b = {**original, "weight_kg": 81.5, "base_updated_at": t0}
    a = (await push(client, h, metrics=[edit_a]))["results"][0]
    assert a["status"] == "applied" and a["server_updated_at"] != t0
    b = (await push(client, h, metrics=[edit_b]))["results"][0]                    # device B pushes a stale edit
    assert b["status"] == "conflict" and b["server_updated_at"] == a["server_updated_at"]
    assert b["server_copy"]["weight_kg"] == 79.0 and b["server_copy"]["client_uuid"] == original["client_uuid"]
    assert b["server_copy"]["deleted_at"] is None and b["server_copy"]["id"] == created["server_id"]
    # B's retry of A's own edit (a lost response) is a no-op, not a conflict
    assert (await push(client, h, metrics=[edit_a]))["results"][0]["status"] == "unchanged"
    # B adopts the server copy, edits again on top of it and wins
    edit_b2 = {**original, "weight_kg": 78.0, "base_updated_at": b["server_updated_at"]}
    assert (await push(client, h, metrics=[edit_b2]))["results"][0]["status"] == "applied"
    items, _ = await pull_all(client, h, 200)
    assert [(k, x["weight_kg"]) for k, x in items] == [("metrics", 78.0)]          # one record, one final value


async def test_an_edit_without_a_base_of_a_stored_item_is_a_conflict(client):
    h, *_ = await setup(client)
    item = measurement(weight=80.0)
    await push(client, h, metrics=[item])
    r = (await push(client, h, metrics=[{**item, "weight_kg": 70.0}]))["results"][0]      # base_updated_at is null
    assert r["status"] == "conflict" and r["server_copy"]["weight_kg"] == 80.0


async def test_the_same_day_measured_on_two_devices_keeps_the_first(client):
    h, *_ = await setup(client)
    first = measurement(weight=80.0)
    second = measurement(weight=82.0)                                              # another client_uuid, same day
    await push(client, h, metrics=[first])
    result = (await push(client, h, metrics=[second]))["results"][0]
    assert result["status"] == "conflict" and result["server_copy"]["client_uuid"] == first["client_uuid"]
    assert result["server_copy"]["weight_kg"] == 80.0
    assert len((await client.get(f"{BASE}/body-metrics", headers=h)).json()) == 1
    # moving an existing measurement onto a day that is taken is a conflict too
    other_day = measurement(offset=2, weight=79.0)
    stored = (await push(client, h, metrics=[other_day]))["results"][0]
    r = (await push(client, h, metrics=[{**other_day, "measured_on": day(1).isoformat(),
                                         "base_updated_at": stored["server_updated_at"]}]))["results"][0]
    assert r["status"] == "conflict" and r["server_copy"]["client_uuid"] == first["client_uuid"]


async def test_logs_are_append_only(client):
    h, ex, food = await setup(client)
    w, m = workout(ex), meal(food)
    stored = await push(client, h, workouts=[w], logs=[m])
    edited_w = {**w, "sets": [{"exercise_id": ex, "set_number": 1, "reps": 12, "weight_kg": 20}],
                "base_updated_at": stored["results"][0]["server_updated_at"]}
    edited_m = {**m, "items": [{"food_item_id": food, "grams": 500}],
                "base_updated_at": stored["results"][1]["server_updated_at"]}
    result = await push(client, h, workouts=[edited_w], logs=[edited_m])
    assert statuses(result) == ["conflict", "conflict"]
    assert result["results"][0]["server_copy"]["sets"][0]["reps"] == 5               # the server version stands
    assert result["results"][1]["server_copy"]["items"][0]["grams"] == 100.0
    assert (await client.get(f"{BASE}/workouts", headers=h)).json()["items"][0]["sets"][0]["reps"] == 5


# ------------------------------------------------------------------ deletes and tombstones

async def test_deleting_leaves_a_tombstone_that_cannot_be_resurrected(client):
    h, ex, food = await setup(client)
    w, m, a = workout(ex), meal(food), measurement()
    stored = (await push(client, h, workouts=[w], logs=[m], metrics=[a]))["results"]
    base = {r["type"]: r["server_updated_at"] for r in stored}
    deletes = await push(
        client, h, workouts=[{**w, "deleted": True, "base_updated_at": base["workout"]}],
        logs=[{**m, "deleted": True, "base_updated_at": base["nutrition_log"]}],
        metrics=[{**a, "deleted": True, "base_updated_at": base["body_metrics"]}])
    assert statuses(deletes) == ["applied"] * 3
    assert all(r["server_updated_at"] > base[r["type"]] for r in deletes["results"])        # the delete is a change
    assert (await client.get(f"{BASE}/workouts", headers=h)).json()["total"] == 0
    assert (await client.get(f"{BASE}/body-metrics", headers=h)).json() == []
    # replaying the delete, or deleting what was never stored, changes nothing
    assert statuses(await push(client, h, workouts=[{**w, "deleted": True}], logs=[{**m, "deleted": True}],
                               metrics=[{**a, "deleted": True}])) == ["unchanged"] * 3
    assert statuses(await push(client, h, workouts=[{**workout(ex), "deleted": True}])) == ["unchanged"]
    # the tombstones arrive on pull
    items, _ = await pull_all(client, h, 200)
    assert len(items) == 3 and all(x["deleted_at"] is not None for _, x in items)
    # sending the deleted item as a live one is a conflict that carries the tombstone
    again = await push(client, h, workouts=[w], logs=[m], metrics=[a])
    assert statuses(again) == ["conflict"] * 3 and all(r["server_copy"]["deleted_at"] for r in again["results"])
    # the day of a deleted measurement is free again
    assert statuses(await push(client, h, metrics=[measurement(weight=77.0)])) == ["applied"]


async def test_a_stale_delete_is_a_conflict_and_a_delete_without_base_applies(client):
    h, ex, food = await setup(client)
    m1, m2 = measurement(offset=1), measurement(offset=2)
    s1 = (await push(client, h, metrics=[m1]))["results"][0]
    s2 = (await push(client, h, metrics=[m2]))["results"][0]
    edited = (await push(client, h, metrics=[{**m1, "weight_kg": 75.0, "base_updated_at": s1["server_updated_at"]}]))
    assert edited["results"][0]["status"] == "applied"                              # another device changed it
    stale = (await push(client, h, metrics=[{**m1, "deleted": True, "base_updated_at": s1["server_updated_at"]}]))
    assert stale["results"][0]["status"] == "conflict" and stale["results"][0]["server_copy"]["weight_kg"] == 75.0
    assert len((await client.get(f"{BASE}/body-metrics", headers=h)).json()) == 2   # nothing was deleted
    blind = await push(client, h, metrics=[{**m2, "deleted": True}])
    assert blind["results"][0]["status"] == "applied" and s2["server_id"] == blind["results"][0]["server_id"]


async def test_two_devices_deleting_the_same_workout_converge(client):
    h, ex, _ = await setup(client)
    w = workout(ex)
    t0 = (await push(client, h, workouts=[w]))["results"][0]["server_updated_at"]
    one = (await push(client, h, workouts=[{**w, "deleted": True, "base_updated_at": t0}]))["results"][0]
    two = (await push(client, h, workouts=[{**w, "deleted": True, "base_updated_at": t0}]))["results"][0]
    assert (one["status"], two["status"]) == ("applied", "unchanged")
    assert one["server_id"] == two["server_id"] and two["server_updated_at"] == one["server_updated_at"]


# ------------------------------------------------------------------ pull

async def test_pull_pages_through_everything_exactly_once(client):
    h, ex, food = await setup(client)
    await push(client, h, workouts=[workout(ex, o) for o in (1, 2, 3)], logs=[meal(food, o) for o in (1, 2, 3)],
               metrics=[measurement(o) for o in (1, 2, 3)])
    everything = await pull(client, h)
    assert (everything["has_more"], len(everything["workouts"]), len(everything["nutrition_logs"]),
            len(everything["body_metrics"])) == (False, 3, 3, 3)
    for limit in (1, 2, 4, 9, 10):
        items, _ = await pull_all(client, h, limit)
        ids = [(kind, x["id"]) for kind, x in items]
        assert len(ids) == 9 and len(set(ids)) == 9, limit                          # no item twice, none missing
    first = await pull(client, h, limit=4)
    assert first["has_more"] is True and sum(len(first[k]) for k in ("workouts", "nutrition_logs", "body_metrics")) == 4
    page_one = {x["id"] for x in first["workouts"]}
    second = await pull(client, h, first["cursor"], 4)
    assert page_one.isdisjoint({x["id"] for x in second["workouts"]})


async def test_pull_item_shapes_match_the_rest_resources(client):
    h, ex, food = await setup(client)
    w, m, a = workout(ex, notes="felt good"), meal(food, hunger_level_before=3), measurement(waist_cm=85.5)
    await push(client, h, workouts=[w], logs=[m], metrics=[a])
    page = await pull(client, h)
    rest_w = (await client.get(f"{BASE}/workouts", headers=h)).json()["items"][0]
    rest_m = (await client.get(f"{BASE}/nutrition-logs", headers=h)).json()["items"][0]
    rest_a = (await client.get(f"{BASE}/body-metrics", headers=h)).json()[0]
    assert page["workouts"][0] == {**rest_w, "deleted_at": None}
    assert page["nutrition_logs"][0] == {**rest_m, "deleted_at": None}
    assert page["body_metrics"][0] == {**rest_a, "deleted_at": None}
    assert page["workouts"][0]["notes"] == "felt good" and page["body_metrics"][0]["waist_cm"] == 85.5


async def test_a_cursor_delivers_later_changes_and_overlaps_recent_ones(client):
    h, ex, food = await setup(client)
    await push(client, h, workouts=[workout(ex, 3)])
    _, cursor = await pull_all(client, h, 200)
    later = workout(ex, 2)
    await push(client, h, workouts=[later])
    await client.post(f"{BASE}/nutrition-logs", headers=h, json=meal(food, 1))             # another route, same stream
    page = await pull(client, h, cursor)
    uuids = {x["client_uuid"] for x in page["workouts"]}
    assert later["client_uuid"] in uuids and len(page["nutrition_logs"]) == 1
    assert len(page["workouts"]) == 2                  # the first workout is inside the 60 s overlap: delivered again
    assert page["has_more"] is False


async def test_changes_made_through_the_rest_routes_reach_the_other_device(client):
    h, ex, food = await setup(client)
    _, cursor = await pull_all(client, h, 200)
    created = await client.post(f"{BASE}/body-metrics", headers=h, json=measurement(1, 79.0))
    rest_id = created.json()["id"]
    assert [x["id"] for x in (await pull(client, h, cursor))["body_metrics"]] == [rest_id]
    await client.delete(f"{BASE}/body-metrics/{rest_id}", headers=h)
    page = await pull(client, h, cursor)
    assert [(x["id"], x["deleted_at"] is not None) for x in page["body_metrics"]] == [(rest_id, True)]


async def test_users_never_see_each_others_items(client):
    a, ex, food = await setup(client)
    b, _, _ = await setup(client)
    shared = new_id()
    mine = {**measurement(1, 80.0), "client_uuid": shared}
    theirs = {**measurement(1, 90.0), "client_uuid": shared}                       # the same uuid in another account
    assert statuses(await push(client, a, metrics=[mine])) == ["applied"]
    result = await push(client, b, metrics=[theirs])
    assert statuses(result) == ["applied"] and result["results"][0]["server_copy"] is None
    assert [x["weight_kg"] for x in (await pull(client, a))["body_metrics"]] == [80.0]
    assert [x["weight_kg"] for x in (await pull(client, b))["body_metrics"]] == [90.0]
    assert (await pull(client, (await _user(client))))["workouts"] == []


async def test_a_pushed_measurement_updates_the_current_weight(client):
    h, *_ = await setup(client)
    await push(client, h, metrics=[measurement(1, 71.5)])
    assert (await client.get(f"{BASE}/users/me/profile", headers=h)).json()["weight_kg"] == 71.5

