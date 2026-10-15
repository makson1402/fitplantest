"""Plan compliance (FR-R2) and minimum-data rule (FR-R5). algorithms.md sections 7-8."""
from __future__ import annotations

from datetime import date, timedelta

from .constants import DIET_COMPLIANCE_TOLERANCE, MIN_DATA_DAYS


def workout_compliance(completed: int, sessions_per_week: int, period_days: int) -> float | None:
    """Percent; planned = sessions per week x (period days / 7). None when nothing was planned."""
    planned = sessions_per_week * period_days / 7
    if planned <= 0:
        return None
    return round(min(completed / planned * 100, 100.0), 1)


def diet_compliance(daily_kcal: dict[date, float], target_kcal: float, start: date, end: date) -> float | None:
    """Share of days in [start, end] with logged calories within +-10 % of the target. Days without logs fail."""
    days = (end - start).days + 1
    if days <= 0 or target_kcal <= 0:
        return None
    ok = sum(1 for i in range(days)
             if (k := daily_kcal.get(start + timedelta(days=i))) is not None
             and abs(k - target_kcal) <= DIET_COMPLIANCE_TOLERANCE * target_kcal)
    return round(ok / days * 100, 1)


def has_enough_data(record_dates: set[date]) -> bool:
    """FR-R5: at least 7 distinct calendar days with any record."""
    return len(record_dates) >= MIN_DATA_DAYS
