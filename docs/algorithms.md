# Algorithm specification (task D-04)

Status: DRAFT for gate G1. Values marked **[confirm at G0]** are assumptions; change them in one place (section 0) and in `scripts/algorithms_reference.py`.

Every number in the worked examples is produced by `scripts/algorithms_reference.py` (`python3 scripts/algorithms_reference.py --check`). The backend implements the same rules and reuses those vectors as unit tests.

Rule for implementers: if this document is silent on a behaviour, do not invent one. Write the question in `docs/questions.md` and mark the task blocked.

## 0. Constants and ranges (single source)

| Name | Value | Used in |
| --- | --- | --- |
| Age | 16–100 years **[confirm at G0]** (Polish digital-consent age is 16) | FR-U7 |
| Height | 120–250 cm **[confirm at G0]** | FR-U7 |
| Weight, target weight | 30–300 kg | FR-U7 |
| PAL values offered | sedentary 1.2, light 1.375, moderate 1.55, high 1.725, very high 1.9 (DB accepts 1.20–2.40) | FR-U6 |
| RPE, hunger level | integers 1–10 | FR-A2, FR-A3 |
| Password | 8–72 bytes (bcrypt truncates at 72), at least one letter and one digit | FR-U1 |
| Training days | 1–7 | FR-P1 |
| Meals per day | 3–5 | FR-P6 |
| Photo upload | JPEG, PNG or WebP, at most 8 MB **[confirm at G0]** | FR-N1 |
| Recognition expiry | 6 h | FR-N4 |
| Plan duration | 8 weeks (`end_date = start_date + 56 days`) **[confirm at G0]** | FR-P1 |
| Weight step | 2.5 kg | section 6 |
| Hunger | stored and reported; never changes a plan automatically (no requirement asks for it) | FR-A3 |

Rounding: "round half up". Kcal are integers; grams and macros have one decimal in responses.

## 1. Energy needs (FR-P4)

BMR (Mifflin-St Jeor): `10·kg + 6.25·cm − 5·age + s`, where `s = +5` male, `−161` female, `−78` other (average of the two).
TDEE = round(BMR × PAL).

## 2. Targets by goal (FR-P5)

1. `target_kcal = round(TDEE × factor)`, then at least the floor (male 1500, female and other 1200).
2. `protein_g = min(g_per_kg × weight_kg, 0.35 × target_kcal / 4)`.
3. `fat_g = fat_share × target_kcal / 9`.
4. `carbs_g = (target_kcal − 4·protein_g − 9·fat_g) / 4`. With the 35 % protein cap and the fat shares below, carbs are never below 35 % of kcal, so no carb floor is needed.

| Goal | kcal factor | protein g/kg | fat share of kcal |
| --- | --- | --- | --- |
| weight_loss | 0.80 | 2.0 | 0.30 |
| muscle_gain | 1.10 | 1.8 | 0.25 |
| strength | 1.05 | 1.8 | 0.25 |
| maintenance | 1.00 | 1.6 | 0.30 |
| general_fitness | 1.00 | 1.6 | 0.30 |
| endurance | 1.05 | 1.4 | 0.20 |

Test vectors (inputs: sex, kg, cm, age, PAL, goal):

| Case | Result |
| --- | --- |
| male, 80, 180, 25, 1.55, muscle_gain | BMR 1805.0, TDEE 2798, target 3078 kcal, protein 144.0 g, fat 85.5 g, carbs 433.1 g |
| female, 60, 165, 30, 1.375, weight_loss | BMR 1320.3, TDEE 1815, target 1452 kcal, protein 120.0 g, fat 48.4 g, carbs 134.1 g |
| female, 55, 155, 60, 1.2, weight_loss (floor applies) | BMR 1057.8, TDEE 1269, target 1200 kcal (floor), protein 105.0 g, fat 40.0 g, carbs 105.0 g |
| male, 120, 185, 35, 1.375, weight_loss (protein cap applies) | BMR 2186.3, TDEE 3006, target 2405 kcal, protein 210.4 g (cap, not 240), fat 80.2 g, carbs 210.4 g |

`user_profile.tdee_kcal` is recomputed on every change of age, sex, weight, height or PAL.

## 3. Muscle groups and goal coverage (FR-P2)

Seed muscle groups (DB-03): chest, back, shoulders (upper); biceps, triceps (upper); quadriceps, hamstrings, glutes, calves (lower); core (core). Region decides the progression step.

