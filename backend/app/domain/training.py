"""Training plan generation (FR-P1, P2, P3) and swap alternatives (FR-A1). algorithms.md section 4."""
from __future__ import annotations

from dataclasses import dataclass, field

from .constants import (EQUIPMENT, EXERCISES_PER_SESSION, GROUP_PRIORITY, LEVELS, MAIN_GROUPS, MAX_EXERCISES_BEFORE_TRIM,
                        MIN_SETS, SESSION_GROUPS, SETS_REPS, SPLITS)


@dataclass(frozen=True)
class Exercise:
    id: int
    main_group: str
    difficulty: str                      # beginner | intermediate | advanced
    equipment: str                       # none | home | gym
    is_compound: bool = False
    is_bodyweight: bool = False
    secondary_groups: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Injury:
    severity: str                        # mild | moderate | severe
    affected_group: str | None = None
    excluded_exercise_ids: frozenset[int] = frozenset()


@dataclass(frozen=True)
class PlannedExercise:
    exercise_id: int
    position: int
    sets: int
    reps: int
    rest_s: int


@dataclass(frozen=True)
class PlannedSession:
    name: str
    weekday: str
    groups: tuple[str, ...]
    exercises: tuple[PlannedExercise, ...]
    duration_min: int


@dataclass(frozen=True)
class TrainingPlan:
    sessions: tuple[PlannedSession, ...]
    skipped_groups: tuple[str, ...] = ()


class InsufficientExercises(Exception):
    """FR-P3. `empty_groups` cannot be covered; `suggestions` hold change_equipment / change_goal."""

    def __init__(self, empty_groups: list[str], suggestions: dict):
        super().__init__(f"no eligible exercise for: {', '.join(empty_groups)}")
        self.empty_groups = empty_groups
        self.suggestions = suggestions


def _excluded(e: Exercise, injuries: list[Injury]) -> bool:
    for inj in injuries:
        if e.id in inj.excluded_exercise_ids:
            return True
        if inj.affected_group is not None:
            if e.main_group == inj.affected_group:
                return True
            if inj.severity in ("moderate", "severe") and inj.affected_group in e.secondary_groups:
                return True
    return False


def eligible_exercises(exercises: list[Exercise], level: str, equipment: str, injuries: list[Injury],
                       apply_injuries: bool = True) -> list[Exercise]:
    lv, eq = LEVELS.index(level), EQUIPMENT.index(equipment)
    return [e for e in exercises
            if LEVELS.index(e.difficulty) <= lv and EQUIPMENT.index(e.equipment) <= eq
            and not (apply_injuries and _excluded(e, injuries))]


def _classify(exercises, goal, level, equipment, injuries):
    """Return (skipped_groups, empty_groups) for the goal's main groups."""
    with_inj = {e.main_group for e in eligible_exercises(exercises, level, equipment, injuries)}
    without_inj = {e.main_group for e in eligible_exercises(exercises, level, equipment, injuries, False)}
    skipped, empty = [], []
    for g in MAIN_GROUPS[goal]:
        if g in with_inj:
            continue
        (skipped if g in without_inj else empty).append(g)
    return skipped, empty


def _suggestions(exercises, goal, level, equipment, injuries) -> dict:
    out: dict = {}
    for eq in EQUIPMENT[EQUIPMENT.index(equipment) + 1:]:
        if not _classify(exercises, goal, level, eq, injuries)[1]:
            out["change_equipment"] = eq
            break
    goals = [g for g in MAIN_GROUPS if g != goal and not _classify(exercises, g, level, equipment, injuries)[1]]
    if goals:
        out["change_goal"] = goals
    return out


def _session_group_lists(days: int, required: list[str]) -> list[list[str]]:
    lists = []
    for _name, kind, _wd in SPLITS[days]:
        lists.append([g for g in SESSION_GROUPS[kind] if g in required])
    covered = {g for l in lists for g in l}
    for g in required:
        if g not in covered:
            min(lists, key=len).append(g)
    return [l if l else list(required) for l in lists]


def _sets_reps(goal: str, level: str, compound: bool) -> tuple[int, int, int]:
    sets, reps, rest = SETS_REPS[goal][0 if compound else 1]
    if level == "beginner":
        sets = max(sets - 1, MIN_SETS)
    return sets, reps, rest


def generate_training_plan(goal: str, days: int, level: str, equipment: str,
                           exercises: list[Exercise], injuries: list[Injury] | None = None) -> TrainingPlan:
    injuries = injuries or []
    skipped, empty = _classify(exercises, goal, level, equipment, injuries)
    if empty:
        raise InsufficientExercises(empty, _suggestions(exercises, goal, level, equipment, injuries))
    required = [g for g in MAIN_GROUPS[goal] if g not in skipped]
    if not required:                      # everything blocked by injuries: nothing can be trained safely
        raise InsufficientExercises(list(skipped), {})
    pool: dict[str, list[Exercise]] = {}
    for e in eligible_exercises(exercises, level, equipment, injuries):
        if e.main_group in required:
            pool.setdefault(e.main_group, []).append(e)
    for g in pool:
        pool[g].sort(key=lambda e: (not e.is_compound, -LEVELS.index(e.difficulty), e.id))

    group_lists = _session_group_lists(days, required)
    occurrence: dict[str, int] = {}
    sessions: list[PlannedSession] = []
    for (name, _kind, weekday), groups in zip(SPLITS[days], group_lists):
        target = max(EXERCISES_PER_SESSION[level], len(groups))
        picks = {g: 1 for g in groups}
        order = [g for g in GROUP_PRIORITY if g in groups]
        slots = target - len(groups)
        while slots > 0:
            progressed = False
            for g in order:
                if slots > 0 and picks[g] < len(pool[g]):
                    picks[g] += 1
                    slots -= 1
                    progressed = True
            if not progressed:
                break
        chosen: list[Exercise] = []
        for g in groups:
            k = occurrence.get(g, 0)
            occurrence[g] = k + 1
            n = len(pool[g])
            start = (k * picks[g]) % n
            chosen.extend(pool[g][(start + i) % n] for i in range(picks[g]))
        chosen.sort(key=lambda e: (not e.is_compound, GROUP_PRIORITY.index(e.main_group), e.id))
        trim = 1 if len(chosen) > MAX_EXERCISES_BEFORE_TRIM else 0
        planned = []
        total = 600
        for pos, e in enumerate(chosen, start=1):
            sets, reps, rest = _sets_reps(goal, level, e.is_compound)
            sets = max(sets - trim, MIN_SETS)
            planned.append(PlannedExercise(e.id, pos, sets, reps, rest))
            total += sets * (45 + rest)
        sessions.append(PlannedSession(name, weekday, tuple(groups), tuple(planned), -(-total // 300) * 5))
    return TrainingPlan(tuple(sessions), tuple(skipped))


def alternatives(current: Exercise, session_exercise_ids: set[int], exercises: list[Exercise],
                 level: str, equipment: str, injuries: list[Injury] | None = None) -> list[Exercise]:
    """FR-A1: eligible exercises of the same main group, excluding the current and those already in the session."""
    return [e for e in eligible_exercises(exercises, level, equipment, injuries or [])
            if e.main_group == current.main_group and e.id != current.id and e.id not in session_exercise_ids]


def is_valid_swap(current: Exercise, candidate: Exercise, session_exercise_ids: set[int], exercises: list[Exercise],
                  level: str, equipment: str, injuries: list[Injury] | None = None) -> bool:
    return any(a.id == candidate.id for a in alternatives(current, session_exercise_ids, exercises, level, equipment, injuries))
