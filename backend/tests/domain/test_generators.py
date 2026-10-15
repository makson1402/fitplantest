import unittest

from app.domain.constants import ALL_GROUPS, MAIN_GROUPS
from app.domain.diet import Food, InsufficientFoods, eligible_foods, generate_diet
from app.domain.meal_scaling import Macros, Portionable, scale_meal
from app.domain.nutrition import nutrition_targets
from app.domain.suggestions import suggest
from app.domain.training import (Exercise, InsufficientExercises, Injury, alternatives, generate_training_plan,
                                 is_valid_swap)


def catalog(equipment_by_group=None):
    """Per group: 2 gym compound (beginner+intermediate), 1 home isolation, 1 bodyweight (none)."""
    ex, i = [], 1
    for g in ALL_GROUPS:
        ex += [Exercise(i, g, "beginner", "gym", True), Exercise(i + 1, g, "intermediate", "gym", True),
               Exercise(i + 2, g, "beginner", "home", False), Exercise(i + 3, g, "beginner", "none", False, True)]
        i += 10
    return ex


class Training(unittest.TestCase):
    def setUp(self):
        self.ex = catalog()

    def test_all_splits_cover_required_groups_and_are_sane(self):
        for goal in MAIN_GROUPS:
            for days in range(1, 8):
                for level in ("beginner", "advanced"):
                    plan = generate_training_plan(goal, days, level, "gym", self.ex)
                    self.assertEqual(len(plan.sessions), days)
                    covered = {self.byid(e.exercise_id).main_group for s in plan.sessions for e in s.exercises}
                    self.assertEqual(covered, set(MAIN_GROUPS[goal]), (goal, days, level))
                    for s in plan.sessions:
                        ids = [e.exercise_id for e in s.exercises]
                        self.assertEqual(len(ids), len(set(ids)))
                        self.assertGreaterEqual(len(ids), len(s.groups))
                        self.assertEqual([e.position for e in s.exercises], list(range(1, len(ids) + 1)))
                        self.assertTrue(all(e.sets >= 2 for e in s.exercises))
                        self.assertEqual(s.duration_min % 5, 0)

    def byid(self, i):
        return next(e for e in self.ex if e.id == i)

    def test_equipment_and_level_filter(self):
        plan = generate_training_plan("strength", 3, "beginner", "none", self.ex)
        for s in plan.sessions:
            for e in s.exercises:
                self.assertEqual(self.byid(e.exercise_id).equipment, "none")

    def test_insufficient_exercises_has_suggestions(self):
        ex = [e for e in self.ex if not (e.main_group == "back" and e.equipment != "gym")]
        ex = [e for e in ex if not (e.main_group == "back" and e.difficulty == "beginner")]      # back only intermediate gym
        with self.assertRaises(InsufficientExercises) as cm:
            generate_training_plan("strength", 3, "beginner", "gym", ex)
        self.assertEqual(cm.exception.empty_groups, ["back"])

    def test_change_equipment_suggestion(self):
        ex = [e for e in self.ex if not (e.main_group == "back" and e.equipment != "gym")]
        with self.assertRaises(InsufficientExercises) as cm:
            generate_training_plan("strength", 3, "beginner", "home", ex)
        self.assertEqual(cm.exception.suggestions.get("change_equipment"), "gym")

    def test_injury_skips_group_and_excludes_exercises(self):
        inj = [Injury("severe", "quadriceps")]
        plan = generate_training_plan("strength", 3, "beginner", "gym", self.ex, inj)
        self.assertEqual(plan.skipped_groups, ("quadriceps",))
        used = {e.exercise_id for s in plan.sessions for e in s.exercises}
        self.assertFalse(any(self.byid(i).main_group == "quadriceps" for i in used))
        inj2 = [Injury("mild", None, frozenset({1}))]
        plan2 = generate_training_plan("strength", 3, "beginner", "gym", self.ex, inj2)
        self.assertNotIn(1, {e.exercise_id for s in plan2.sessions for e in s.exercises})

    def test_secondary_group_rule(self):
        ex = self.ex + [Exercise(900, "chest", "beginner", "gym", True, False, frozenset({"shoulders"}))]
        mild = generate_training_plan("strength", 1, "beginner", "gym", ex, [Injury("mild", "shoulders")])
        severe = generate_training_plan("strength", 1, "beginner", "gym", ex, [Injury("severe", "shoulders")])
        used_m = {e.exercise_id for s in mild.sessions for e in s.exercises}
        used_s = {e.exercise_id for s in severe.sessions for e in s.exercises}
        self.assertNotIn(900, used_s)
        self.assertEqual(severe.skipped_groups, ("shoulders",))

    def test_swap(self):
        cur = self.byid(1)
        alts = alternatives(cur, {1, 2}, self.ex, "beginner", "gym")
        self.assertEqual({a.id for a in alts}, {3, 4})
        self.assertTrue(is_valid_swap(cur, self.byid(3), {1}, self.ex, "beginner", "gym"))
        self.assertFalse(is_valid_swap(cur, self.byid(11), {1}, self.ex, "beginner", "gym"))     # other group
        self.assertFalse(is_valid_swap(cur, self.byid(2), {1}, self.ex, "beginner", "gym"))      # intermediate > beginner

    def test_deterministic(self):
        a = generate_training_plan("muscle_gain", 4, "intermediate", "gym", self.ex)
        b = generate_training_plan("muscle_gain", 4, "intermediate", "gym", self.ex)
        self.assertEqual(a, b)


