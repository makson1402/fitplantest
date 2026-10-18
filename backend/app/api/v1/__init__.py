from fastapi import APIRouter

from app.api.v1 import (
    analytics,
    auth,
    diet,
    health,
    library,
    metrics,
    nutrition,
    nutrition_log,
    profile,
    reports,
    training,
    users,
    workouts,
)

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(library.reference)
router.include_router(library.library)
router.include_router(profile.router)
router.include_router(nutrition.router)
router.include_router(training.router)
router.include_router(training.exercises_router)
router.include_router(diet.router)
router.include_router(workouts.router)
router.include_router(metrics.router)
router.include_router(nutrition_log.router)
router.include_router(analytics.router)
router.include_router(reports.router)
router.include_router(users.router)