Main muscle groups per goal:

| Goal | Main groups |
| --- | --- |
| muscle_gain | all ten |
| every other goal (strength, weight_loss, maintenance, general_fitness, endurance) | chest, back, shoulders, quadriceps, hamstrings, glutes, core |

## 4. Training plan generation (FR-P1, P2, P3, P7)

### 4.1 Inputs
`goal`, `training_days`, `experience_level`, `equipment` (the request may omit the last two and use the profile values) and the user's active injuries.

### 4.2 Eligible exercises
An exercise is eligible when all hold:
- `difficulty_level <= experience_level` (beginner < intermediate < advanced);
- `equipment <= user equipment` using the order none < home < gym (a gym user can do everything, a home user can do home and none, a "none" user only bodyweight);
- it is not excluded by injuries (4.3).

### 4.3 Injury rule
For every active injury of the user, an exercise is excluded when any of these holds:
1. it is listed in `injury_type_excluded_exercise` for the injury's type;
2. its main muscle group equals the injury's `affected_muscle_group_id`;
3. the severity is `moderate` or `severe` and the affected group is one of the exercise's secondary groups.

**FR-P2 versus injuries (decision, confirm at G0).** FR-P2 asks for at least one exercise per main group *and* no injury-excluded exercise. These conflict when an injury covers a whole group. Rule: a required group that has no eligible exercise only because of injuries is **skipped** (listed in `training_plan.skipped_muscle_group_ids` and in the response as `skipped_groups` with reason `injury`). Required groups = goal main groups minus skipped groups.

### 4.4 Insufficient exercises (FR-P3)
If a required group (not skipped) has no eligible exercise because of level or equipment, generation fails with HTTP 422, code `insufficient_exercises`, and no plan is stored. The error `details` list each empty group and the suggestions:
- `change_equipment`: the lowest higher equipment level at which every required group has at least one exercise (if any);
- `change_goal`: every goal whose required groups are all covered with the current settings.

### 4.5 Split by number of days

| Days | Sessions (name: groups) | Weekdays |
| --- | --- | --- |
| 1 | Full Body: all required groups | wed |
| 2 | Full Body A, Full Body B | mon, thu |
| 3 | Full Body A, B, C | mon, wed, fri |
| 4 | Upper A, Lower A, Upper B, Lower B | mon, tue, thu, fri |
| 5 | Upper, Lower, Push, Pull, Legs | mon, tue, thu, fri, sat |
| 6 | Push, Pull, Legs, Push, Pull, Legs | mon–sat |
| 7 | Push, Pull, Legs, Push, Pull, Legs, Full Body | mon–sun |

Groups per session type: Upper = chest, back, shoulders, biceps, triceps; Lower = quadriceps, hamstrings, glutes, calves, core; Push = chest, shoulders, triceps; Pull = back, biceps, core; Legs = quadriceps, hamstrings, glutes, calves, core; Full Body = all required groups. Only required groups are used. A group that appears in no session after filtering (for example `core` when Upper is the only type) is added to the session with the fewest groups.

### 4.6 Choosing exercises
- Sort the eligible exercises of a group by `is_compound DESC, difficulty_level DESC, id ASC`.
- Every session gets at least one exercise per group it contains.
- Target exercises per session: beginner 5, intermediate 6, advanced 7, but never fewer than the number of groups in the session. Extra slots go to second exercises, group priority: quadriceps, back, chest, hamstrings, glutes, shoulders, biceps, triceps, core, calves.
- When a group appears in several sessions, the k-th occurrence (k from 0) takes the exercises starting at index `(k × picks) mod n` of the sorted list, cyclically, so sessions vary.
- Sessions with more than 8 exercises use one set fewer per exercise (minimum 2).
- Exercises in a session are ordered: compound before isolation, then larger groups first.
- `planned_weight_kg` stays NULL (section 6 sets it after the first workout).

### 4.7 Sets, reps and rest
| Goal | Compound (sets × reps, rest s) | Isolation (sets × reps, rest s) |
| --- | --- | --- |
| strength | 5 × 5, 180 | 3 × 8, 90 |
| muscle_gain | 4 × 8, 120 | 3 × 12, 75 |
| weight_loss | 3 × 12, 60 | 3 × 15, 45 |
| maintenance | 3 × 10, 90 | 2 × 12, 60 |
| general_fitness | 3 × 10, 75 | 2 × 12, 60 |
| endurance | 3 × 15, 45 | 2 × 20, 30 |