def foods():
    f, i = [], 1
    def add(role, kcal, p, fat, c, mn, mx, st, dflt, mts):
        nonlocal i
        f.append(Food(i, role, Macros(kcal, p, fat, c), mn, mx, st, dflt, frozenset(mts),
                      frozenset({7}) if i == 99 else frozenset(), True, role in ("carb", "vegetable", "fruit", "fat")))
        i += 1
    allm = {"breakfast", "lunch", "dinner", "snack"}
    for kcal, p, fat, c in [(165, 31, 3.6, 0), (120, 22, 2, 1), (200, 26, 10, 0)]:
        add("protein", kcal, p, fat, c, 80, 300, 5, 150, {"lunch", "dinner", "breakfast"})
    for kcal, p, fat, c in [(130, 2.7, 0.3, 28), (360, 12, 2, 68), (250, 8, 3, 48)]:
        add("carb", kcal, p, fat, c, 80, 450, 5, 150, {"lunch", "dinner", "breakfast"})
    for kcal, p, fat, c in [(35, 2.4, 0.4, 7.2), (25, 1.4, 0.2, 5)]:
        add("vegetable", kcal, p, fat, c, 80, 250, 10, 100, {"lunch", "dinner"})
    for kcal, p, fat, c in [(884, 0, 100, 0), (600, 20, 52, 20)]:
        add("fat", kcal, p, fat, c, 5, 40, 5, 10, allm)
    for kcal, p, fat, c in [(52, 0.3, 0.2, 14), (89, 1.1, 0.3, 23)]:
        add("fruit", kcal, p, fat, c, 80, 300, 10, 120, {"breakfast", "snack"})
    add("dairy", 60, 10, 0.4, 3.6, 100, 300, 10, 200, {"breakfast", "snack"})
    return f


class Diet(unittest.TestCase):
    def test_generates_valid_week(self):
        t = nutrition_targets("male", 80, 180, 25, 1.55, "maintenance")
        for mpd in (3, 4, 5):
            plan = generate_diet(t, mpd, foods())
            self.assertEqual(len(plan.meals), 7 * mpd)
            for d in range(1, 8):
                tot = sum(m.totals.kcal for m in plan.meals if m.day_index == d)
                self.assertAlmostEqual(tot / t.target_kcal, 1.0, delta=0.05, msg=(mpd, d))

    def test_low_density_catalog_fails_cleanly(self):
        # every carb below 90 kcal/100 g cannot reach a 2800 kcal target within portion limits
        t = nutrition_targets("male", 80, 180, 25, 1.55, "maintenance")
        light = [f if f.role != "carb" else Food(f.id, f.role, Macros(80, 2, 0.2, 18), f.min_g, 450, 5, 150, f.meal_types)
                 for f in foods()]
        with self.assertRaises(InsufficientFoods):
            generate_diet(t, 3, light)

    def test_allergen_and_vegan_filters(self):
        fs = foods()
        fs.append(Food(99, "protein", Macros(100, 20, 1, 0), 50, 300, 5, 150, frozenset({"lunch"}), frozenset({7}), True, False))
        out = eligible_foods(fs, "lunch", "omnivore", {7}, set())
        self.assertNotIn(99, [f.id for f in out])
        vegan = eligible_foods(foods(), "lunch", "vegan", set(), set())
        self.assertTrue(all(f.is_vegan for f in vegan))
        self.assertNotIn(1, [f.id for f in eligible_foods(foods(), "lunch", "omnivore", set(), {1})])

    def test_insufficient_foods_names_roles(self):
        t = nutrition_targets("male", 80, 180, 25, 1.55, "maintenance")
        fs = [f for f in foods() if f.role != "vegetable"]
        with self.assertRaises(InsufficientFoods) as cm:
            generate_diet(t, 3, fs)
        self.assertTrue(any(m["role"] == "vegetable" for m in cm.exception.missing_roles))

    def test_scaling_example_from_spec(self):
        P = lambda k, p, f, c, mn, mx, st: Portionable(Macros(k, p, f, c), mn, mx, st)
        items = [P(165, 31.0, 3.6, 0.0, 80, 300, 5), P(130, 2.7, 0.3, 28.0, 100, 450, 5),
                 P(35, 2.4, 0.4, 7.2, 80, 250, 10), P(884, 0.0, 100.0, 0.0, 5, 30, 5)]
        t = nutrition_targets("male", 80, 180, 25, 1.55, "muscle_gain")
        target = Macros(t.target_kcal * .35, t.protein_g * .35, t.fat_g * .35, t.carbs_g * .35)
        grams, tot = scale_meal(items, target)
        self.assertEqual(grams, [105, 450, 250, 25])
        self.assertEqual([round(tot.kcal, 1), round(tot.protein, 1), round(tot.fat, 1), round(tot.carbs, 1)],
                         [1066.8, 50.7, 31.1, 144.0])


class Suggestions(unittest.TestCase):
    def test_target_reached_and_ranking(self):
        daily = Macros(2500, 150, 80, 280)
        res, msg = suggest(daily, Macros(2450, 140, 78, 270), foods())
        self.assertEqual((res, msg), ([], "target_reached"))
        res, msg = suggest(daily, Macros(1000, 60, 30, 100), foods())
        self.assertIsNone(msg)
        self.assertEqual(len(res), 5)
        self.assertEqual(res, sorted(res, key=lambda s: s.score))
        rem = 1500
        self.assertTrue(all(s.macros.kcal <= rem * 1.05 for s in res))
        res2, _ = suggest(daily, Macros(1000, 60, 30, 100), foods(), [(5, Macros(1450, 85, 45, 160)), (6, Macros(2000, 1, 1, 1))])
        self.assertNotIn(6, [s.ref_id for s in res2 if s.kind == "planned_meal"])


if __name__ == "__main__":
    unittest.main()
