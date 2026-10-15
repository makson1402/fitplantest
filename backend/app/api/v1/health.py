from fastapi import APIRouter, Request

from app.schemas.common import Health

router = APIRouter(tags=["meta"])


@router.get("/health", operation_id="getHealth", summary="Liveness and dependency status", response_model=Health,
            response_model_exclude_none=True)
async def get_health(request: Request) -> Health:
    # Dependency probes (postgres, mongo, ai_service) register here once those layers exist (DB-01, DB-02, B-18).
    checks = {name: "up" if await probe() else "down" for name, probe in request.app.state.health_probes.items()}
    status = "ok" if all(v == "up" for v in checks.values()) else "degraded"
    return Health(status=status, **checks)
