"""Adaptation and progression (FR-A4, FR-A5), personal records. algorithms.md section 6.

`adapt` returns None when there is no explicit signal: the plan is never changed without one.
"""
from __future__ import annotations

from dataclasses import dataclass

from .constants import (BODYWEIGHT_REPS_CAP, MIN_SETS, PR_MAX_REPS, PROGRESSION_STEP_KG, REDUCTION_FACTOR,
                        RPE_REDUCE_AT, RPE_RESERVE_MAX, WEIGHT_STEP_KG)
from .rounding import round_half_up


@dataclass(frozen=True)
class SetLog:
    reps: int
    weight_kg: float
    completed: bool = True
    rpe: int | None = None


@dataclass(frozen=True)
class Adjustment:
    reason: str            # baseline | reduce_high_rpe | reduce_incomplete_set | progression
    sets: int
    reps: int
    weight_kg: float | None


def round_to_step(x: float, step: float = WEIGHT_STEP_KG) -> float:
    return round_half_up(x / step) * step


def adapt(planned_sets: int, planned_reps: int, planned_weight: float | None, is_bodyweight: bool,
          body_region: str, sets: list[SetLog], overall_rpe: int | None,
          workout_high_rpe: bool | None = None) -> Adjustment | None:
    """`sets` are the logged sets of ONE exercise in the workout."""
    if workout_high_rpe is None:
        workout_high_rpe = overall_rpe is not None and overall_rpe >= RPE_REDUCE_AT
    incomplete = any(not s.completed for s in sets)
    reduce = workout_high_rpe or incomplete
    reason = "reduce_high_rpe" if workout_high_rpe else "reduce_incomplete_set"
    completed = [s for s in sets if s.completed]

    if not is_bodyweight and planned_weight is None and completed:
        base = max(s.weight_kg for s in completed) * (REDUCTION_FACTOR if reduce else 1.0)
        return Adjustment("baseline", planned_sets, planned_reps, round_to_step(base))

    if reduce:
        if is_bodyweight or planned_weight is None:
            return Adjustment(reason, max(planned_sets - 1, MIN_SETS), planned_reps, planned_weight)
        lowered = min(round_to_step(planned_weight * REDUCTION_FACTOR), planned_weight - WEIGHT_STEP_KG)
        return Adjustment(reason, planned_sets, planned_reps, max(lowered, 0.0))

    if len(completed) < planned_sets or any(s.reps < planned_reps for s in completed):
        return None
    rpes = [s.rpe for s in completed if s.rpe is not None]
    effort = max(rpes) if rpes else overall_rpe
    if effort is None or effort > RPE_RESERVE_MAX:
        return None
    if is_bodyweight:
        new_reps = min(planned_reps + 1, BODYWEIGHT_REPS_CAP)
        return Adjustment("progression", planned_sets, new_reps, planned_weight) if new_reps != planned_reps else None
    used = min(s.weight_kg for s in completed)
    return Adjustment("progression", planned_sets, planned_reps, used + PROGRESSION_STEP_KG[body_region])


def e1rm(weight_kg: float, reps: int) -> float:
    return weight_kg if reps == 1 else round_half_up(weight_kg * (1 + reps / 30), 2)


def best_new_record(sets: list[SetLog], current_e1rm: float | None) -> tuple[SetLog, float] | None:
    """Best counted set (completed, weight > 0, reps <= 12) if it beats the current record."""
    counted = [(s, e1rm(s.weight_kg, s.reps)) for s in sets
               if s.completed and s.weight_kg > 0 and 1 <= s.reps <= PR_MAX_REPS]
    if not counted:
        return None
    best = max(counted, key=lambda p: p[1])
    return best if current_e1rm is None or best[1] > current_e1rm else None
