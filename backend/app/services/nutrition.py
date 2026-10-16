"""Energy needs and macro targets for the signed-in user (B-10; FR-P4, FR-P5). Formulas: docs/algorithms.md 1-2."""
from __future__ import annotations

from app.core.errors import not_found
from app.domain.nutrition import nutrition_targets
from app.repositories import UnitOfWork, UserRecord
from app.schemas.nutrition import NutritionTargets


class NutritionService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    async def targets(self, user: UserRecord) -> NutritionTargets:
        profile = await self.uow.profile.get_profile(user.id)
        if profile is None:
            raise not_found("Profile not found")  # onboarding (PUT /users/me/profile) comes first
        t = nutrition_targets(profile.sex, float(profile.weight_kg), profile.height_cm, profile.age,
                              float(profile.activity_level_pal), profile.goal)
        return NutritionTargets(bmr_kcal=t.bmr_kcal, tdee_kcal=t.tdee_kcal, target_kcal=t.target_kcal,
                                protein_g=t.protein_g, fat_g=t.fat_g, carbs_g=t.carbs_g, goal=profile.goal)
