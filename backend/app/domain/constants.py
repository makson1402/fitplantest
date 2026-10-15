"""All tunable constants in one place (docs/algorithms.md section 0)."""
from __future__ import annotations

PAL = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "high": 1.725, "very_high": 1.9}
SEX_OFFSET = {"male": 5, "female": -161, "other": -78}
GOAL_KCAL_FACTOR = {"weight_loss": 0.80, "muscle_gain": 1.10, "strength": 1.05,
                    "maintenance": 1.00, "general_fitness": 1.00, "endurance": 1.05}
PROTEIN_G_PER_KG = {"weight_loss": 2.0, "muscle_gain": 1.8, "strength": 1.8,
                    "maintenance": 1.6, "general_fitness": 1.6, "endurance": 1.4}
FAT_SHARE_OF_KCAL = {"weight_loss": 0.30, "muscle_gain": 0.25, "strength": 0.25,
                     "maintenance": 0.30, "general_fitness": 0.30, "endurance": 0.20}
KCAL_FLOOR = {"male": 1500, "female": 1200, "other": 1200}
PROTEIN_MAX_SHARE = 0.35

AGE_RANGE = (16, 100)
HEIGHT_RANGE_CM = (120, 250)
WEIGHT_RANGE_KG = (30, 300)

WEIGHT_STEP_KG = 2.5
PROGRESSION_STEP_KG = {"upper": 2.5, "lower": 5.0, "core": 2.5}
REDUCTION_FACTOR = 0.90
RPE_REDUCE_AT = 9
RPE_RESERVE_MAX = 7
BODYWEIGHT_REPS_CAP = 20
PR_MAX_REPS = 12
MIN_SETS = 2

PREDICTION_WINDOW_DAYS = 28
PREDICTION_MIN_WEIGHINS = 3
PREDICTION_MIN_SPAN_DAYS = 7
PREDICTION_MIN_SLOPE_KG_PER_DAY = 0.01
PREDICTION_MAX_DAYS = 730
GOAL_REACHED_TOLERANCE_KG = 0.5
PREDICTION_MIN_R2 = 0.5
PREDICTION_MAX_GAP_DAYS = 10
PREDICTION_MIN_WORKOUT_COMPLIANCE = 60.0

MIN_DATA_DAYS = 7
PLAN_DURATION_DAYS = 56
DIET_COMPLIANCE_TOLERANCE = 0.10
SUGGESTION_MIN_REMAINING_KCAL = 100
SUGGESTION_KCAL_OVERSHOOT = 1.05
SUGGESTION_IDEAL_SHARE = 0.35
SUGGESTION_COUNT = 5
LOW_CONFIDENCE = 0.30
RECOGNITION_TOP_K = 3

LEVELS = ("beginner", "intermediate", "advanced")
EQUIPMENT = ("none", "home", "gym")

MUSCLE_REGION = {
    "chest": "upper", "back": "upper", "shoulders": "upper", "biceps": "upper", "triceps": "upper",
    "quadriceps": "lower", "hamstrings": "lower", "glutes": "lower", "calves": "lower", "core": "core",
}
ALL_GROUPS = tuple(MUSCLE_REGION)
STRENGTH_GROUPS = ("chest", "back", "shoulders", "quadriceps", "hamstrings", "glutes", "core")
MAIN_GROUPS = {"muscle_gain": ALL_GROUPS, **{g: STRENGTH_GROUPS for g in
                ("strength", "weight_loss", "maintenance", "general_fitness", "endurance")}}
# group order for extra slots and for ordering inside a session
GROUP_PRIORITY = ("quadriceps", "back", "chest", "hamstrings", "glutes", "shoulders", "biceps", "triceps", "core", "calves")

SESSION_GROUPS = {
    "Upper": ("chest", "back", "shoulders", "biceps", "triceps"),
    "Lower": ("quadriceps", "hamstrings", "glutes", "calves", "core"),
    "Push": ("chest", "shoulders", "triceps"),
    "Pull": ("back", "biceps", "core"),
    "Legs": ("quadriceps", "hamstrings", "glutes", "calves", "core"),
    "Full Body": ALL_GROUPS,
}
# days -> [(session name, session type, weekday)]
SPLITS = {
    1: [("Full Body", "Full Body", "wed")],
    2: [("Full Body A", "Full Body", "mon"), ("Full Body B", "Full Body", "thu")],
    3: [("Full Body A", "Full Body", "mon"), ("Full Body B", "Full Body", "wed"), ("Full Body C", "Full Body", "fri")],
    4: [("Upper A", "Upper", "mon"), ("Lower A", "Lower", "tue"), ("Upper B", "Upper", "thu"), ("Lower B", "Lower", "fri")],
    5: [("Upper", "Upper", "mon"), ("Lower", "Lower", "tue"), ("Push", "Push", "thu"), ("Pull", "Pull", "fri"), ("Legs", "Legs", "sat")],
    6: [("Push A", "Push", "mon"), ("Pull A", "Pull", "tue"), ("Legs A", "Legs", "wed"),
        ("Push B", "Push", "thu"), ("Pull B", "Pull", "fri"), ("Legs B", "Legs", "sat")],
    7: [("Push A", "Push", "mon"), ("Pull A", "Pull", "tue"), ("Legs A", "Legs", "wed"),
        ("Push B", "Push", "thu"), ("Pull B", "Pull", "fri"), ("Legs B", "Legs", "sat"), ("Full Body", "Full Body", "sun")],
}
EXERCISES_PER_SESSION = {"beginner": 5, "intermediate": 6, "advanced": 7}
MAX_EXERCISES_BEFORE_TRIM = 8
# goal -> (compound (sets, reps, rest_s), isolation (sets, reps, rest_s))
SETS_REPS = {
    "strength": ((5, 5, 180), (3, 8, 90)),
    "muscle_gain": ((4, 8, 120), (3, 12, 75)),
    "weight_loss": ((3, 12, 60), (3, 15, 45)),
    "maintenance": ((3, 10, 90), (2, 12, 60)),
    "general_fitness": ((3, 10, 75), (2, 12, 60)),
    "endurance": ((3, 15, 45), (2, 20, 30)),
}

# meals_per_day -> [(meal type, share of daily kcal)]
MEAL_SLOTS = {
    3: [("breakfast", 0.30), ("lunch", 0.40), ("dinner", 0.30)],
    4: [("breakfast", 0.25), ("lunch", 0.35), ("dinner", 0.30), ("snack", 0.10)],
    5: [("breakfast", 0.25), ("snack", 0.10), ("lunch", 0.30), ("dinner", 0.25), ("snack", 0.10)],
}
SCALING_WEIGHTS = (3.0, 2.0, 1.0, 1.5)       # kcal, protein, fat, carbs
DAY_TOLERANCE = {"kcal": 0.05, "protein": 0.10, "fat": 0.15, "carbs": 0.10}
DIET_MAX_ATTEMPTS = 5
