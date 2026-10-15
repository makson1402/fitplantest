import unittest
from datetime import date, timedelta

from app.domain.adaptation import SetLog, adapt, best_new_record, e1rm
from app.domain.compliance import diet_compliance, has_enough_data, workout_compliance
from app.domain.nutrition import nutrition_targets
from app.domain.prediction import predict_goal


class Targets(unittest.TestCase):
    CASES = [
        (("male", 80, 180, 25, 1.55, "muscle_gain"), (1805.0, 2798, 3078, 144.0, 85.5, 433.1)),
        (("female", 60, 165, 30, 1.375, "weight_loss"), (1320.3, 1815, 1452, 120.0, 48.4, 134.1)),
        (("female", 55, 155, 60, 1.2, "weight_loss"), (1057.8, 1269, 1200, 105.0, 40.0, 105.0)),
        (("male", 120, 185, 35, 1.375, "weight_loss"), (2186.3, 3006, 2405, 210.4, 80.2, 210.4)),
    ]

    def test_vectors(self):
        for args, exp in self.CASES:
            t = nutrition_targets(*args)
            self.assertEqual((t.bmr_kcal, t.tdee_kcal, t.target_kcal, t.protein_g, t.fat_g, t.carbs_g), exp, args)


S = SetLog


class Adapt(unittest.TestCase):
    def run_case(self, **kw):
        return adapt(3, 10, **kw)

    def test_cases(self):
        up = dict(is_bodyweight=False, body_region="upper")
        A = self.run_case(planned_weight=60.0, sets=[S(10, 60, True, 6)] * 3, overall_rpe=6, **up)
        self.assertEqual((A.reason, A.sets, A.reps, A.weight_kg), ("progression", 3, 10, 62.5))
        B = self.run_case(planned_weight=100.0, is_bodyweight=False, body_region="lower", sets=[S(10, 100, True, 7)] * 3, overall_rpe=7)
        self.assertEqual((B.reason, B.weight_kg), ("progression", 105.0))
        C = self.run_case(planned_weight=60.0, sets=[S(10, 60, True, 8)] * 3, overall_rpe=9, **up)
        self.assertEqual((C.reason, C.sets, C.reps, C.weight_kg), ("reduce_high_rpe", 3, 10, 55.0))
        D = self.run_case(planned_weight=60.0, sets=[S(10, 60), S(10, 60), S(6, 60, False)], overall_rpe=8, **up)
        self.assertEqual((D.reason, D.weight_kg), ("reduce_incomplete_set", 55.0))
        self.assertIsNone(self.run_case(planned_weight=60.0, sets=[S(10, 60, True, 8)] * 3, overall_rpe=8, **up))   # E
        self.assertIsNone(self.run_case(planned_weight=60.0, sets=[S(10, 60)] * 3, overall_rpe=None, **up))        # F
        G = self.run_case(planned_weight=None, sets=[S(10, 40), S(10, 42.5), S(9, 42.5)], overall_rpe=6, **up)
        self.assertEqual((G.reason, G.sets, G.reps, G.weight_kg), ("baseline", 3, 10, 42.5))
        bw = dict(planned_weight=None, is_bodyweight=True, body_region="upper")
        H = self.run_case(sets=[S(10, 0, True, 6)] * 3, overall_rpe=6, **bw)
        self.assertEqual((H.reason, H.sets, H.reps, H.weight_kg), ("progression", 3, 11, None))
        I = self.run_case(sets=[S(10, 0, True, 9)] * 3, overall_rpe=9, **bw)
        self.assertEqual((I.reason, I.sets, I.reps), ("reduce_high_rpe", 2, 10))
        J = self.run_case(planned_weight=60.0, sets=[S(10, 60, True, 6), S(10, 60, True, 6), S(9, 60, True, 6)], overall_rpe=6, **up)
        self.assertIsNone(J)

    def test_no_signal_never_changes(self):
        # FR-A4: sweep RPE 1..8 with all sets done and no reserve (rpe 8) -> never a reduction
        for rpe in (8,):
            self.assertIsNone(adapt(3, 10, 60.0, False, "upper", [S(10, 60, True, rpe)] * 3, rpe))

    def test_e1rm_and_pr(self):
        self.assertEqual((e1rm(100, 1), e1rm(100, 5), e1rm(60, 10)), (100, 116.67, 80.0))
        sets = [S(5, 100), S(13, 50), S(3, 110, False)]
        rec = best_new_record(sets, None)
        self.assertEqual(rec[1], 116.67)
        self.assertIsNone(best_new_record(sets, 116.67))


class Prediction(unittest.TestCase):
    today = date(2026, 10, 14)

    def test_vectors(self):
        t = self.today
        reg = [(t - timedelta(days=d), round(84.0 - (28 - d) * 0.07, 2)) for d in (28, 25, 21, 18, 14, 11, 7, 4, 0)]
        r = predict_goal(reg, 78.0, t, 90.0)
        self.assertEqual((r["status"], r["estimated_date"], r["slope_kg_per_week"], r["r2"], r["warnings"]),
                         ("ok", "2026-12-11", -0.49, 1.0, []))
        irr = [(t - timedelta(days=d), w) for d, w in [(27, 84.0), (20, 83.1), (19, 84.4), (9, 82.0), (0, 83.5)]]
        r = predict_goal(irr, 78.0, t, 50.0)
        self.assertEqual((r["estimated_date"], r["slope_kg_per_week"], r["r2"], r["warnings"]),
                         ("2027-02-21", -0.26, 0.18, ["low_fit", "low_training_compliance"]))
        gain = [(t - timedelta(days=d), 80.0 + (28 - d) * 0.05) for d in (28, 21, 14, 7, 0)]
        self.assertEqual(predict_goal(gain, 75.0, t)["status"], "moving_away")
        self.assertEqual(predict_goal([(t, 80.0), (t - timedelta(days=2), 80.2)], 75.0, t)["status"], "insufficient_data")
        self.assertEqual(predict_goal(reg, None, t)["status"], "no_target")


class Compliance(unittest.TestCase):
    def test_workout(self):
        self.assertEqual(workout_compliance(6, 3, 14), 100.0)
        self.assertEqual(workout_compliance(3, 3, 14), 50.0)
        self.assertIsNone(workout_compliance(1, 0, 7))

    def test_diet_and_min_data(self):
        d0 = date(2026, 10, 1)
        logs = {d0: 2000, d0 + timedelta(days=1): 2300, d0 + timedelta(days=2): 1850}
        self.assertEqual(diet_compliance(logs, 2000, d0, d0 + timedelta(days=3)), 50.0)   # day0 and day2 ok, day1 +15 %, day3 no log
        self.assertFalse(has_enough_data({d0 + timedelta(days=i) for i in range(6)}))
        self.assertTrue(has_enough_data({d0 + timedelta(days=i) for i in range(7)}))


if __name__ == "__main__":
    unittest.main()
