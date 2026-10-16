"""Biometric profile, injuries, allergies and excluded foods (B-06; FR-U6, FR-U7, FR-P4, FR-P6, FR-N3)."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.core.errors import AppError, not_found
from app.domain.nutrition import tdee
from app.repositories import UnitOfWork, UserRecord
from app.repositories.profile import InjuryRecord, ProfileRecord
from app.schemas import library as lib
from app.schemas import profile as s
from app.services.library import food_summary

_TWO, _THREE = Decimal("0.01"), Decimal("0.001")


def _dec(value: float, places: Decimal = _TWO) -> Decimal:
    """Exact decimal of the JSON number, rounded half up to the places the column stores."""
    return Decimal(str(value)).quantize(places, rounding=ROUND_HALF_UP)


def unknown_ids(field: str, missing: set[int]) -> AppError:
    return AppError(422, "validation_error", "Invalid input", [
        {"field": field, "code": "not_found", "message": f"Unknown id(s): {sorted(missing)}"}])


def _profile(r: ProfileRecord) -> s.Profile:
    return s.Profile(
        age=r.age, sex=r.sex, weight_kg=float(r.weight_kg), height_cm=r.height_cm,
        activity_level_pal=float(r.activity_level_pal), goal=r.goal,
        target_weight_kg=float(r.target_weight_kg) if r.target_weight_kg is not None else None,
        experience_level=r.experience_level, equipment=r.equipment, tdee_kcal=r.tdee_kcal or 0,
        updated_at=r.updated_at)


def _injury(r: InjuryRecord) -> s.Injury:
    return s.Injury(
        id=r.id, injury_type_id=r.injury_type_id, injury_type_name=r.injury_type_name,
        affected_muscle_group_id=r.affected_muscle_group_id, affected_muscle_group_name=r.affected_muscle_group_name,
        severity=r.severity, start_date=r.start_date, is_active=r.is_active, notes=r.notes)


class ProfileService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow
        self.repo = uow.profile

    # ------------------------------------------------------------------ profile
    async def get_profile(self, user: UserRecord) -> s.Profile:
        record = await self.repo.get_profile(user.id)
        if record is None:
            raise not_found("Profile not found")
        return _profile(record)

    async def put_profile(self, user: UserRecord, body: s.ProfileInput) -> s.Profile:
        """Create or replace the profile; TDEE is recomputed from the stored values every time."""
        weight, pal = _dec(body.weight_kg), _dec(body.activity_level_pal, _THREE)  # PAL: 1.375, 1.725
        values = {
            "age": body.age, "sex": body.sex, "weight_kg": weight, "height_cm": body.height_cm,
            "activity_level_pal": pal, "goal": body.goal, "experience_level": body.experience_level,
            "equipment": body.equipment,
            "target_weight_kg": _dec(body.target_weight_kg) if body.target_weight_kg is not None else None,
            "tdee_kcal": tdee(body.sex, float(weight), body.height_cm, body.age, float(pal)),
        }
        record = await self.repo.upsert_profile(user.id, values)
        await self.uow.commit()
        return _profile(record)

    # ------------------------------------------------------------------ injuries
    async def list_injuries(self, user: UserRecord) -> list[s.Injury]:
        return [_injury(r) for r in await self.repo.list_injuries(user.id)]

    async def create_injury(self, user: UserRecord, body: s.InjuryInput) -> s.Injury:
        problems = []
        if not await self.repo.injury_type_exists(body.injury_type_id):
            problems.append({"field": "injury_type_id", "code": "not_found", "message": "Unknown injury type"})
        if not await self.repo.muscle_group_exists(body.affected_muscle_group_id):
            problems.append({"field": "affected_muscle_group_id", "code": "not_found",
                             "message": "Unknown muscle group"})
        if problems:
            raise AppError(422, "validation_error", "Invalid input", problems)
        record = await self.repo.create_injury(user.id, body.model_dump())
        await self.uow.commit()
        return _injury(record)

    async def update_injury(self, user: UserRecord, injury_id: int, body: s.InjuryUpdate) -> s.Injury:
        # Only fields the client sent: `notes: null` clears the note, an absent `notes` leaves it alone.
        changes = {k: v for k, v in body.model_dump().items() if k in body.model_fields_set}
        record = await self.repo.update_injury(user.id, injury_id, changes)
        if record is None:
            raise not_found("Injury not found")
        await self.uow.commit()
        return _injury(record)

    async def delete_injury(self, user: UserRecord, injury_id: int) -> None:
        if not await self.repo.delete_injury(user.id, injury_id):
            raise not_found("Injury not found")
        await self.uow.commit()

    # ------------------------------------------------------------------ allergies
    async def get_allergies(self, user: UserRecord) -> list[lib.Allergen]:
        return [lib.Allergen(**vars(a)) for a in await self.repo.user_allergens(user.id)]

    async def put_allergies(self, user: UserRecord, body: s.AllergyList) -> list[lib.Allergen]:
        ids = list(dict.fromkeys(body.allergen_ids))  # drop duplicates, keep order
        missing = set(ids) - await self.repo.existing_allergen_ids(ids)
        if missing:
            raise unknown_ids("allergen_ids", missing)
        await self.repo.replace_user_allergens(user.id, ids)
        await self.uow.commit()
        return await self.get_allergies(user)

    # ------------------------------------------------------------------ excluded foods
    async def get_excluded_foods(self, user: UserRecord) -> list[lib.FoodSummary]:
        return [food_summary(f) for f in await self.repo.excluded_foods(user.id)]

    async def put_excluded_foods(self, user: UserRecord, body: s.ExcludedFoodList) -> list[lib.FoodSummary]:
        ids = list(dict.fromkeys(body.food_item_ids))
        missing = set(ids) - await self.repo.existing_food_ids(ids)
        if missing:
            raise unknown_ids("food_item_ids", missing)
        await self.repo.replace_excluded_foods(user.id, ids)
        await self.uow.commit()
        return await self.get_excluded_foods(user)