Beginners get one set fewer (minimum 2). Estimated duration = round up to 5 min of `600 s + Σ sets × (45 s + rest)`.

### 4.8 Lifecycle (FR-P7)
Generation creates a `draft` plan (replacing any existing draft). `accept` sets `status = active`, sets start date (today or given) and end date, archives the previously active plan. Regenerate = generate again with changed inputs.

### 4.9 Swap and alternatives (FR-A1)
Alternatives for a session exercise: eligible exercises (4.2, 4.3) with the same main muscle group, excluding the current one and any already in that session. A swap keeps sets, reps, rest and weight, stores `original_exercise_id`. A swap to an ineligible or other-group exercise is rejected with `invalid_swap`.

## 5. Diet plan generation (FR-P6, P7)

### 5.1 Meal slots
| meals_per_day | Slots (type, share of daily kcal) |
| --- | --- |
| 3 | breakfast 0.30, lunch 0.40, dinner 0.30 |
| 4 | breakfast 0.25, lunch 0.35, dinner 0.30, snack 0.10 |
| 5 | breakfast 0.25, snack 0.10, lunch 0.30, dinner 0.25, snack 0.10 |

Macros per meal are the daily macros times the same share. The plan covers 7 days (`day_index` 1–7).

### 5.2 Eligible foods
`is_active`, meal type in `suitable_meal_types`, `diet_type` filter (vegetarian needs `is_vegetarian`, vegan needs `is_vegan`), none of the user's allergens (`user_allergen` ∩ `food_item_allergen`), not in `user_excluded_food`.

### 5.3 Meal composition
| Meal type | Roles (one item each) |
| --- | --- |
| breakfast | protein or dairy, carb, fruit, fat |
| lunch, dinner | protein, carb, vegetable, fat (a `dish` item may replace protein + carb) |
| snack | fruit or dairy, fat (optional) |

Selection for day `d` (1–7) and slot `i`: sort eligible items of the role by id and take index `(d − 1 + 2·i) mod n`; if that equals the item of the same slot the previous day and `n ≥ 2`, take the next one.

### 5.4 Scaling grams
Per meal solve a bounded least squares: variables are grams/100 of each chosen item, bounds `[min_portion_g, max_portion_g]`, minimise `Σ w_j · ((A x − t)_j / t_j)²` over kcal, protein, fat, carbs with weights 3, 2, 1, 1.5. Round to `portion_step_g`, clamp to the bounds. Reference: `scale_meal` (uses `scipy.optimize.lsq_linear`).

Worked example (lunch for the first target above, share 0.35): meal target 1077.3 kcal, 50.4 g protein, 29.9 g fat, 151.6 g carbs. Result: chicken breast 105 g, white rice 450 g (at its maximum), broccoli 250 g (at its maximum), olive oil 25 g, giving 1066.8 kcal, 50.7 g protein, 31.1 g fat, 144.0 g carbs (−1.0 %, +0.6 %, +4.0 %, −5.0 %).

### 5.5 Acceptance
Each day's totals must be within kcal ±5 %, protein ±10 %, fat ±15 %, carbs ±10 % of the daily targets. If a day misses, retry with the next item indices (up to 5 attempts); if it still misses, fail with 422 `insufficient_foods` and the roles that could not be satisfied.

**Amendment (task B-12, to be confirmed at review).** With the real food database (about 210 foods) the five attempts above almost never succeed: 1 708 of 1 728 tested combinations of profile, goal, diet type, meals per day and allergens failed. Causes: a `dish` item has fixed proportions, so a dish day (days 3 and 6 of the rotation in 5.3) rarely meets all four macros, and picking all meals of a day blindly by rotation rarely lands inside the tolerance. The search is therefore extended **after** the 5 attempts above, which stay unchanged (stage 1), so every plan stage 1 finds is the same as before:

