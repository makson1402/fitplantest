"""B-25: progress reports and their PDF / CSV export against a real, seeded PostgreSQL.

The figures are computed by hand from the data the test logs; the exports must repeat exactly the report's values."""
from __future__ import annotations

import csv
import io
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest_asyncio
from pypdf import PdfReader

from app.core.config import Settings
from app.main import create_app
from tests.db.test_analytics_api import _eat, _exercise_ids, _food, _train, _user, _weigh, day
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


def last_week() -> tuple[date, date]:
    """The last full ISO week (Monday-Sunday) before today's week."""
    monday = datetime.now(UTC).date() - timedelta(days=datetime.now(UTC).date().weekday() + 7)
    return monday, monday + timedelta(days=6)


def offset_of(d: date) -> int:
    return (day() - d).days


async def _history(client):
    """A user with seven distinct days in last week: weigh-ins Mon, Sat, Sun; workouts Tue, Thu; meals Wed, Fri."""
    h = await _user(client)
    a, b = await _exercise_ids(client, h, 2)
    oil, rice = await _food(client, h, "Olive oil"), await _food(client, h, "White rice, cooked")
    monday, sunday = last_week()
    at = lambda n: offset_of(monday + timedelta(days=n))  # noqa: E731
    await _weigh(client, h, at(0), 84.0)
    await _weigh(client, h, at(5), 83.5)
    await _weigh(client, h, at(6), 83.0)
    await _train(client, h, at(1), [(a, 5, 100, True), (a, 5, 100, True)])
    await _train(client, h, at(3), [(a, 5, 105, True), (b, 8, 50, True), (b, 8, 90, False)])
    await _eat(client, h, at(2), oil, 100)                                  # 884 kcal
    await _eat(client, h, at(2), rice, 200, "dinner")                       # + 260 = 1144
    await _eat(client, h, at(4), oil, 50)                                   # 442
    return h, a, b, monday, sunday


async def _report(client, h, start: date, end: date, status: int = 201) -> dict:
    r = await client.post(f"{BASE}/reports", headers=h, json={"period_start": start.isoformat(),
                                                              "period_end": end.isoformat()})
    assert r.status_code == status, r.text
    return r.json()


async def test_every_report_route_needs_authentication(client):
    for method, path in (("get", "/reports"), ("post", "/reports"), ("get", "/reports/1"),
                         ("get", "/reports/1/export?format=csv")):
        assert (await client.request(method, BASE + path)).status_code == 401, path


async def test_a_weekly_report_has_the_hand_computed_figures(client):
    h, a, b, monday, sunday = await _history(client)
    report = await _report(client, h, monday, sunday)
    assert report["report_type"] == "weekly"
    assert (report["period_start"], report["period_end"]) == (monday.isoformat(), sunday.isoformat())
    assert report["weight_difference_kg"] == -1.0                         # 83.0 - 84.0
    assert report["training_volume_kg"] == 1925.0                         # 1000 + 525 + 400; the failed set is out
    assert report["training_sessions_completed"] == 2 and report["training_sessions_planned"] == 0
    assert report["workout_compliance_pct"] is None and report["diet_compliance_pct"] is None   # no plans
    assert report["avg_daily_calories"] == 793                            # (1144 + 442) / 2 eating days
    assert report["estimated_goal_completion_date"] is None and report["irregular_data"] is False
    assert report["is_auto"] is False and report["generated_at"]
    charts = report["details"]["charts"]
    assert [(p["date"], p["value"]) for p in charts["weight"]] == [
        (monday.isoformat(), 84.0), ((monday + timedelta(days=5)).isoformat(), 83.5), (sunday.isoformat(), 83.0)]
    assert [p["value"] for p in charts["tonnage"]] == [1000.0, 925.0]
    assert [p["value"] for p in charts["calories"]] == [1144.0, 442.0]
    assert charts["workouts_per_week"] == [{"date": monday.isoformat(), "value": 2.0}]
    lifts = report["details"]["key_lifts"]
    assert [(k["exercise_id"], k["first_e1rm_kg"], k["best_e1rm_kg"]) for k in lifts] == [
        (a, 116.67, 122.5), (b, 63.33, 63.33)]
    assert report["details"]["goal_prediction"]["status"] == "no_target"


async def test_the_report_type_follows_the_period(client):
    h, *_ = await _history(client)
    today = datetime.now(UTC).date()
    first_of_this_month = today.replace(day=1)
    previous_month_end = first_of_this_month - timedelta(days=1)
    month = await _report(client, h, previous_month_end.replace(day=1), previous_month_end)
    assert month["report_type"] == "monthly"
    monday, _ = last_week()
    assert (await _report(client, h, monday, monday + timedelta(days=5)))["report_type"] == "custom"   # 6 days
    assert (await _report(client, h, monday + timedelta(days=1), monday + timedelta(days=7)))["report_type"] == "custom"
    assert (await _report(client, h, monday, monday))["report_type"] == "custom"                       # one day


