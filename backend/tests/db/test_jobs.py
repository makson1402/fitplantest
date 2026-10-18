"""B-26: weekly report job, push delivery and expired-photo cleanup against a real, seeded PostgreSQL (+ MongoDB)."""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core.config import Settings
from app.db.mongo import create_mongo_client, ensure_indexes
from app.db.session import create_engine_from_url
from app.jobs.dispatch import GIVE_UP_AFTER, dispatch_pending
from app.jobs.photo_cleanup import cleanup_photos
from app.jobs.weekly_report import report_week, run_weekly_reports
from app.main import create_app
from app.repositories import UserRecord
from app.repositories.recognitions import MongoRecognitionRepository
from app.repositories.sql import sql_uow_factory
from app.services.push import ExpoPushSender, PushDeliveryError, PushMessage, PushResult
from tests.db.test_analytics_api import _user
from tests.db.test_mongo_buffer import _item, _mongo_url
from tests.db.test_reports_api import _history
from tests.fakes import FakeClock
from tests.support import NO_STORES

BASE = "/api/v1"


@pytest_asyncio.fixture
async def env(seeded_engine):
    url = seeded_engine.url.render_as_string(hide_password=False)
    settings = Settings(jwt_secret="test-secret-" + "x" * 32, bcrypt_rounds=4, auth_rate_limit=10_000,
                        _env_file=None, **{**NO_STORES, "database_url": url})
    app = create_app(settings)
    engine = create_engine_from_url(url, pool_size=3)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        yield http, sql_uow_factory(engine), seeded_engine
    await engine.dispose()
    await app.state.db_engine.dispose()


def this_monday() -> date:
    today = datetime.now(UTC).date()
    return today - timedelta(days=today.weekday())


def monday_at(hour: int, minute: int = 0) -> FakeClock:
    """The scheduler's clock: this Monday at the given UTC time. The data of `_history` is last week's."""
    return FakeClock(datetime.combine(this_monday(), datetime.min.time(), tzinfo=UTC) + timedelta(hours=hour,
                                                                                                  minutes=minute))


async def _me(http, h) -> int:
    return (await http.get(f"{BASE}/users/me", headers=h)).json()["id"]


async def _reports(http, h) -> list[dict]:
    return (await http.get(f"{BASE}/reports?limit=100", headers=h)).json()["items"]


async def _notifications(http, h) -> list[dict]:
    return (await http.get(f"{BASE}/notifications?limit=100", headers=h)).json()["items"]


class FakeSender:
    def __init__(self, invalid: set[str] | None = None):
        self.calls: list[list[PushMessage]] = []
        self.invalid = invalid or set()
        self.fail = False

    async def send(self, messages: list[PushMessage]) -> PushResult:
        if self.fail:
            raise PushDeliveryError("ConnectError")
        self.calls.append(messages)
        return PushResult(delivered=len([m for m in messages if m.to not in self.invalid]),
                          invalid_tokens=[m.to for m in messages if m.to in self.invalid])


# ------------------------------------------------------------------ the week that is due

def _user_record(zone: str) -> UserRecord:
    return UserRecord(1, "a@example.com", None, zone, True, datetime(2026, 1, 1, tzinfo=UTC))


def test_the_report_week_follows_monday_0700_in_the_users_zone():
    # 2026-10-12 is a Monday. Warsaw is UTC+2 that day (summer time ended on 2026-10-25).
    warsaw = _user_record("Europe/Warsaw")
    assert report_week(warsaw, datetime(2026, 10, 12, 4, 59, tzinfo=UTC)) == (date(2026, 9, 28), date(2026, 10, 4))
    assert report_week(warsaw, datetime(2026, 10, 12, 5, 0, tzinfo=UTC)) == (date(2026, 10, 5), date(2026, 10, 11))
    assert report_week(warsaw, datetime(2026, 10, 13, 12, 0, tzinfo=UTC)) == (date(2026, 10, 5), date(2026, 10, 11))
    assert report_week(warsaw, datetime(2026, 10, 18, 22, 0, tzinfo=UTC)) == (date(2026, 10, 5), date(2026, 10, 11))
    # the same instant is Monday morning in Warsaw and still Sunday evening in Los Angeles
    los_angeles = _user_record("America/Los_Angeles")
    at = datetime(2026, 10, 12, 5, 30, tzinfo=UTC)
    assert report_week(warsaw, at)[0] == date(2026, 10, 5)
    assert report_week(los_angeles, at)[0] == date(2026, 9, 28)
    assert report_week(los_angeles, datetime(2026, 10, 12, 14, 0, tzinfo=UTC))[0] == date(2026, 10, 5)  # 07:00 PDT
    assert report_week(_user_record("Mars/Olympus"), datetime(2026, 10, 12, 7, 0, tzinfo=UTC))[0] == date(2026, 10, 5)


