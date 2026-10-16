"""Body measurements (B-17; FR-R1, FR-U6): one live measurement per user and day; the newest is the current weight."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import uuid4

from app.core.clock import Clock
from app.core.errors import AppError, not_found
from app.domain.nutrition import tdee
from app.repositories import UnitOfWork, UserRecord
from app.repositories.metrics import BodyMetricsRecord
from app.schemas import metrics as s
from app.services.training import today_for

_TWO = Decimal("0.01")
_MEASUREMENTS = ("chest_cm", "waist_cm", "thigh_cm", "bicep_cm", "hip_cm", "calf_cm", "body_fat_percent")
_MAX_CIRCUMFERENCE = 999.99  # numeric(5,2)


def _dec(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value)).quantize(_TWO, rounding=ROUND_HALF_UP)


def serialize(r: BodyMetricsRecord) -> s.BodyMetrics:
    def num(v):
        return float(v) if v is not None else None
    return s.BodyMetrics(
        id=r.id, client_uuid=r.client_uuid, measured_on=r.measured_on, weight_kg=float(r.weight_kg),
        chest_cm=num(r.chest_cm), waist_cm=num(r.waist_cm), thigh_cm=num(r.thigh_cm), bicep_cm=num(r.bicep_cm),
        hip_cm=num(r.hip_cm), calf_cm=num(r.calf_cm), body_fat_percent=num(r.body_fat_percent),
        updated_at=r.updated_at)


class BodyMetricsService:
    def __init__(self, uow: UnitOfWork, clock: Clock):
        self.uow, self.clock = uow, clock
        self.repo = uow.metrics

    def _values(self, user: UserRecord, body: s.BodyMetricsInput) -> dict:
        problems = []
        if body.measured_on > today_for(user, self.clock) + timedelta(days=1):
            problems.append({"field": "measured_on", "code": "future_date", "message": "Cannot be in the future"})
        for name in _MEASUREMENTS[:-1]:
            value = getattr(body, name)
            if value is not None and value > _MAX_CIRCUMFERENCE:
                problems.append({"field": name, "code": "out_of_range", "message": "Must be below 1000 cm"})
        if problems:
            raise AppError(422, "validation_error", "Invalid input", problems)
        return {"measured_on": body.measured_on, "weight_kg": _dec(body.weight_kg),
                **{name: _dec(getattr(body, name)) for name in _MEASUREMENTS}}

    async def save(self, user: UserRecord, body: s.BodyMetricsInput) -> s.BodyMetrics:
        """Save a measurement. Same `client_uuid` or same day: the existing one is updated, never duplicated."""
        values = self._values(user, body)
        await self.uow.training.lock_user(user.id)  # serialise saves of one user (one measurement per day)
        target = None
        if body.client_uuid is not None:
            known = await self.repo.find_by_client_uuid(user.id, body.client_uuid)
            if known is not None and known.deleted_at is not None:
                raise AppError(409, "conflict", "A measurement with this client_uuid was deleted")
            target = known
        same_day = await self.repo.find_by_day(user.id, body.measured_on)
        if target is not None and same_day is not None and same_day.id != target.id:
            raise AppError(409, "conflict", "Another measurement already exists for that day")
        target = target or same_day
        if target is None:
            record = await self.repo.insert(user.id, {**values, "client_uuid": body.client_uuid or uuid4()})
        else:
            record = await self.repo.update(user.id, target.id, values)  # type: ignore[assignment]
        await self._sync_profile_weight(user)
        await self.uow.commit()
        return serialize(record)

    async def _sync_profile_weight(self, user: UserRecord) -> None:
        """The newest measurement is the current weight: copy it to the profile and recompute the TDEE."""
        latest = await self.repo.latest(user.id)
        profile = await self.uow.profile.get_profile(user.id)
        if latest is None or profile is None or profile.weight_kg == latest.weight_kg:
            return
        value = tdee(profile.sex, float(latest.weight_kg), profile.height_cm, profile.age,
                     float(profile.activity_level_pal))
        await self.uow.profile.update_weight(user.id, latest.weight_kg, value)

    async def list(self, user: UserRecord, date_from: date | None, date_to: date | None) -> list[s.BodyMetrics]:
        return [serialize(r) for r in await self.repo.list(user.id, date_from, date_to)]

    async def delete(self, user: UserRecord, record_id: int) -> None:
        await self.uow.training.lock_user(user.id)
        if not await self.repo.soft_delete(user.id, record_id, self.clock.now()):
            raise not_found("Measurement not found")
        await self._sync_profile_weight(user)
        await self.uow.commit()
