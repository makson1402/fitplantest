from fastapi import APIRouter

from app.api.deps import owned_or_404
from app.core.errors import AppError
from app.main import create_app
from app.repositories import UserRecord


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_health_degraded_when_a_probe_fails(settings):
    from fastapi.testclient import TestClient

    async def up():
        return True

    async def down():
        return False

    app = create_app(settings, health_probes={"postgres": up, "mongo": down})
    assert TestClient(app).get("/api/v1/health").json() == {"status": "degraded", "postgres": "up", "mongo": "down"}


def test_unknown_route_uses_error_model(client):
    r = client.get("/api/v1/nope")
    assert r.status_code == 404 and r.json()["code"] == "not_found" and "message" in r.json()


def test_unhandled_error_is_500_with_error_model(app, client):
    router = APIRouter()

    @router.get("/boom")
    async def boom():
        raise RuntimeError("secret internals")

    app.include_router(router)
    r = client.get("/boom")
    assert r.status_code == 500
    assert r.json() == {"code": "internal_error", "message": "Internal server error"}


def test_owned_or_404():
    class Row:
        def __init__(self, user_id):
            self.user_id = user_id

    me = UserRecord(1, "a@b.pl", None, "UTC", True, None)  # type: ignore[arg-type]
    row = Row(1)
    assert owned_or_404(row, me) is row
    for other in (Row(2), None):
        try:
            owned_or_404(other, me)
            raise AssertionError("expected 404")
        except AppError as e:
            assert (e.status, e.code) == (404, "not_found")
