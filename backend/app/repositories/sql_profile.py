"""SQLAlchemy implementation of `ProfileRepository` (B-06)."""
from __future__ import annotations

from sqlalchemy import delete, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.profile import Injury, UserAllergen, UserExcludedFood, UserProfile
from app.db.models.reference import Allergen, FoodItem, InjuryType, MuscleGroup
from app.repositories.library import FoodRecord, NamedRecord
from app.repositories.profile import InjuryRecord, ProfileRecord
from app.repositories.sql_library import _food

_PROFILE_COLUMNS = (
    "age", "sex", "weight_kg", "height_cm", "activity_level_pal", "goal", "target_weight_kg", "experience_level",
    "equipment", "tdee_kcal",
)


def _profile(row: UserProfile) -> ProfileRecord:
    return ProfileRecord(
        user_id=row.user_id, age=row.age, sex=row.sex, weight_kg=row.weight_kg, height_cm=row.height_cm,
        activity_level_pal=row.activity_level_pal, goal=row.goal, target_weight_kg=row.target_weight_kg,
        experience_level=row.experience_level, equipment=row.equipment, tdee_kcal=row.tdee_kcal,
        updated_at=row.updated_at,
    )


def _injury(row: Injury, type_name: str, group_name: str) -> InjuryRecord:
    return InjuryRecord(
        id=row.id, user_id=row.user_id, injury_type_id=row.injury_type_id, injury_type_name=type_name,
        affected_muscle_group_id=row.affected_muscle_group_id, affected_muscle_group_name=group_name,
        severity=row.severity, start_date=row.start_date, is_active=row.is_active, notes=row.notes,
    )


def _injury_query(*conditions):
    return (select(Injury, InjuryType.name, MuscleGroup.name)
            .join(InjuryType, InjuryType.id == Injury.injury_type_id)
            .join(MuscleGroup, MuscleGroup.id == Injury.affected_muscle_group_id).where(*conditions))


class SqlProfileRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------ profile
    async def get_profile(self, user_id: int) -> ProfileRecord | None:
        row = await self.session.get(UserProfile, user_id, populate_existing=True)
        return _profile(row) if row else None

    async def upsert_profile(self, user_id: int, values: dict) -> ProfileRecord:
        data = {k: values[k] for k in _PROFILE_COLUMNS}
        stmt = pg_insert(UserProfile).values(user_id=user_id, **data)
        stmt = stmt.on_conflict_do_update(index_elements=[UserProfile.user_id], set_=data).returning(UserProfile)
        row = await self.session.scalar(stmt, execution_options={"populate_existing": True})
        return _profile(row)

    # ------------------------------------------------------------------ injuries
    async def list_injuries(self, user_id: int) -> list[InjuryRecord]:
        rows = await self.session.execute(
            _injury_query(Injury.user_id == user_id)
            .order_by(Injury.is_active.desc(), Injury.start_date.desc(), Injury.id.desc()))
        return [_injury(*r) for r in rows]

    async def get_injury(self, user_id: int, injury_id: int) -> InjuryRecord | None:
        row = (await self.session.execute(_injury_query(Injury.id == injury_id, Injury.user_id == user_id))).first()
        return _injury(*row) if row else None

    async def create_injury(self, user_id: int, values: dict) -> InjuryRecord:
        new_id = await self.session.scalar(insert(Injury).values(user_id=user_id, **values).returning(Injury.id))
        return await self.get_injury(user_id, new_id)  # type: ignore[return-value]

    async def update_injury(self, user_id: int, injury_id: int, changes: dict) -> InjuryRecord | None:
        if changes:
            updated = await self.session.scalar(
                update(Injury).where(Injury.id == injury_id, Injury.user_id == user_id).values(**changes)
                .returning(Injury.id))
            if updated is None:
                return None
        return await self.get_injury(user_id, injury_id)

    async def delete_injury(self, user_id: int, injury_id: int) -> bool:
        deleted = await self.session.scalar(
            delete(Injury).where(Injury.id == injury_id, Injury.user_id == user_id).returning(Injury.id))
        return deleted is not None

    async def injury_type_exists(self, injury_type_id: int) -> bool:
        return await self.session.get(InjuryType, injury_type_id) is not None

    async def muscle_group_exists(self, muscle_group_id: int) -> bool:
        return await self.session.get(MuscleGroup, muscle_group_id) is not None

    # ------------------------------------------------------------------ allergens
    async def user_allergens(self, user_id: int) -> list[NamedRecord]:
        rows = await self.session.scalars(
            select(Allergen).join(UserAllergen, UserAllergen.allergen_id == Allergen.id)
            .where(UserAllergen.user_id == user_id).order_by(Allergen.name))
        return [NamedRecord(a.id, a.name, a.description) for a in rows]

    async def existing_allergen_ids(self, ids: list[int]) -> set[int]:
        return set(await self.session.scalars(select(Allergen.id).where(Allergen.id.in_(ids)))) if ids else set()

    async def replace_user_allergens(self, user_id: int, ids: list[int]) -> None:
        await self.session.execute(delete(UserAllergen).where(UserAllergen.user_id == user_id))
        if ids:
            await self.session.execute(insert(UserAllergen), [{"user_id": user_id, "allergen_id": i} for i in ids])

    # ------------------------------------------------------------------ excluded foods
    async def excluded_foods(self, user_id: int) -> list[FoodRecord]:
        rows = await self.session.scalars(
            select(FoodItem).join(UserExcludedFood, UserExcludedFood.food_item_id == FoodItem.id)
            .where(UserExcludedFood.user_id == user_id).order_by(FoodItem.name, FoodItem.id))
        return [_food(f) for f in rows]

    async def existing_food_ids(self, ids: list[int]) -> set[int]:
        if not ids:
            return set()
        return set(await self.session.scalars(select(FoodItem.id).where(FoodItem.id.in_(ids), FoodItem.is_active)))

    async def replace_excluded_foods(self, user_id: int, ids: list[int]) -> None:
        await self.session.execute(delete(UserExcludedFood).where(UserExcludedFood.user_id == user_id))
        if ids:
            await self.session.execute(insert(UserExcludedFood), [{"user_id": user_id, "food_item_id": i} for i in ids])
