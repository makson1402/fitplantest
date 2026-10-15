"""Goal date prediction (FR-R4). algorithms.md section 9."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from .constants import (GOAL_REACHED_TOLERANCE_KG, PREDICTION_MAX_DAYS, PREDICTION_MAX_GAP_DAYS,
                        PREDICTION_MIN_R2, PREDICTION_MIN_SLOPE_KG_PER_DAY, PREDICTION_MIN_SPAN_DAYS,
                        PREDICTION_MIN_WEIGHINS, PREDICTION_MIN_WORKOUT_COMPLIANCE, PREDICTION_WINDOW_DAYS)


def predict_goal(weighins: list[tuple[date, float]], target_kg: float | None, today: date,
                 workout_compliance_pct: float | None = None) -> dict:
    if target_kg is None:
        return {"status": "no_target"}
    pts = [(d, w) for d, w in sorted(weighins) if 0 <= (today - d).days <= PREDICTION_WINDOW_DAYS]
    if len(pts) < PREDICTION_MIN_WEIGHINS or (pts[-1][0] - pts[0][0]).days < PREDICTION_MIN_SPAN_DAYS:
        return {"status": "insufficient_data"}
    x = np.array([(d - pts[0][0]).days for d, _ in pts], float)
    y = np.array([w for _, w in pts], float)
    slope, intercept = np.polyfit(x, y, 1)
    fitted = slope * x + intercept
    ss_res = float(((y - fitted) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 if ss_tot == 0 else 1 - ss_res / ss_tot
    current = float(fitted[-1])
    if abs(current - target_kg) <= GOAL_REACHED_TOLERANCE_KG:
        return {"status": "goal_reached", "slope_kg_per_week": float(round(slope * 7, 2)), "r2": float(round(r2, 2)),
                "warnings": []}
    warnings: list[str] = []
    if r2 < PREDICTION_MIN_R2:
        warnings.append("low_fit")
    if max((b[0] - a[0]).days for a, b in zip(pts, pts[1:])) > PREDICTION_MAX_GAP_DAYS:
        warnings.append("gaps")
    if workout_compliance_pct is not None and workout_compliance_pct < PREDICTION_MIN_WORKOUT_COMPLIANCE:
        warnings.append("low_training_compliance")
    need = target_kg - current
    out = {"slope_kg_per_week": float(round(slope * 7, 2)), "r2": float(round(r2, 2)), "warnings": warnings}
    if abs(slope) < PREDICTION_MIN_SLOPE_KG_PER_DAY:
        return {"status": "no_progress", **out}
    if need * slope < 0:
        return {"status": "moving_away", **out}
    days = need / slope
    if days > PREDICTION_MAX_DAYS:
        return {"status": "no_progress", **out}
    return {"status": "ok", "estimated_date": (pts[-1][0] + timedelta(days=round(days))).isoformat(), **out}
