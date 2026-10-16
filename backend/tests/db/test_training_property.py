"""B-11 'done when': property test over goal x level x equipment x injury on the SEEDED exercise library.

For every combination a plan is either produced and then (a) covers every required muscle group, (b) contains no
exercise excluded by the injuries, (c) respects level and equipment, or `InsufficientExercises` is raised and then
the reported groups really have no eligible exercise. The rules are re-implemented here from algorithms.md 4.2-4.4
on purpose, so the test does not just repeat the code under test.
"""
from __future__ import annotations

import itertools

import pytest
from sqlalchemy import text

from app.domain.constants import EQUIPMENT, LEVELS, MAIN_GROUPS
from app.domain.training import Exercise, Injury, InsufficientExercises, generate_training_plan

GOALS = tuple(MAIN_GROUPS)


@pytest.fixture(scope="module")
def library(seeded_engine):
    with seeded_engine.connect() as c:
        secondary: dict[int, set[str]] = {}
        for exercise_id, group in c.execute(text(
            "select s.exercise_id, g.name from exercise_secondary_muscle_group s"
            " join muscle_group g on g.id = s.muscle_group_id")):
            secondary.setdefault(exercise_id, set()).add(group)
        exercises = [
            Exercise(r[0], r[1], r[2], r[3], r[4], r[5], frozenset(secondary.get(r[0], ())))
            for r in c.execute(text(
                "select e.id, g.name, e.difficulty_level::text, e.equipment::text, e.is_compound, e.is_bodyweight"
                " from exercise e join muscle_group g on g.id = e.main_muscle_group_id order by e.id"))
        ]
        excluded: dict[str, set[int]] = {}
        for injury_type, exercise_id in c.execute(text(
            "select t.name, x.exercise_id from injury_type_excluded_exercise x"
            " join injury_type t on t.id = x.injury_type_id")):
            excluded.setdefault(injury_type, set()).add(exercise_id)
        injury_types = [r[0] for r in c.execute(text("select name from injury_type order by name"))]
        groups = [r[0] for r in c.execute(text("select name from muscle_group order by id"))]
    return exercises, excluded, injury_types, groups


def _blocked(e: Exercise, injury: Injury) -> bool:
    """algorithms.md 4.3, written independently of the implementation."""
    if e.id in injury.excluded_exercise_ids or e.main_group == injury.affected_group:
        return True
    return injury.severity in ("moderate", "severe") and injury.affected_group in e.secondary_groups


def _allowed(e: Exercise, level: str, equipment: str, injuries: list[Injury]) -> bool:
    return (LEVELS.index(e.difficulty) <= LEVELS.index(level) and EQUIPMENT.index(e.equipment) <= EQUIPMENT.index(equipment)
            and not any(_blocked(e, i) for i in injuries))


def _check(exercises, goal, days, level, equipment, injuries):
    by_id = {e.id: e for e in exercises}
    try:
        plan = generate_training_plan(goal, days, level, equipment, exercises, injuries)
    except InsufficientExercises as exc:
        assert exc.empty_groups, "an insufficient result must name at least one group"
        for group in exc.empty_groups:
            assert not any(_allowed(e, level, equipment, injuries) for e in exercises if e.main_group == group), group
        return None
    used = [by_id[e.exercise_id] for s in plan.sessions for e in s.exercises]
    assert used, "a plan must contain exercises"
    required = [g for g in MAIN_GROUPS[goal] if g not in plan.skipped_groups]
    assert {e.main_group for e in used} >= set(required), (goal, level, equipment)  # (a)
    assert all(_allowed(e, level, equipment, injuries) for e in used), (goal, level, equipment, injuries)  # (b), (c)
    for group in plan.skipped_groups:  # skipped only because of the injuries, never silently
        assert group in MAIN_GROUPS[goal]
        assert not any(_allowed(e, level, equipment, injuries) for e in exercises if e.main_group == group)
        assert any(_allowed(e, level, equipment, []) for e in exercises if e.main_group == group)
    assert len(plan.sessions) == days
    for s in plan.sessions:
        assert s.exercises and len({e.exercise_id for e in s.exercises}) == len(s.exercises)  # no repeats in a session
    return plan


def test_every_goal_level_equipment_and_split_without_injuries(library):
    exercises, *_ = library
    produced = 0
    for goal, level, equipment, days in itertools.product(GOALS, LEVELS, EQUIPMENT, range(1, 8)):
        produced += _check(exercises, goal, days, level, equipment, []) is not None
    assert produced == len(GOALS) * len(LEVELS) * len(EQUIPMENT) * 7  # the seed has no gap: always a plan


def test_every_injury_type_on_every_muscle_group(library):
    """17 injury types x 10 affected groups x 3 severities x all goals/levels/equipment (4 sessions a week)."""
    exercises, excluded, injury_types, groups = library
    plans = insufficient = 0
    for injury_type, group, severity in itertools.product(injury_types, groups, ("mild", "moderate", "severe")):
        injury = Injury(severity, group, frozenset(excluded.get(injury_type, ())))
        for goal, level, equipment in itertools.product(("muscle_gain", "strength", "weight_loss"), LEVELS, EQUIPMENT):
            if _check(exercises, goal, 4, level, equipment, [injury]) is None:
                insufficient += 1
            else:
                plans += 1
    assert plans > 0 and plans + insufficient == len(injury_types) * len(groups) * 3 * 3 * 3 * 3


def test_two_simultaneous_injuries(library):
    exercises, excluded, injury_types, groups = library
    for i, first in enumerate(injury_types):
        second = injury_types[-1 - i]
        a = Injury("moderate", groups[i % len(groups)], frozenset(excluded.get(first, ())))
        b = Injury("severe", groups[(3 * i + 1) % len(groups)], frozenset(excluded.get(second, ())))
        for level, equipment in itertools.product(LEVELS, EQUIPMENT):
            _check(exercises, "muscle_gain", 5, level, equipment, [a, b])
