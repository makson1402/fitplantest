"""Reference data and library use cases (B-08, B-09). Rules: docs/algorithms.md 4.9 for alternatives."""
from __future__ import annotations

from app.core.errors import not_found
from app.domain.constants import EQUIPMENT, LEVELS
from app.domain.training import alternatives
from app.repositories import UnitOfWork
from app.repositories.library import ExerciseRecord, FoodRecord
from app.schemas import library as s


def exercise_summary(r: ExerciseRecord) -> s.ExerciseSummary:
    group = s.MuscleGroupRef(id=r.main_muscle_group_id, name=r.main_muscle_group_name)
    return s.ExerciseSummary(
        id=r.id, name=r.name, main_muscle_group=group, difficulty_level=r.difficulty_level, equipment=r.equipment,
        is_compound=r.is_compound, is_bodyweight=r.is_bodyweight,
    )


def food_summary(r: FoodRecord) -> s.FoodSummary:
    return s.FoodSummary(
        id=r.id, name=r.name, calories_per_100g=float(r.calories_per_100g), protein_per_100g=float(r.protein_per_100g),
        fat_per_100g=float(r.fat_per_100g), carbs_per_100g=float(r.carbs_per_100g), role=r.role,
        default_portion_g=r.default_portion_g,
    )


class LibraryService:
    def __init__(self, uow: UnitOfWork):
        self.library = uow.library

    # ------------------------------------------------------------------ dictionaries
    async def muscle_groups(self) -> list[s.MuscleGroup]:
        return [s.MuscleGroup(**vars(r)) for r in await self.library.muscle_groups()]

    async def injury_types(self) -> list[s.InjuryType]:
        return [s.InjuryType(**vars(r)) for r in await self.library.injury_types()]

    async def allergens(self) -> list[s.Allergen]:
        return [s.Allergen(**vars(r)) for r in await self.library.allergens()]

    async def food_categories(self) -> list[s.FoodCategory]:
        return [s.FoodCategory(**vars(r)) for r in await self.library.food_categories()]

    # ------------------------------------------------------------------ exercises
    async def list_exercises(self, *, q: str | None, muscle_group_id: int | None, equipment: str | None,
                             difficulty_level: str | None, limit: int, offset: int) -> s.ExercisePage:
        records, total = await self.library.list_exercises(
            q=q.strip() if q else None, muscle_group_id=muscle_group_id, equipment=equipment,
            difficulty_level=difficulty_level, limit=limit, offset=offset)
        return s.ExercisePage(items=[exercise_summary(r) for r in records], total=total, limit=limit, offset=offset)

    async def get_exercise(self, exercise_id: int) -> s.Exercise:
        record = await self.library.get_exercise(exercise_id)
        if record is None:
            raise not_found("Exercise not found")
        return s.Exercise(
            **exercise_summary(record).model_dump(), description=record.description, instruction=record.instruction,
            secondary_muscle_groups=[s.MuscleGroupRef(id=i, name=n) for i, n in record.secondary_muscle_groups])

    async def alternatives(self, user_id: int, exercise_id: int) -> list[s.ExerciseSummary]:
        """Same-main-group exercises the user can do: level, equipment and injuries respected (FR-A1).

        Without a profile there is no level or equipment to respect, so only the injury rule applies
        (docs/questions.md, B-08)."""
        exercises = await self.library.domain_exercises()
        current = next((e for e in exercises if e.id == exercise_id), None)
        if current is None:
            raise not_found("Exercise not found")
        context = await self.library.training_context(user_id)
        level = context.experience_level or LEVELS[-1]
        equipment = context.equipment or EQUIPMENT[-1]
        chosen = alternatives(current, set(), exercises, level, equipment, context.injuries)
        by_id = {r.id: r for r in await self.library.exercises_by_ids([e.id for e in chosen])}
        # compound first, then by name: a stable, useful order for a swap sheet
        ordered = sorted((by_id[e.id] for e in chosen), key=lambda r: (not r.is_compound, r.name))
        return [exercise_summary(r) for r in ordered]

    # ------------------------------------------------------------------ foods
    async def list_foods(self, *, q: str | None, category_id: int | None, role: str | None, limit: int,
                         offset: int) -> s.FoodPage:
        records, total = await self.library.list_foods(
            q=q.strip() if q else None, category_id=category_id, role=role, limit=limit, offset=offset)
        return s.FoodPage(items=[food_summary(r) for r in records], total=total, limit=limit, offset=offset)

    async def get_food(self, food_id: int) -> s.Food:
        record = await self.library.get_food(food_id)
        if record is None:
            raise not_found("Food not found")
        return s.Food(
            **food_summary(record).model_dump(),
            categories=[s.FoodCategory(**vars(c)) for c in record.categories],
            allergens=[s.Allergen(**vars(a)) for a in record.allergens],
            is_vegetarian=record.is_vegetarian, is_vegan=record.is_vegan, min_portion_g=record.min_portion_g,
            max_portion_g=record.max_portion_g, portion_step_g=record.portion_step_g)
