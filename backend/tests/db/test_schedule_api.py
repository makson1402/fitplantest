"""B-14: reminders, push tokens, notification inbox and moving a planned session to another weekday (FR-P9, FR-R7)."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest_asyncio
from sqlalchemy import text

from app.core.config import Settings
from app.main import create_app
from tests.db.test_analytics_api import _user
from tests.support import NO_STORES

BASE = "/api/v1"


@pytest_asyncio.fixture
async def client(seeded_engine):
    url = seeded_engine.url.render_as_string(hide_password=False)
    settings = Settings(jwt_secret="test-secret-" + "x" * 32, bcrypt_rounds=4, auth_rate_limit=10_000,
                        _env_file=None, **{**NO_STORES, "database_url": url})
    app = create_app(settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        yield http
    await app.state.db_engine.dispose()


def token(n: str | None = None) -> str:
    return f"ExponentPushToken[{n or uuid.uuid4().hex}]"


# ------------------------------------------------------------------ reminders

def meal(meal_type: str, at: str, weekdays: list[str], **extra) -> dict:
    return {"type": "meal_reminder", "meal_type": meal_type, "weekdays": weekdays, "time_of_day": at, **extra}


def workout(at: str, weekdays: list[str], **extra) -> dict:
    return {"type": "training_reminder", "weekdays": weekdays, "time_of_day": at, **extra}


async def test_every_route_needs_authentication(client):
    for method, path in (("get", "/reminders"), ("put", "/reminders"), ("post", "/devices/push-token"),
                         ("delete", "/devices/push-token/1"), ("get", "/notifications"),
                         ("post", "/notifications/1/read"), ("patch", "/training-sessions/1")):
        assert (await client.request(method, BASE + path)).status_code == 401, path


async def test_the_schedule_round_trips(client):
    h = await _user(client)
    assert (await client.get(f"{BASE}/reminders", headers=h)).json() == []
    body = {"reminders": [
        meal("breakfast", "07:30", ["mon", "tue", "wed", "thu", "fri"], message="Eat!"),
        meal("dinner", "19:00:30", ["sat", "sun"], is_enabled=False),
        workout("18:15", ["wed", "mon", "fri"]),                       # the given order of days is kept
    ]}
    r = await client.put(f"{BASE}/reminders", headers=h, json=body)
    assert r.status_code == 200, r.text
    saved = r.json()
    assert [x["id"] for x in saved] == sorted(x["id"] for x in saved)           # ids follow the input order
    assert saved[0] == {"id": saved[0]["id"], "type": "meal_reminder", "meal_type": "breakfast",
                        "weekdays": ["mon", "tue", "wed", "thu", "fri"], "time_of_day": "07:30:00", "message": "Eat!",
                        "is_enabled": True}
    assert saved[1]["time_of_day"] == "19:00:30" and saved[1]["is_enabled"] is False and saved[1]["message"] is None
    assert saved[2]["type"] == "training_reminder" and saved[2]["meal_type"] is None
    assert saved[2]["weekdays"] == ["wed", "mon", "fri"]
    assert (await client.get(f"{BASE}/reminders", headers=h)).json() == saved

    again = (await client.put(f"{BASE}/reminders", headers=h, json={"reminders": [workout("06:00", ["sun"])]})).json()
    assert len(again) == 1 and again[0]["time_of_day"] == "06:00:00"            # the old ones are gone
    assert (await client.get(f"{BASE}/reminders", headers=h)).json() == again
    assert (await client.put(f"{BASE}/reminders", headers=h, json={"reminders": []})).json() == []
    assert (await client.get(f"{BASE}/reminders", headers=h)).json() == []


async def test_reminders_keep_the_local_time_whatever_the_time_zone(client):
    h = await _user(client)
    await client.put(f"{BASE}/reminders", headers=h, json={"reminders": [meal("lunch", "12:00", ["mon"])]})
    before = (await client.get(f"{BASE}/reminders", headers=h)).json()
    for zone in ("Europe/Warsaw", "Pacific/Kiritimati", "America/Los_Angeles"):
        assert (await client.patch(f"{BASE}/users/me", headers=h, json={"timezone": zone})).status_code == 200
        assert (await client.get(f"{BASE}/reminders", headers=h)).json() == before      # 12:00 stays 12:00
    assert before[0]["time_of_day"] == "12:00:00"


async def test_invalid_reminders_are_422_and_change_nothing(client):
    h = await _user(client)
    keep = (await client.put(f"{BASE}/reminders", headers=h,
                             json={"reminders": [workout("07:00", ["mon"])]})).json()
    bad = [
        meal("breakfast", "07:00", ["mon"]) | {"meal_type": None},               # meal reminder without a meal type
        workout("07:00", ["mon"], meal_type="lunch"),                            # training reminder with a meal type
        workout("07:00", ["mon", "mon"]),                                        # duplicate weekday
        workout("07:00", []),                                                    # no weekday
        workout("07:00", ["mon", "tue", "wed", "thu", "fri", "sat", "sun", "mon"]),
        workout("07:00", ["funday"]),
        workout("25:00", ["mon"]), workout("noon", ["mon"]), workout("07:00:00+02:00", ["mon"]),
        workout("07:00", ["mon"], message="x" * 201), workout("07:00", ["mon"], message="a\x00b"),
        {"type": "motivational", "weekdays": ["mon"], "time_of_day": "07:00"},   # not a reminder type
        {"type": "training_reminder", "weekdays": ["mon"]},                       # no time
    ]
    for item in bad:
        r = await client.put(f"{BASE}/reminders", content=json.dumps({"reminders": [item]}),
                             headers={**h, "content-type": "application/json"})
        assert r.status_code == 422 and r.json()["code"] == "validation_error", item
    for payload in ({}, {"reminders": None}, {"reminders": "all"}):
        assert (await client.put(f"{BASE}/reminders", headers=h, json=payload)).status_code == 422
    too_many = {"reminders": [workout("07:00", ["mon"])] * 51}
    r = await client.put(f"{BASE}/reminders", headers=h, json=too_many)
    assert r.status_code == 422 and r.json()["details"][0]["field"] == "reminders"
    assert (await client.get(f"{BASE}/reminders", headers=h)).json() == keep             # nothing was replaced
    assert (await client.put(f"{BASE}/reminders", headers=h, json={"reminders": [workout("07:00", ["mon"])] * 50})
            ).status_code == 200


async def test_reminders_are_private(client):
    a, b = await _user(client), await _user(client)
    await client.put(f"{BASE}/reminders", headers=a, json={"reminders": [workout("07:00", ["mon"])]})
    assert (await client.get(f"{BASE}/reminders", headers=b)).json() == []
    await client.put(f"{BASE}/reminders", headers=b, json={"reminders": []})
    assert len((await client.get(f"{BASE}/reminders", headers=a)).json()) == 1          # b's replace did not touch a


# ------------------------------------------------------------------ push tokens

async def test_registering_a_token_twice_keeps_one_device(client):
    h = await _user(client)
    t = token()
    first = await client.post(f"{BASE}/devices/push-token", headers=h, json={"token": t, "platform": "android"})
    assert first.status_code == 201 and first.json()["token"] == t and first.json()["platform"] == "android"
    second = await client.post(f"{BASE}/devices/push-token", headers=h, json={"token": t, "platform": "ios"})
    assert second.status_code == 201 and second.json()["id"] == first.json()["id"]
    assert second.json()["platform"] == "ios"
    assert (await client.delete(f"{BASE}/devices/push-token/{first.json()['id']}", headers=h)).status_code == 204
    assert (await client.delete(f"{BASE}/devices/push-token/{first.json()['id']}", headers=h)).status_code == 404


async def test_a_device_moves_to_the_user_who_signs_in_on_it(client):
    old_owner, new_owner = await _user(client), await _user(client)
    t = token()
    mine = (await client.post(f"{BASE}/devices/push-token", headers=old_owner,
                              json={"token": t, "platform": "android"})).json()
    moved = (await client.post(f"{BASE}/devices/push-token", headers=new_owner,
                               json={"token": t, "platform": "android"})).json()
    assert moved["id"] == mine["id"]                                             # one row per token
    assert (await client.delete(f"{BASE}/devices/push-token/{mine['id']}", headers=old_owner)).status_code == 404
    assert (await client.delete(f"{BASE}/devices/push-token/{mine['id']}", headers=new_owner)).status_code == 204


async def test_only_valid_expo_tokens_are_accepted(client):
    h = await _user(client)
    for bad in ("", "abc", "ExponentPushToken[]", "ExponentPushToken[a b]", "ExponentPushToken[x]]", "fcm:123",
                "ExponentPushToken[" + "a" * 201 + "]", "ExponentPushToken[a\x00b]"):
        r = await client.post(f"{BASE}/devices/push-token", headers=h, json={"token": bad, "platform": "android"})
        assert r.status_code == 422 and r.json()["details"][0]["field"] == "token", repr(bad)
    r = await client.post(f"{BASE}/devices/push-token", headers=h, json={"token": token(), "platform": "web"})
    assert r.status_code == 422 and r.json()["details"][0]["field"] == "platform"
    assert (await client.post(f"{BASE}/devices/push-token", headers=h, json={"token": token()})).status_code == 422
    assert (await client.post(f"{BASE}/devices/push-token", headers=h,
                              json={"token": "ExpoPushToken[old-style_1]", "platform": "ios"})).status_code == 201


async def test_a_user_keeps_the_ten_latest_devices(client):
    h = await _user(client)
    ids = []
    for _ in range(12):
        r = await client.post(f"{BASE}/devices/push-token", headers=h, json={"token": token(), "platform": "ios"})
        ids.append(r.json()["id"])
    for old in ids[:2]:
        assert (await client.delete(f"{BASE}/devices/push-token/{old}", headers=h)).status_code == 404
    for kept in ids[2:]:
        assert (await client.delete(f"{BASE}/devices/push-token/{kept}", headers=h)).status_code == 204


# ------------------------------------------------------------------ notifications

def _insert_notifications(engine, user_id: int, count: int) -> list[int]:
    base = datetime.now(UTC) - timedelta(hours=count)
    ids = []
    with engine.begin() as conn:
        for i in range(count):
            row = conn.execute(text(
                "INSERT INTO notification (user_id, type, title, message, data, created_at) "
                "VALUES (:u, :t, :title, :msg, CAST(:data AS jsonb), :at) RETURNING id"),
                {"u": user_id, "t": "progress_update" if i % 2 == 0 else "motivational", "title": f"Title {i}",
                 "msg": f"Message {i}", "data": json.dumps({"report_id": i} if i % 2 == 0 else {}),
                 "at": base + timedelta(hours=i)}).one()
            ids.append(row[0])
    return ids


async def test_the_inbox_lists_newest_first_and_pages(client, seeded_engine):
    h = await _user(client)
    me = (await client.get(f"{BASE}/users/me", headers=h)).json()["id"]
    empty = (await client.get(f"{BASE}/notifications", headers=h)).json()
    assert empty == {"items": [], "total": 0, "limit": 20, "offset": 0}
    ids = _insert_notifications(seeded_engine, me, 25)
    page = (await client.get(f"{BASE}/notifications", headers=h)).json()
    assert (page["total"], page["limit"], page["offset"], len(page["items"])) == (25, 20, 0, 20)
    assert [n["id"] for n in page["items"]] == list(reversed(ids))[:20]
    newest = page["items"][0]
    assert newest["type"] == "progress_update" and newest["data"] == {"report_id": 24}
    assert newest["title"] == "Title 24" and newest["message"] == "Message 24" and newest["read_at"] is None
    assert page["items"][1]["data"] == {}
    rest = (await client.get(f"{BASE}/notifications?limit=20&offset=20", headers=h)).json()
    assert [n["id"] for n in rest["items"]] == list(reversed(ids))[20:] and rest["offset"] == 20
    for query in ("?limit=0", "?limit=101", "?offset=-1", f"?offset={2**70}"):
        assert (await client.get(f"{BASE}/notifications{query}", headers=h)).status_code == 422, query


async def test_marking_read_is_idempotent_and_private(client, seeded_engine):
    a, b = await _user(client), await _user(client)
    a_id = (await client.get(f"{BASE}/users/me", headers=a)).json()["id"]
    first, second = _insert_notifications(seeded_engine, a_id, 2)
    assert (await client.post(f"{BASE}/notifications/{first}/read", headers=b)).status_code == 404   # not b's
    assert (await client.post(f"{BASE}/notifications/{first}/read", headers=a)).status_code == 204
    read_at = next(n for n in (await client.get(f"{BASE}/notifications", headers=a)).json()["items"]
                   if n["id"] == first)["read_at"]
    assert read_at is not None
    assert (await client.post(f"{BASE}/notifications/{first}/read", headers=a)).status_code == 204
    items = {n["id"]: n for n in (await client.get(f"{BASE}/notifications", headers=a)).json()["items"]}
    assert items[first]["read_at"] == read_at and items[second]["read_at"] is None     # the first time is kept
    assert (await client.post(f"{BASE}/notifications/999999999/read", headers=a)).status_code == 404
    assert (await client.post(f"{BASE}/notifications/{2**70}/read", headers=a)).status_code == 422
    assert (await client.get(f"{BASE}/notifications", headers=b)).json()["total"] == 0


# ------------------------------------------------------------------ moving a session (FR-P9)

PROFILE = {"age": 30, "sex": "male", "weight_kg": 80, "height_cm": 180, "activity_level_pal": 1.55,
           "goal": "strength", "experience_level": "intermediate", "equipment": "gym"}


async def _plan(client, h, days: int = 3) -> dict:
    return (await client.post(f"{BASE}/training-plans/generate", headers=h,
                              json={"goal": "strength", "training_days": days})).json()


async def test_a_session_moves_to_a_free_weekday(client):
    h = await _user(client, PROFILE)
    plan = await _plan(client, h)
    taken = {s["weekday"]: s for s in plan["sessions"]}
    free = next(d for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun") if d not in taken)
    session = plan["sessions"][0]
    r = await client.patch(f"{BASE}/training-sessions/{session['id']}", headers=h, json={"weekday": free})
    assert r.status_code == 200, r.text
    moved = r.json()
    assert moved["weekday"] == free and moved["id"] == session["id"] and moved["name"] == session["name"]
    assert [e["id"] for e in moved["exercises"]] == [e["id"] for e in session["exercises"]]    # nothing else changed
    stored = (await client.get(f"{BASE}/training-plans/draft", headers=h)).json()
    assert {s["id"]: s["weekday"] for s in stored["sessions"]}[session["id"]] == free
    # the same weekday again is not a conflict with itself
    assert (await client.patch(f"{BASE}/training-sessions/{session['id']}", headers=h,
                               json={"weekday": free})).status_code == 200


async def test_a_taken_weekday_is_a_409_and_changes_nothing(client):
    h = await _user(client, PROFILE)
    plan = await _plan(client, h)
    first, second = plan["sessions"][0], plan["sessions"][1]
    r = await client.patch(f"{BASE}/training-sessions/{first['id']}", headers=h, json={"weekday": second["weekday"]})
    assert r.status_code == 409 and r.json()["code"] == "conflict"
    stored = (await client.get(f"{BASE}/training-plans/draft", headers=h)).json()
    assert [s["weekday"] for s in stored["sessions"]] == [s["weekday"] for s in plan["sessions"]]


async def test_session_moves_are_validated_private_and_closed_for_archived_plans(client):
    h, other = await _user(client, PROFILE), await _user(client, PROFILE)
    plan = await _plan(client, h)
    sid = plan["sessions"][0]["id"]
    for payload in ({}, {"weekday": "someday"}, {"weekday": None}, {"weekday": 3}):
        r = await client.patch(f"{BASE}/training-sessions/{sid}", headers=h, json=payload)
        assert r.status_code == 422 and r.json()["code"] == "validation_error", payload
    assert (await client.patch(f"{BASE}/training-sessions/{sid}", headers=other,
                               json={"weekday": "sun"})).status_code == 404            # another user's session
    assert (await client.patch(f"{BASE}/training-sessions/999999999", headers=h,
                               json={"weekday": "sun"})).status_code == 404
    assert (await client.patch(f"{BASE}/training-sessions/{2**70}", headers=h,
                               json={"weekday": "sun"})).status_code == 422

    await client.post(f"{BASE}/training-plans/{plan['id']}/accept", headers=h, json={})
    free = next(d for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
                if d not in {s["weekday"] for s in plan["sessions"]})
    assert (await client.patch(f"{BASE}/training-sessions/{sid}", headers=h, json={"weekday": free})).status_code == 200
    newer = await _plan(client, h, 4)
    await client.post(f"{BASE}/training-plans/{newer['id']}/accept", headers=h, json={})   # the first plan is archived
    r = await client.patch(f"{BASE}/training-sessions/{sid}", headers=h, json={"weekday": "sun"})
    assert r.status_code == 409 and r.json()["code"] == "conflict"
