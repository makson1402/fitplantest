from fastapi import APIRouter

from app.api.v1 import auth, diet, health, library, nutrition, profile, training

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