Stage 2, at most `DIET_EXTRA_ATTEMPTS` attempts (constant in `app/domain/constants.py`, 12):
1. **No `dish` item.** The day uses the standard composition of 5.3 (allowed there: a `dish` item *may* replace protein + carb).
2. **Best of `DIET_MEAL_CANDIDATES` (8) rotation offsets per meal.** For every meal the 8 consecutive offsets of the rotation are scaled with 5.4 and the meal whose scaled totals are closest to its target (the objective of 5.4) is kept; the search over offsets stops early when a meal is within about 1 % on every macro (`GOOD_MEAL_ERROR`).
3. **Carry-over of errors.** A meal aims at its share of what is still missing from the day (daily target minus the totals of the earlier meals, spread over the remaining meals by their shares), not at its fixed share, so the rounding and portion-limit errors of earlier meals are made up by later ones.

The tolerances of this section are **not** relaxed. If a day still misses, the answer is 422 `insufficient_foods` as before. Measured on the seeded database (4 profiles x 6 goals x 3 meal counts): omnivore, vegetarian and vegan plans without allergies are always found (216 of 216); an omnivore is served for every single allergen tested (gluten, milk, eggs, nuts, soy); a vegan or vegetarian diet without gluten or soy fails only for the heaviest profile tested (120 kg, more than 200 g protein), and combinations that leave very few foods (four or eight allergens at once on a vegan or vegetarian diet) mostly fail. Typical time per plan 0.2 s, worst case about 2 s.

## 6. Adaptation and progression (FR-A2, A4, A5)

Runs when a workout is saved with a `training_session_id`. Implemented by `adapt` in the reference script. Changes are written to `session_exercise` (they apply the next time that session occurs) and recorded in `plan_adjustment`.

### 6.1 Signals
- **Reduce signal**: the workout's `overall_rpe >= 9` (applies to every logged exercise) **or** an exercise has a set with `completed = false` (applies to that exercise).
- **Reserve signal** ("set with reserve", **[confirm at G0]**): every planned set of the exercise was logged as completed with `reps >= planned_reps`, and the highest set RPE (or, when no set RPE is given, the overall RPE) is at most 7. If no RPE is available at all, there is no signal.
- No reduce and no reserve signal: **nothing changes** (FR-A4).

### 6.2 Reduction
Weighted exercise with a planned weight: `new = min(round_to_2.5(weight × 0.9), weight − 2.5)`. Bodyweight exercise or no planned weight: one set fewer (minimum 2). Reduction wins over progression.

### 6.3 Progression
Weighted: `new = (lowest completed set weight) + step`, step 2.5 kg for upper and core groups, 5 kg for lower. Bodyweight (`is_bodyweight`): planned reps + 1, capped at 20.

### 6.4 Baseline
For a weighted exercise with `planned_weight_kg` NULL, the first workout that logs completed sets sets `planned_weight_kg = round_to_2.5(highest logged weight × (0.9 if reduce signal else 1.0))` with reason `baseline`, and nothing else happens in that step.

### 6.5 Personal records
Only completed sets with weight > 0 and reps ≤ 12 count. `e1RM = weight` for 1 rep, otherwise `weight × (1 + reps/30)` (Epley). A new PR is a set whose e1RM exceeds the current record's e1RM; the old record gets `is_current = false`. Returned in the workout response as `new_personal_records`.

Test vectors for section 6 (planned 3 sets × 10 reps):

| Case | Result (reason, sets, reps, weight) |
| --- | --- |
| A: planned 60 kg, upper, all sets 10 reps, RPE 6 | progression, 3, 10, 62.5 |
| B: planned 100 kg, lower, all sets done, RPE 7 | progression, 3, 10, 105.0 |
| C: planned 60 kg, overall RPE 9 | reduce_high_rpe, 3, 10, 55.0 |
| D: planned 60 kg, one set not completed, overall RPE 8 | reduce_incomplete_set, 3, 10, 55.0 |
| E: RPE 8, all sets done | no change |
| F: all sets done, no RPE anywhere | no change |
| G: first log, weight unknown, sets at 40, 42.5, 42.5 kg | baseline, 3, 10, 42.5 |
| H: bodyweight, all done, RPE 6 | progression, 3, 11, – |
| I: bodyweight, RPE 9 | reduce_high_rpe, 2, 10, – |
| J: third set only 9 reps | no change |

e1RM vectors: 100 kg × 1 = 100; 100 kg × 5 = 116.67; 60 kg × 10 = 80.0.

## 7. Compliance (FR-R2)

- Workout compliance % = completed workouts in the period ÷ planned sessions in the period × 100, where planned = sessions per week of the active plan × number of plan weeks overlapping the period (counted in days/7).
- Diet compliance % = days in the period (from the plan start) whose logged calories are within ±10 % of the daily target ÷ days in the period × 100. Days without logs count as not compliant.