async def test_generating_a_period_again_replaces_the_report(client):
    h, a, _, monday, sunday = await _history(client)
    first = await _report(client, h, monday, sunday)
    await _train(client, h, offset_of(monday + timedelta(days=2)), [(a, 10, 20, True)])           # +200 kg
    second = await _report(client, h, monday, sunday)
    assert second["id"] == first["id"] and second["training_volume_kg"] == 2125.0
    assert second["training_sessions_completed"] == 3
    page = (await client.get(f"{BASE}/reports", headers=h)).json()
    assert page["total"] == 1 and page["items"][0]["id"] == first["id"]
    assert (await client.get(f"{BASE}/reports/{first['id']}", headers=h)).json() == second


async def test_list_filters_by_type_and_pages_newest_period_first(client):
    h, _, _, monday, sunday = await _history(client)
    weekly = await _report(client, h, monday, sunday)
    custom_a = await _report(client, h, monday, monday + timedelta(days=2))
    custom_b = await _report(client, h, monday + timedelta(days=3), sunday)
    page = (await client.get(f"{BASE}/reports", headers=h)).json()
    assert (page["total"], page["limit"], page["offset"]) == (3, 20, 0)
    assert [r["id"] for r in page["items"]] == [custom_b["id"], custom_a["id"], weekly["id"]]
    # newest period_start first; the same start (weekly and custom_a): the newer report first
    only = (await client.get(f"{BASE}/reports?report_type=custom", headers=h)).json()
    assert only["total"] == 2 and {r["id"] for r in only["items"]} == {custom_a["id"], custom_b["id"]}
    second = (await client.get(f"{BASE}/reports?limit=1&offset=1", headers=h)).json()
    assert second["total"] == 3 and [r["id"] for r in second["items"]] == [custom_a["id"]]
    assert (await client.get(f"{BASE}/reports?report_type=yearly", headers=h)).status_code == 422
    assert (await client.get(f"{BASE}/reports?limit=0", headers=h)).status_code == 422


async def test_invalid_periods_are_422_with_the_field(client):
    h, _, _, monday, sunday = await _history(client)
    today = datetime.now(UTC).date()

    async def refused(body: dict, field: str, code: str | None = None) -> None:
        r = await client.post(f"{BASE}/reports", headers=h, json=body)
        assert r.status_code == 422 and r.json()["code"] == "validation_error", body
        assert r.json()["details"][0]["field"] == field, r.json()
        if code:
            assert r.json()["details"][0]["code"] == code

    await refused({"period_start": sunday.isoformat(), "period_end": monday.isoformat()}, "period_end")
    await refused({"period_start": monday.isoformat(), "period_end": (today + timedelta(days=1)).isoformat()},
                  "period_end", "in_future")
    await refused({"period_start": (today - timedelta(days=400)).isoformat(), "period_end": today.isoformat()},
                  "period_end", "out_of_range")
    await refused({"period_end": today.isoformat()}, "period_start", "required")
    await refused({"period_start": "yesterday", "period_end": today.isoformat()}, "period_start")
    assert (await client.get(f"{BASE}/reports", headers=h)).json()["total"] == 0                # nothing was stored


async def test_a_report_needs_seven_days_of_history(client):
    h = await _user(client)
    monday, sunday = last_week()
    for n in range(6):
        await _weigh(client, h, offset_of(monday + timedelta(days=n)), 80)
    r = await client.post(f"{BASE}/reports", headers=h, json={"period_start": monday.isoformat(),
                                                              "period_end": sunday.isoformat()})
    assert r.status_code == 422 and r.json()["code"] == "insufficient_data"
    await _weigh(client, h, offset_of(sunday), 80)
    assert (await client.post(f"{BASE}/reports", headers=h, json={
        "period_start": monday.isoformat(), "period_end": sunday.isoformat()})).status_code == 201


async def test_a_report_is_visible_to_its_owner_only(client):
    h, _, _, monday, sunday = await _history(client)
    report = await _report(client, h, monday, sunday)
    other = await _user(client)
    assert (await client.get(f"{BASE}/reports", headers=other)).json() == {"items": [], "total": 0, "limit": 20,
                                                                         "offset": 0}
    for path in (f"/reports/{report['id']}", f"/reports/{report['id']}/export?format=csv",
                 f"/reports/{report['id']}/export?format=pdf", "/reports/999999999"):
        r = await client.get(BASE + path, headers=other)
        assert r.status_code == 404 and r.json()["code"] == "not_found", path


