"""Report periods (algorithms.md section 8): weekly = ISO week Monday-Sunday, monthly = calendar month, else custom."""
from __future__ import annotations

import calendar
from datetime import date


def classify_period(start: date, end: date) -> str:
    if start.weekday() == 0 and (end - start).days == 6:
        return "weekly"
    if start.day == 1 and end == date(start.year, start.month, calendar.monthrange(start.year, start.month)[1]):
        return "monthly"
    return "custom"