## 8. Analytics (FR-R1, R3, R5)

Periods: `week` = last 7 days including today, `month` = last 30 days, `3months` = last 90 days. Report types: `weekly` = ISO week Monday–Sunday, `monthly` = calendar month, `custom`.

Metrics: weight change = last minus first weigh-in in the period (null with fewer than 2); total workouts = non-deleted workout logs; average workouts per week = total ÷ (days/7); average calories = mean of daily calorie sums over days with at least one nutrition log; tonnage = Σ reps × weight over completed sets; strength in key exercises = for the three most-trained exercises in the period, e1RM of the first and the best set.

**Minimum data (FR-R5, decision, confirm at G0).** Reports and analytics are available once the user's history has at least 7 distinct calendar days with any record (workout, nutrition log or body metric). Before that the API returns `status: "insufficient_data"`. Inside a period without data, the metrics are null.

## 9. Goal prediction (FR-R4)

Reference: `predict_goal`. Uses the weigh-ins of the last 28 days, a least-squares line of weight over days.

| Situation | `status` |
| --- | --- |
| no target weight | `no_target` |
| fewer than 3 weigh-ins or span under 7 days | `insufficient_data` |
| fitted current weight within 0.5 kg of the target | `goal_reached` |
| absolute slope below 0.01 kg/day, or more than 730 days to go | `no_progress` |
| slope points away from the target | `moving_away` |
| otherwise | `ok` with `estimated_date` = last weigh-in + (target − fitted current) ÷ slope days |

`warnings` (irregular data, FR-R4): `low_fit` (R² < 0.5), `gaps` (a gap over 10 days between weigh-ins), `low_training_compliance` (workout compliance under 60 %). `irregular_data = warnings is not empty`. A date is still returned with warnings.

Vectors (today 2026-10-14, target 78 kg unless stated): weigh-ins losing 0.5 kg/week with 90 % compliance → `ok`, 2026-12-11, slope −0.49 kg/week, R² 1.0, no warnings; scattered weigh-ins with 50 % compliance → `ok`, 2027-02-21, slope −0.26, R² 0.18, warnings `low_fit`, `low_training_compliance`; gaining weight with target 75 → `moving_away`; two weigh-ins → `insufficient_data`.

## 10. Real-time meal suggestions (FR-N5)

`remaining = daily target − today's logged totals` (kcal and macros). If remaining kcal < 100, return no suggestions with the message `target_reached`. Otherwise:
1. Candidates: the not-yet-logged meals of today in the active diet plan, plus every eligible food (5.2, plus the user's diet type) at a scaled portion.
2. For a single food, grams = clamp(ideal_kcal ÷ kcal_per_g, min, max), rounded to the step, where `ideal_kcal = min(remaining_kcal, 0.35 × daily target)`.
3. Drop candidates whose kcal exceed `remaining_kcal × 1.05`.
4. Score = `Σ ((candidate_j − ideal_j) / ideal_j)²` over protein, fat and carbs, where ideal macros = remaining macros scaled to `ideal_kcal`. Lower is better.
5. Return the best 5 with grams, nutrition and allergy-free guarantee.

## 11. Meal photo recognition (FR-N1–N4)

- The AI service returns up to K = 3 `(label, confidence)` candidates (K configurable).
- Each label is mapped through `food_item.recognition_label`; no match gives `foodItemId: null` (the user must pick a food in the review step).
- Initial grams = `default_portion_g`; nutrition = per 100 g × grams ÷ 100.
- Candidates with confidence < 0.30 are flagged `low_confidence`.
- Each recognised item gets `allergy_warning = true` when its food shares an allergen with the user's allergens; this is shown before saving.
- `overallConfidence` = confidence of the top candidate.
- Confirm writes `recognition_ai`, `nutrition_log`, `nutrition_log_food_item` in one transaction and deletes the Mongo document. `was_edited = true` when any grams or item changed.

## 12. Weekly report (FR-R7)

A job runs every Monday at 07:00 in each user's `timezone` and generates the weekly report for the previous Monday–Sunday if the minimum-data rule (section 8) holds, then creates a `notification` of type `progress_update` with `data = {"report_id": …}` and sends a push. `UNIQUE (user_id, report_type, period_start, period_end)` makes a second run a no-op.
