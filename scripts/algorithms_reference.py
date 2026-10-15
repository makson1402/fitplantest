"""Reference implementation of the formulas in docs/algorithms.md (task D-04).

Purpose: every number in the worked examples of algorithms.md comes from this file, so the
document and the code cannot drift. The backend implements the same rules (B-10, B-16,
B-22, B-24) and should reuse the vectors from `VECTORS` as unit tests.

Run:  python3 scripts/algorithms_reference.py          # print vectors
      python3 scripts/algorithms_reference.py --check   # assert them (CI-friendly)
Needs numpy and scipy only for the goal prediction and the meal scaling demo.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

# --------------------------------------------------------------------------- constants (algorithms.md section 0)
PAL = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "high": 1.725, "very_high": 1.9}
SEX_OFFSET = {"male": 5, "female": -161, "other": -78}          # other = average of the two
GOAL_KCAL_FACTOR = {"weight_loss": 0.80, "muscle_gain": 1.10, "strength": 1.05,
                    "maintenance": 1.00, "general_fitness": 1.00, "endurance": 1.05}
PROTEIN_G_PER_KG = {"weight_loss": 2.0, "muscle_gain": 1.8, "strength": 1.8,
                    "maintenance": 1.6, "general_fitness": 1.6, "endurance": 1.4}
FAT_SHARE_OF_KCAL = {"weight_loss": 0.30, "muscle_gain": 0.25, "strength": 0.25,
                     "maintenance": 0.30, "general_fitness": 0.30, "endurance": 0.20}
KCAL_FLOOR = {"male": 1500, "female": 1200, "other": 1200}
PROTEIN_MAX_SHARE = 0.35
WEIGHT_STEP_KG = 2.5
PROGRESSION_STEP_KG = {"upper": 2.5, "lower": 5.0, "core": 2.5}
REDUCTION_FACTOR = 0.90
RPE_REDUCE_AT = 9
RPE_RESERVE_MAX = 7
BODYWEIGHT_REPS_CAP = 20
PREDICTION_WINDOW_DAYS = 28
PREDICTION_MIN_WEIGHINS = 3
PREDICTION_MIN_SPAN_DAYS = 7
PREDICTION_MIN_SLOPE_KG_PER_DAY = 0.01
PREDICTION_MAX_DAYS = 730
GOAL_REACHED_TOLERANCE_KG = 0.5
PREDICTION_MIN_R2 = 0.5
PREDICTION_MAX_GAP_DAYS = 10
PREDICTION_MIN_WORKOUT_COMPLIANCE = 60.0


def round_half_up(x: float, ndigits: int = 0) -> float:
    q = Decimal(1).scaleb(-ndigits)
    return float(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))


# --------------------------------------------------------------------------- 1-3 energy and macros
def bmr(sex: str, weight_kg: float, height_cm: float, age: int) -> float:
    return 10 * weight_kg + 6.25 * height_cm - 5 * age + SEX_OFFSET[sex]


def tdee(sex: str, weight_kg: float, height_cm: float, age: int, pal: float) -> int:
    return int(round_half_up(bmr(sex, weight_kg, height_cm, age) * pal))


def nutrition_targets(sex, weight_kg, height_cm, age, pal, goal) -> dict:
    t = tdee(sex, weight_kg, height_cm, age, pal)
    kcal = max(int(round_half_up(t * GOAL_KCAL_FACTOR[goal])), KCAL_FLOOR[sex])
    protein = min(PROTEIN_G_PER_KG[goal] * weight_kg, PROTEIN_MAX_SHARE * kcal / 4)
    fat = FAT_SHARE_OF_KCAL[goal] * kcal / 9
    carbs = (kcal - 4 * protein - 9 * fat) / 4
    return {"bmr_kcal": round_half_up(bmr(sex, weight_kg, height_cm, age), 1), "tdee_kcal": t, "target_kcal": kcal,
            "protein_g": round_half_up(protein, 1), "fat_g": round_half_up(fat, 1), "carbs_g": round_half_up(carbs, 1)}


# --------------------------------------------------------------------------- 6 adaptation
@dataclass
class SetLog:
    reps: int
    weight_kg: float
    completed: bool = True
    rpe: int | None = None


def round_to_step(x: float, step: float = WEIGHT_STEP_KG) -> float:
    return round_half_up(x / step) * step


def adapt(planned_sets: int, planned_reps: int, planned_weight: float | None, is_bodyweight: bool,
          body_region: str, sets: list[SetLog], overall_rpe: int | None, workout_high_rpe: bool | None = None):
    """Return (reason, new_sets, new_reps, new_weight) or None when there is no explicit signal.

    `sets` are the logged sets of ONE exercise in the workout.
    """
    if workout_high_rpe is None:
        workout_high_rpe = overall_rpe is not None and overall_rpe >= RPE_REDUCE_AT
    incomplete = any(not s.completed for s in sets)
    reduce = workout_high_rpe or incomplete
    completed_sets = [s for s in sets if s.completed]

    # first time a weighted exercise is logged: take the baseline from the log, nothing else
    if not is_bodyweight and planned_weight is None and completed_sets:
        base = max(s.weight_kg for s in completed_sets) * (REDUCTION_FACTOR if reduce else 1.0)
        return ("baseline", planned_sets, planned_reps, round_to_step(base))

    if reduce:
        if is_bodyweight or planned_weight is None:
            return ("reduce_high_rpe" if workout_high_rpe else "reduce_incomplete_set",
                    max(planned_sets - 1, 2), planned_reps, planned_weight)
        lowered = min(round_to_step(planned_weight * REDUCTION_FACTOR), planned_weight - WEIGHT_STEP_KG)
        return ("reduce_high_rpe" if workout_high_rpe else "reduce_incomplete_set",
                planned_sets, planned_reps, max(lowered, 0.0))

    # progression needs an explicit "reserve" signal: every planned set done at the planned reps and RPE <= 7
    if len(completed_sets) < planned_sets or any(s.reps < planned_reps for s in completed_sets):
        return None
    rpes = [s.rpe for s in completed_sets if s.rpe is not None]
    effort = max(rpes) if rpes else overall_rpe
    if effort is None or effort > RPE_RESERVE_MAX:
        return None
    if is_bodyweight:
        new_reps = min(planned_reps + 1, BODYWEIGHT_REPS_CAP)
        return ("progression", planned_sets, new_reps, planned_weight) if new_reps != planned_reps else None
    used = min(s.weight_kg for s in completed_sets)
    return ("progression", planned_sets, planned_reps, used + PROGRESSION_STEP_KG[body_region])


def e1rm(weight_kg: float, reps: int) -> float:
    return weight_kg if reps == 1 else round_half_up(weight_kg * (1 + reps / 30), 2)


# --------------------------------------------------------------------------- 9 goal prediction
def predict_goal(weighins: list[tuple[date, float]], target_kg: float | None, today: date,
                 workout_compliance_pct: float | None = None) -> dict:
    import numpy as np
    if target_kg is None:
        return {"status": "no_target"}
    pts = [(d, w) for d, w in sorted(weighins) if (today - d).days <= PREDICTION_WINDOW_DAYS]
    if len(pts) < PREDICTION_MIN_WEIGHINS or (pts[-1][0] - pts[0][0]).days < PREDICTION_MIN_SPAN_DAYS:
        return {"status": "insufficient_data"}
    x = np.array([(d - pts[0][0]).days for d, _ in pts], float)
    y = np.array([w for _, w in pts], float)
    slope, intercept = np.polyfit(x, y, 1)
    fitted = slope * x + intercept
    ss_res = float(((y - fitted) ** 2).sum()); ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 if ss_tot == 0 else 1 - ss_res / ss_tot
    current = float(fitted[-1])
    if abs(current - target_kg) <= GOAL_REACHED_TOLERANCE_KG:
        return {"status": "goal_reached", "slope_kg_per_week": float(round(slope * 7, 2)), "r2": float(round(r2, 2))}
    warnings = []
    if r2 < PREDICTION_MIN_R2: warnings.append("low_fit")
    if max((b[0] - a[0]).days for a, b in zip(pts, pts[1:])) > PREDICTION_MAX_GAP_DAYS: warnings.append("gaps")
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
    est = pts[-1][0] + timedelta(days=round(days))
    return {"status": "ok", "estimated_date": est.isoformat(), **out}


# --------------------------------------------------------------------------- 5 meal scaling demo
def scale_meal(foods: list[dict], target: dict, weights=(3.0, 2.0, 1.0, 1.5)):
    """Bounded least squares on relative error. foods: per-100g values and gram bounds. Returns grams."""
    import numpy as np
    from scipy.optimize import lsq_linear
    A = np.array([[f["kcal"], f["protein"], f["fat"], f["carbs"]] for f in foods], float).T   # 4 x n, per 100 g
    t = np.array([target["kcal"], target["protein"], target["fat"], target["carbs"]], float)
    w = np.array(weights, float) / np.maximum(t, 1e-9)
    res = lsq_linear(A * w[:, None], t * w, bounds=([f["min_g"] / 100 for f in foods], [f["max_g"] / 100 for f in foods]))
    grams = []
    for f, x in zip(foods, res.x):
        g = round_half_up(x * 100 / f["step_g"]) * f["step_g"]
        grams.append(int(min(max(g, f["min_g"]), f["max_g"])))
    totals = A @ (np.array(grams) / 100)
    return grams, [round(float(v), 1) for v in totals]


# --------------------------------------------------------------------------- vectors used by the doc and by tests
VECTORS = {
    "targets_male_muscle_gain": (("male", 80, 180, 25, 1.55, "muscle_gain"),
                                 {"bmr_kcal": 1805.0, "tdee_kcal": 2798, "target_kcal": 3078, "protein_g": 144.0, "fat_g": 85.5, "carbs_g": 433.1}),
    "targets_female_weight_loss": (("female", 60, 165, 30, 1.375, "weight_loss"),
                                   {"bmr_kcal": 1320.3, "tdee_kcal": 1815, "target_kcal": 1452, "protein_g": 120.0, "fat_g": 48.4, "carbs_g": 134.1}),
    "targets_floor_applies": (("female", 55, 155, 60, 1.2, "weight_loss"),
                              {"bmr_kcal": 1057.8, "tdee_kcal": 1269, "target_kcal": 1200, "protein_g": 105.0, "fat_g": 40.0, "carbs_g": 105.0}),
    "targets_protein_cap": (("male", 120, 185, 35, 1.375, "weight_loss"),
                            {"bmr_kcal": 2186.3, "tdee_kcal": 3006, "target_kcal": 2405, "protein_g": 210.4, "fat_g": 80.2, "carbs_g": 210.4}),
}


def main(check: bool) -> int:
    ok = True
    print("== nutrition targets")
    for name, (args, expected) in VECTORS.items():
        got = nutrition_targets(*args)
        print(name, args, "->", got)
        if check and expected is not None and got != expected:
            ok = False; print("   MISMATCH, expected", expected)

    print("\n== adaptation vectors (planned 3x10)")
    cases = [
        ("A progression upper, all sets done, RPE 6", dict(planned_weight=60.0, is_bodyweight=False, body_region="upper", sets=[SetLog(10, 60, True, 6)] * 3, overall_rpe=6)),
        ("B progression lower, all sets done, RPE 7", dict(planned_weight=100.0, is_bodyweight=False, body_region="lower", sets=[SetLog(10, 100, True, 7)] * 3, overall_rpe=7)),
        ("C reduce: overall RPE 9", dict(planned_weight=60.0, is_bodyweight=False, body_region="upper", sets=[SetLog(10, 60, True, 8)] * 3, overall_rpe=9)),
        ("D reduce: one set not completed (overall RPE 8)", dict(planned_weight=60.0, is_bodyweight=False, body_region="upper", sets=[SetLog(10, 60), SetLog(10, 60), SetLog(6, 60, False)], overall_rpe=8)),
        ("E no signal: RPE 8, all sets done", dict(planned_weight=60.0, is_bodyweight=False, body_region="upper", sets=[SetLog(10, 60, True, 8)] * 3, overall_rpe=8)),
        ("F no signal: RPE missing", dict(planned_weight=60.0, is_bodyweight=False, body_region="upper", sets=[SetLog(10, 60)] * 3, overall_rpe=None)),
        ("G baseline: first log, weight unknown", dict(planned_weight=None, is_bodyweight=False, body_region="upper", sets=[SetLog(10, 40), SetLog(10, 42.5), SetLog(9, 42.5)], overall_rpe=6)),
        ("H bodyweight progression (+1 rep)", dict(planned_weight=None, is_bodyweight=True, body_region="upper", sets=[SetLog(10, 0, True, 6)] * 3, overall_rpe=6)),
        ("I bodyweight reduce (-1 set)", dict(planned_weight=None, is_bodyweight=True, body_region="upper", sets=[SetLog(10, 0, True, 9)] * 3, overall_rpe=9)),
        ("J reps below plan: no progression", dict(planned_weight=60.0, is_bodyweight=False, body_region="upper", sets=[SetLog(10, 60, True, 6), SetLog(10, 60, True, 6), SetLog(9, 60, True, 6)], overall_rpe=6)),
    ]
    for label, kw in cases:
        print(label, "->", adapt(3, 10, **kw))

    print("\n== e1RM (Epley, reps<=12)")
    for w, r in [(100, 1), (100, 5), (60, 10)]:
        print(f"{w} kg x {r} ->", e1rm(w, r))

    print("\n== goal prediction")
    today = date(2026, 10, 14)
    reg = [(today - timedelta(days=d), 84.0 - (28 - d) * 0.07) for d in (28, 25, 21, 18, 14, 11, 7, 4, 0)]
    print("regular loss 0.5 kg/week, target 78:", predict_goal([(d, round(w, 2)) for d, w in reg], 78.0, today, 90.0))
    irr = [(today - timedelta(days=d), w) for d, w in [(27, 84.0), (20, 83.1), (19, 84.4), (9, 82.0), (0, 83.5)]]
    print("irregular:", predict_goal(irr, 78.0, today, 50.0))
    gain = [(today - timedelta(days=d), 80.0 + (28 - d) * 0.05) for d in (28, 21, 14, 7, 0)]
    print("moving away from goal (target 75):", predict_goal(gain, 75.0, today))
    print("too little data:", predict_goal([(today, 80.0), (today - timedelta(days=2), 80.2)], 75.0, today))

    print("\n== meal scaling demo (lunch of the male muscle_gain example, share 0.35)")
    foods = [
        dict(name="chicken breast, cooked", kcal=165, protein=31.0, fat=3.6, carbs=0.0, min_g=80, max_g=300, step_g=5),
        dict(name="white rice, cooked", kcal=130, protein=2.7, fat=0.3, carbs=28.0, min_g=100, max_g=450, step_g=5),
        dict(name="broccoli, cooked", kcal=35, protein=2.4, fat=0.4, carbs=7.2, min_g=80, max_g=250, step_g=10),
        dict(name="olive oil", kcal=884, protein=0.0, fat=100.0, carbs=0.0, min_g=5, max_g=30, step_g=5),
    ]
    share = 0.35
    t = nutrition_targets("male", 80, 180, 25, 1.55, "muscle_gain")
    target = dict(kcal=t["target_kcal"] * share, protein=t["protein_g"] * share, fat=t["fat_g"] * share, carbs=t["carbs_g"] * share)
    print("meal target:", {k: round(v, 1) for k, v in target.items()})
    grams, totals = scale_meal(foods, target)
    print("grams:", dict(zip([f["name"] for f in foods], grams)))
    print("totals kcal/P/F/C:", totals)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv))
