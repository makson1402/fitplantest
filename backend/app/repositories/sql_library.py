"""SQLAlchemy implementation of `LibraryRepository` (B-08, B-09)."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.profile import Injury, UserProfile
from app.db.models.reference import (
    Allergen,
    Exercise,
    ExerciseSecondaryMuscleGroup,
    FoodCategory,
    FoodCategoryFoodItem,
    FoodItem,
    FoodItemAllergen,
    InjuryType,
    InjuryTypeExcludedExercise,
    MuscleGroup,
)
from app.domain.training import Exercise as DomainExercise
from app.domain.training import Injury as DomainInjury
from app.repositories.library import (
    ExerciseRecord,
    FoodRecord,
    InjuryTypeRecord,
    MuscleGroupRecord,
    NamedRecord,
    TrainingContext,
)


def _like(text: str) -> str:
    """Contains-pattern for ILIKE with the wildcard characters of the user's text escaped."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _exercise(row: Exercise, group_name: str) -> ExerciseRecord:
    return ExerciseRecord(
        id=row.id, name=row.name, main_muscle_group_id=row.main_muscle_group_id, main_muscle_group_name=group_name,
        difficulty_level=row.difficulty_level, equipment=row.equipment, is_compound=row.is_compound,
        is_bodyweight=row.is_bodyweight, description=row.description, instruction=row.instruction,
    )


def _food(row: FoodItem) -> FoodRecord:
    return FoodRecord(
        id=row.id, name=row.name, calories_per_100g=row.calories_per_100g, protein_per_100g=row.protein_per_100g,
        fat_per_100g=row.fat_per_100g, carbs_per_100g=row.carbs_per_100g, role=row.role,
        default_portion_g=row.default_portion_g, is_vegetarian=row.is_vegetarian, is_vegan=row.is_vegan,
        min_portion_g=row.min_portion_g, max_portion_g=row.max_portion_g, portion_step_g=row.portion_step_g,
    )


class SqlLibraryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------ dictionaries
    async def muscle_groups(self) -> list[MuscleGroupRecord]:
        rows = await self.session.scalars(select(MuscleGroup).order_by(MuscleGroup.id))
        return [MuscleGroupRecord(r.id, r.name, r.description, r.image_url, r.body_region) for r in rows]

    async def injury_types(self) -> list[InjuryTypeRecord]:
        rows = await self.session.scalars(select(InjuryType).order_by(InjuryType.name))
        return [InjuryTypeRecord(r.id, r.name, r.description, r.avg_healing_time_days) for r in rows]

    async def allergens(self) -> list[NamedRecord]:
        rows = await self.session.scalars(select(Allergen).order_by(Allergen.name))
        return [NamedRecord(r.id, r.name, r.description) for r in rows]

    async def food_categories(self) -> list[NamedRecord]:
        rows = await self.session.scalars(select(FoodCategory).order_by(FoodCategory.name))
        return [NamedRecord(r.id, r.name, r.description) for r in rows]

    # ------------------------------------------------------------------ exercises
    async def list_exercises(self, *, q: str | None, muscle_group_id: int | None, equipment: str | None,
                             difficulty_level: str | None, limit: int, offset: int) -> tuple[list[ExerciseRecord], int]:
        conditions = []
        if q:
            conditions.append(Exercise.name.ilike(_like(q), escape="\\"))
        if muscle_group_id is not None:
            conditions.append(Exercise.main_muscle_group_id == muscle_group_id)
        if equipment is not None:
            conditions.append(Exercise.equipment == equipment)
        if difficulty_level is not None:
            conditions.append(Exercise.difficulty_level == difficulty_level)
        total = await self.session.scalar(select(func.count()).select_from(Exercise).where(*conditions))
        stmt = (select(Exercise, MuscleGroup.name).join(MuscleGroup, MuscleGroup.id == Exercise.main_muscle_group_id)
                .where(*conditions).order_by(Exercise.name, Exercise.id).limit(limit).offset(offset))
        rows = (await self.session.execute(stmt)).all()
        return [_exercise(e, group) for e, group in rows], total or 0

    async def get_exercise(self, exercise_id: int) -> ExerciseRecord | None:
        row = (await self.session.execute(
            select(Exercise, MuscleGroup.name).join(MuscleGroup, MuscleGroup.id == Exercise.main_muscle_group_id)
            .where(Exercise.id == exercise_id))).first()
        if row is None:
            return None
        record = _exercise(*row)
        secondary = await self.session.execute(
            select(MuscleGroup.id, MuscleGroup.name)
            .join(ExerciseSecondaryMuscleGroup, ExerciseSecondaryMuscleGroup.muscle_group_id == MuscleGroup.id)
            .where(ExerciseSecondaryMuscleGroup.exercise_id == exercise_id).order_by(MuscleGroup.id))
        record.secondary_muscle_groups = [(gid, name) for gid, name in secondary]
        return record

    async def domain_exercises(self) -> list[DomainExercise]:
        secondary: dict[int, set[str]] = {}
        for exercise_id, group in await self.session.execute(
            select(ExerciseSecondaryMuscleGroup.exercise_id, MuscleGroup.name)
            .join(MuscleGroup, MuscleGroup.id == ExerciseSecondaryMuscleGroup.muscle_group_id)
        ):
            secondary.setdefault(exercise_id, set()).add(group)
        rows = await self.session.execute(
            select(Exercise, MuscleGroup.name).join(MuscleGroup, MuscleGroup.id == Exercise.main_muscle_group_id)
            .order_by(Exercise.id))
        return [
            DomainExercise(e.id, group, e.difficulty_level, e.equipment, e.is_compound, e.is_bodyweight,
                           frozenset(secondary.get(e.id, ())))
            for e, group in rows
        ]

    async def exercises_by_ids(self, ids: list[int]) -> list[ExerciseRecord]:
        if not ids:
            return []
        rows = await self.session.execute(
            select(Exercise, MuscleGroup.name).join(MuscleGroup, MuscleGroup.id == Exercise.main_muscle_group_id)
            .where(Exercise.id.in_(ids)))
        return [_exercise(e, group) for e, group in rows]

    async def training_context(self, user_id: int) -> TrainingContext:
        profile = await self.session.get(UserProfile, user_id)
        injuries = []
        rows = await self.session.execute(
            select(Injury, MuscleGroup.name).join(MuscleGroup, MuscleGroup.id == Injury.affected_muscle_group_id)
            .where(Injury.user_id == user_id, Injury.is_active))
        for injury, group in rows:
            excluded = await self.session.scalars(
                select(InjuryTypeExcludedExercise.exercise_id)
                .where(InjuryTypeExcludedExercise.injury_type_id == injury.injury_type_id))
            injuries.append(DomainInjury(injury.severity, group, frozenset(excluded)))
        return TrainingContext(profile.experience_level if profile else None, profile.equipment if profile else None,
                               injuries)

    # ------------------------------------------------------------------ foods
    async def list_foods(self, *, q: str | None, category_id: int | None, role: str | None, limit: int,
                         offset: int) -> tuple[list[FoodRecord], int]:
        conditions = [FoodItem.is_active]
        if q:
            conditions.append(FoodItem.name.ilike(_like(q), escape="\\"))
        if category_id is not None:
            conditions.append(FoodItem.id.in_(
                select(FoodCategoryFoodItem.food_item_id).where(FoodCategoryFoodItem.food_category_id == category_id)))
        if role is not None:
            conditions.append(FoodItem.role == role)
        total = await self.session.scalar(select(func.count()).select_from(FoodItem).where(*conditions))
        rows = await self.session.scalars(
            select(FoodItem).where(*conditions).order_by(FoodItem.name, FoodItem.id).limit(limit).offset(offset))
        return [_food(r) for r in rows], total or 0

    async def get_food(self, food_id: int) -> FoodRecord | None:
        row = await self.session.scalar(select(FoodItem).where(FoodItem.id == food_id, FoodItem.is_active))
        if row is None:
            return None
        record = _food(row)
        categories = await self.session.execute(
            select(FoodCategory).join(FoodCategoryFoodItem, FoodCategoryFoodItem.food_category_id == FoodCategory.id)
            .where(FoodCategoryFoodItem.food_item_id == food_id).order_by(FoodCategory.name))
        record.categories = [NamedRecord(c.id, c.name, c.description) for (c,) in categories]
        allergens = await self.session.execute(
            select(Allergen).join(FoodItemAllergen, FoodItemAllergen.allergen_id == Allergen.id)
            .where(FoodItemAllergen.food_item_id == food_id).order_by(Allergen.name))
        record.allergens = [NamedRecord(a.id, a.name, a.description) for (a,) in allergens]
        return record