async def test_plan_compliance_and_planned_sessions_in_a_report(client):
    h = await _user(client)
    ex = (await _exercise_ids(client, h, 1))[0]
    plan = (await client.post(f"{BASE}/training-plans/generate", headers=h,
                              json={"goal": "strength", "training_days": 4})).json()
    await client.post(f"{BASE}/training-plans/{plan['id']}/accept", headers=h,
                      json={"start_date": day(13).isoformat()})
    for offset in (1, 3, 5, 10):
        await _train(client, h, offset, [(ex, 5, 50, True)])
    for offset in range(11, 15):
        await _weigh(client, h, offset, 80)
    report = await _report(client, h, day(13), day())                       # the 14 days of the plan so far
    assert report["training_sessions_completed"] == 4 and report["training_sessions_planned"] == 8   # 4 x 14 / 7
    assert report["workout_compliance_pct"] == 50.0


# ------------------------------------------------------------------ export (FR-R6)

def _csv_rows(content: bytes) -> list[list[str]]:
    assert content.startswith(b"\xef\xbb\xbf")                              # UTF-8 BOM, so that Excel reads it right
    return list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))


async def test_the_csv_repeats_the_report_values(client):
    h, a, b, monday, sunday = await _history(client)
    report = await _report(client, h, monday, sunday)
    r = await client.get(f"{BASE}/reports/{report['id']}/export?format=csv", headers=h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"] == (
        f'attachment; filename="fitplan-report-{monday.isoformat()}-{sunday.isoformat()}.csv"')
    rows = _csv_rows(r.content)
    assert rows[0] == ["section", "key", "value"] and all(len(row) == 3 for row in rows)
    summary = {key: value for section, key, value in rows if section == "summary"}
    for key in ("report_type", "period_start", "period_end", "generated_at"):
        assert summary[key] == str(report[key]), key
    for key in ("weight_difference_kg", "training_volume_kg", "workout_compliance_pct", "diet_compliance_pct",
                "avg_daily_calories", "training_sessions_completed", "training_sessions_planned"):
        expected = report[key]
        assert (summary[key] == "") if expected is None else float(summary[key]) == expected, key
    assert summary["irregular_data"] == "false" and summary["is_auto"] == "false"
    assert summary["estimated_goal_completion_date"] == ""
    for name in ("weight", "tonnage", "calories", "workouts_per_week"):
        exported = [(key, float(value)) for section, key, value in rows if section == name]
        assert exported == [(p["date"], p["value"]) for p in report["details"]["charts"][name]], name
    firsts = {key: float(value) for section, key, value in rows if section == "key_lift_first_e1rm_kg"}
    bests = {key: float(value) for section, key, value in rows if section == "key_lift_best_e1rm_kg"}
    assert firsts == {k["exercise_name"]: k["first_e1rm_kg"] for k in report["details"]["key_lifts"]}
    assert bests == {k["exercise_name"]: k["best_e1rm_kg"] for k in report["details"]["key_lifts"]}
    assert ["goal_prediction", "status", "no_target"] in rows


async def test_the_pdf_opens_and_contains_the_same_figures(client):
    h, a, b, monday, sunday = await _history(client)
    report = await _report(client, h, monday, sunday)
    r = await client.get(f"{BASE}/reports/{report['id']}/export?format=pdf", headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].endswith('.pdf"') and r.content.startswith(b"%PDF-")
    text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(r.content)).pages)
    assert f"{monday.isoformat()} to {sunday.isoformat()} (weekly)" in text
    for expected in ("Weight change (kg)", "-1.0", "Training volume (kg)", "1925.0", "Workouts completed", "793",
                     "Average daily calories (kcal)", "n/a"):
        assert expected in text, expected
    for lift in report["details"]["key_lifts"]:
        assert lift["exercise_name"] in text and str(lift["best_e1rm_kg"]) in text
    for point in report["details"]["charts"]["weight"]:
        assert f"{point['date']}: {point['value']}" in text


async def test_export_rejects_an_unknown_format_and_missing_reports(client):
    h, _, _, monday, sunday = await _history(client)
    report = await _report(client, h, monday, sunday)
    for query in ("", "?format=xlsx", "?format="):
        r = await client.get(f"{BASE}/reports/{report['id']}/export{query}", headers=h)
        assert r.status_code == 422 and r.json()["code"] == "validation_error", query
    assert (await client.get(f"{BASE}/reports/999999/export?format=pdf", headers=h)).status_code == 404
    assert (await client.get(f"{BASE}/reports/{2**70}", headers=h)).status_code == 422