# ------------------------------------------------------------------ weekly reports

async def test_the_weekly_job_creates_exactly_one_report_and_one_notification_per_week(env):
    http, factory, _ = env
    h, _, _, monday, sunday = await _history(http)
    clock = monday_at(8)
    for _ in range(3):                                                        # the job runs again and again
        await run_weekly_reports(factory, clock)
    reports = await _reports(http, h)
    assert len(reports) == 1
    report = reports[0]
    assert report["is_auto"] is True and report["report_type"] == "weekly"
    assert (report["period_start"], report["period_end"]) == (monday.isoformat(), sunday.isoformat())
    assert report["training_volume_kg"] == 1925.0                            # the same figures as a manual report
    inbox = await _notifications(http, h)
    assert len(inbox) == 1
    assert inbox[0]["type"] == "progress_update" and inbox[0]["data"] == {"report_id": report["id"]}
    assert inbox[0]["read_at"] is None and monday.isoformat() in inbox[0]["message"]


async def test_concurrent_job_runs_still_create_one_report(env):
    http, factory, _ = env
    h, *_ = await _history(http)
    clock = monday_at(8)
    await asyncio.gather(*(run_weekly_reports(factory, clock) for _ in range(3)))
    assert len(await _reports(http, h)) == 1 and len(await _notifications(http, h)) == 1


async def test_a_report_made_by_hand_is_not_made_again(env):
    http, factory, _ = env
    h, _, _, monday, sunday = await _history(http)
    manual = (await http.post(f"{BASE}/reports", headers=h, json={"period_start": monday.isoformat(),
                                                                  "period_end": sunday.isoformat()})).json()
    await run_weekly_reports(factory, monday_at(8))
    reports = await _reports(http, h)
    assert [r["id"] for r in reports] == [manual["id"]] and reports[0]["is_auto"] is False
    assert await _notifications(http, h) == []                               # nothing new happened


async def test_users_without_enough_history_get_nothing(env):
    http, factory, _ = env
    h = await _user(http)
    await http.post(f"{BASE}/body-metrics", headers=h, json={"measured_on": (this_monday() - timedelta(days=3))
                                                             .isoformat(), "weight_kg": 80})
    stats = await run_weekly_reports(factory, monday_at(8))
    assert stats.failed == 0 and stats.users >= 1
    assert await _reports(http, h) == [] and await _notifications(http, h) == []


async def test_the_report_waits_for_monday_0700_in_each_users_time_zone(env):
    http, factory, _ = env
    east, west = await _history(http), await _history(http)
    await http.patch(f"{BASE}/users/me", headers=east[0], json={"timezone": "Pacific/Kiritimati"})   # UTC+14
    await http.patch(f"{BASE}/users/me", headers=west[0], json={"timezone": "Pacific/Pago_Pago"})    # UTC-11
    monday = east[3]
    await run_weekly_reports(factory, monday_at(8))                          # 08:00 UTC: Tuesday there, Sunday here
    assert [r["period_start"] for r in await _reports(http, east[0])] == [monday.isoformat()]
    wrong_week = (monday - timedelta(days=7)).isoformat()                     # still the week before for the west
    assert monday.isoformat() not in [r["period_start"] for r in await _reports(http, west[0])]
    assert wrong_week in [r["period_start"] for r in await _reports(http, west[0])] or not await _reports(http, west[0])
    await run_weekly_reports(factory, FakeClock(monday_at(8).current + timedelta(days=1, hours=16)))
    assert monday.isoformat() in [r["period_start"] for r in await _reports(http, west[0])]  # Tuesday 00:00 UTC+16h
    assert len([r for r in await _reports(http, east[0]) if r["period_start"] == monday.isoformat()]) == 1


# ------------------------------------------------------------------ push delivery

def _register(engine, user_id: int, token: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO device_push_token (user_id, token, platform) VALUES (:u, :t, 'android')"),
                     {"u": user_id, "t": token})


def _notify(engine, user_id: int, created: datetime | None = None) -> int:
    with engine.begin() as conn:
        return conn.execute(text(
            "INSERT INTO notification (user_id, type, title, message, data, created_at) VALUES "
            "(:u, 'achievement', 'Well done', 'A new record', CAST(:d AS jsonb), :at) RETURNING id"),
            {"u": user_id, "d": json.dumps({"exercise_id": 7}), "at": created or datetime.now(UTC)}).scalar_one()


def _sent_at(engine, notification_id: int):
    with engine.connect() as conn:
        return conn.execute(text("SELECT sent_at FROM notification WHERE id = :i"), {"i": notification_id}).scalar_one()


def _token_count(engine, token: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM device_push_token WHERE token = :t"), {"t": token}).scalar_one()


async def test_a_notification_is_pushed_once_to_every_device_of_its_user(env):
    http, factory, engine = env
    h = await _user(http)
    me = await _me(http, h)
    a, b = f"ExponentPushToken[{uuid.uuid4().hex}]", f"ExponentPushToken[{uuid.uuid4().hex}]"
    _register(engine, me, a)
    _register(engine, me, b)
    note = _notify(engine, me)
    sender, clock = FakeSender(), FakeClock(datetime.now(UTC))
    stats = await dispatch_pending(factory, clock, sender)
    assert stats.sent >= 1 and stats.pushes >= 2
    mine = [m for call in sender.calls for m in call if m.to in (a, b)]
    assert sorted(m.to for m in mine) == sorted([a, b])
    assert mine[0].title == "Well done" and mine[0].body == "A new record"
    assert mine[0].data == {"exercise_id": 7, "notification_id": note}
    assert _sent_at(engine, note) is not None
    before = len(sender.calls)
    await dispatch_pending(factory, clock, sender)                           # nothing is sent twice
    assert len(sender.calls) == before


async def test_two_dispatchers_do_not_push_the_same_notification_twice(env):
    http, factory, engine = env
    h = await _user(http)
    me = await _me(http, h)
    token = f"ExponentPushToken[{uuid.uuid4().hex}]"
    _register(engine, me, token)
    _notify(engine, me)
    sender, clock = FakeSender(), FakeClock(datetime.now(UTC))
    await asyncio.gather(*(dispatch_pending(factory, clock, sender) for _ in range(4)))
    assert sum(1 for call in sender.calls for m in call if m.to == token) == 1


async def test_dead_tokens_are_removed(env):
    http, factory, engine = env
    h = await _user(http)
    me = await _me(http, h)
    alive, dead = f"ExponentPushToken[{uuid.uuid4().hex}]", f"ExponentPushToken[{uuid.uuid4().hex}]"
    _register(engine, me, alive)
    _register(engine, me, dead)
    note = _notify(engine, me)
    stats = await dispatch_pending(factory, FakeClock(datetime.now(UTC)), FakeSender(invalid={dead}))
    assert stats.removed_tokens >= 1
    assert _token_count(engine, dead) == 0 and _token_count(engine, alive) == 1
    assert _sent_at(engine, note) is not None


async def test_an_unreachable_push_service_keeps_the_notification_queued_until_it_is_a_day_old(env):
    http, factory, engine = env
    h = await _user(http)
    me = await _me(http, h)
    _register(engine, me, f"ExponentPushToken[{uuid.uuid4().hex}]")
    note = _notify(engine, me)
    clock = FakeClock(datetime.now(UTC))
    sender = FakeSender()
    sender.fail = True
    stats = await dispatch_pending(factory, clock, sender)
    assert stats.retry_later >= 1 and _sent_at(engine, note) is None         # stays in the queue
    sender.fail = False
    await dispatch_pending(factory, clock, sender)                           # the service is back: delivered
    assert _sent_at(engine, note) is not None and any(m.title == "Well done" for c in sender.calls for m in c)

    old = _notify(engine, me, created=datetime.now(UTC) - GIVE_UP_AFTER - timedelta(hours=1))
    sender.fail, calls = True, len(sender.calls)
    await dispatch_pending(factory, clock, sender)                           # a day old: dropped, not retried forever
    assert _sent_at(engine, old) is not None and len(sender.calls) == calls


async def test_a_user_without_devices_has_the_notification_marked_handled(env):
    http, factory, engine = env
    h = await _user(http)
    note = _notify(engine, await _me(http, h))
    sender = FakeSender()
    await dispatch_pending(factory, FakeClock(datetime.now(UTC)), sender)
    assert _sent_at(engine, note) is not None
    assert [(await http.get(f"{BASE}/notifications", headers=h)).json()["total"]] == [1]   # still in the inbox


# ------------------------------------------------------------------ Expo sender

def _expo(handler, **kwargs) -> ExpoPushSender:
    return ExpoPushSender("https://push.test/send", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                          **kwargs)


async def test_the_expo_sender_batches_and_reads_tickets():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json.loads(request.content)
        return httpx.Response(200, json={"data": [
            {"status": "error", "details": {"error": "DeviceNotRegistered"}} if m["to"].endswith("[dead]")
            else {"status": "error", "details": {"error": "MessageRateExceeded"}} if m["to"].endswith("[slow]")
            else {"status": "ok", "id": "x"} for m in payload]})

    sender = _expo(handler, access_token="secret-token")
    messages = [PushMessage(f"ExponentPushToken[{i}]", "T", "B", {"report_id": i}) for i in range(150)]
    messages += [PushMessage("ExponentPushToken[dead]", "T", "B"), PushMessage("ExponentPushToken[slow]", "T", "B")]
    result = await sender.send(messages)
    assert [len(json.loads(r.content)) for r in requests] == [100, 52]       # at most 100 per request
    assert result.delivered == 150 and result.invalid_tokens == ["ExponentPushToken[dead]"]
    first = json.loads(requests[0].content)[0]
    assert first == {"to": "ExponentPushToken[0]", "title": "T", "body": "B", "data": {"report_id": 0},
                     "sound": "default"}
    assert requests[0].headers["authorization"] == "Bearer secret-token"
    await sender.aclose()


async def test_the_expo_sender_reports_failures_without_leaking_the_message():
    for response in (httpx.Response(500, text="boom"), httpx.Response(200, text="not json"),
                     httpx.Response(200, json={"errors": [{"code": "X"}]})):
        sender = _expo(lambda request, r=response: r)
        with pytest.raises(PushDeliveryError) as raised:
            await sender.send([PushMessage("ExponentPushToken[a]", "secret title", "secret body")])
        assert "secret" not in str(raised.value)

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    with pytest.raises(PushDeliveryError):
        await _expo(unreachable).send([PushMessage("ExponentPushToken[a]", "t", "b")])
    assert (await _expo(lambda request: httpx.Response(200, json={"data": []})).send([])).delivered == 0


# ------------------------------------------------------------------ photo cleanup

@pytest_asyncio.fixture
async def mongo():
    client = create_mongo_client(_mongo_url())
    try:
        await client.admin.command("ping")
    except Exception as exc:  # noqa: BLE001
        await client.close()
        pytest.skip(f"MongoDB is not reachable: {exc.__class__.__name__}")
    database = client[f"fitplan_test_{uuid.uuid4().hex[:8]}"]
    await ensure_indexes(database)
    yield database
    await client.drop_database(database.name)
    await client.close()


def _photo(root: Path, user: int, age: timedelta, now: datetime) -> str:
    relative = f"meals/{user}/{uuid.uuid4()}.jpg"
    file = root / relative
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(b"jpeg")
    stamp = (now - age).timestamp()
    os.utime(file, (stamp, stamp))
    return relative


async def test_cleanup_removes_only_old_unreferenced_photos(env, mongo, tmp_path):
    http, factory, engine = env
    h = await _user(http)
    me = await _me(http, h)
    now = datetime.now(UTC)
    old, fresh = timedelta(hours=7), timedelta(hours=1)
    gone = _photo(tmp_path, me, old, now)
    too_new = _photo(tmp_path, me, fresh, now)
    buffered = _photo(tmp_path, me, old, now)
    confirmed = _photo(tmp_path, me, old, now)
    other_user_gone = _photo(tmp_path, me + 1000, old, now)
    outside = tmp_path / "keep.txt"
    outside.write_text("not a meal photo")
    os.utime(outside, ((now - old).timestamp(),) * 2)

    await MongoRecognitionRepository(mongo).create(
        user_id=me, meal_type="lunch", photo_path=buffered, model_name="m", model_version="1",
        overall_confidence=0.9, items=[_item()], now=now)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO recognition_ai (user_id, image_url, model_name, uploaded_at, recognized_items, "
            "estimated_calories, estimated_protein_g, estimated_fat_g, estimated_carbs_g, confidence_score, was_edited) "
            "VALUES (:u, :p, 'm', now(), '[]', 100, 1, 1, 1, 0.9, false)"), {"u": me, "p": confirmed})

    deleted = await cleanup_photos(str(tmp_path), factory, mongo, FakeClock(now))
    assert deleted == 2
    assert not (tmp_path / gone).exists() and not (tmp_path / other_user_gone).exists()
    assert (tmp_path / too_new).exists() and (tmp_path / buffered).exists() and (tmp_path / confirmed).exists()
    assert outside.exists()                                                  # nothing outside meals/ is touched
    assert not (tmp_path / "meals" / str(me + 1000)).exists()                # the emptied folder is removed
    assert await cleanup_photos(str(tmp_path), factory, mongo, FakeClock(now)) == 0

    # once the buffered document has expired its photo is unreferenced too
    later = FakeClock(now + timedelta(hours=7))
    assert await cleanup_photos(str(tmp_path), factory, mongo, later) == 2   # buffered and too_new, both old by then
    assert (tmp_path / confirmed).exists()                                   # confirmed photos stay


async def test_cleanup_does_nothing_without_a_photo_dir_or_without_mongo(env, mongo, tmp_path):
    http, factory, _ = env
    now = datetime.now(UTC)
    kept = _photo(tmp_path, 1, timedelta(hours=9), now)
    assert await cleanup_photos(None, factory, mongo, FakeClock(now)) == 0
    assert await cleanup_photos(str(tmp_path), factory, None, FakeClock(now)) == 0     # references unknown: keep all
    assert (tmp_path / kept).exists()
    assert await cleanup_photos(str(tmp_path / "missing"), factory, mongo, FakeClock(now)) == 0
