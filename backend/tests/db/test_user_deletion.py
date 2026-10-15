"""FR-U5: deleting a user removes every row they own (DB-01 'done when')."""
from __future__ import annotations

from sqlalchemy import text

# Every table with a direct user_id column; all must cascade.
OWNED = [
    "oauth_identity", "refresh_token", "password_reset_token", "user_profile", "injury", "user_allergen",
    "user_excluded_food", "training_plan", "workout_log", "personal_record", "body_metrics", "diet_plan",
    "recognition_ai", "nutrition_log", "progress_report", "reminder", "notification", "device_push_token",
]
INDIRECT = [
    "training_session", "session_exercise", "workout_set_log", "plan_adjustment", "meal", "meal_food_item",
    "nutrition_log_food_item",
]


def _one(c, sql: str, **params):
    return c.execute(text(sql), params).scalar_one()


def test_delete_user_cascades_everywhere(pg_engine):
    with pg_engine.begin() as c:
        uid = _one(c, "insert into users (email) values ('del@example.com') returning id")
        mg = _one(c, "insert into muscle_group (name, body_region) values ('chest-t', 'upper') returning id")
        ex = _one(c, "insert into exercise (name, main_muscle_group_id, difficulty_level, equipment, description,"
                     " instruction) values ('bench-t', :mg, 'beginner', 'gym', 'd', 'i') returning id", mg=mg)
        al = _one(c, "insert into allergen (name) values ('nuts-t') returning id")
        it = _one(c, "insert into injury_type (name) values ('strain-t') returning id")
        fi = _one(c, "insert into food_item (name, calories_per_100g, protein_per_100g, fat_per_100g,"
                     " carbs_per_100g, role) values ('rice-t', 130, 2.7, 0.3, 28, 'carb') returning id")

        c.execute(text("insert into oauth_identity (user_id, provider, provider_subject) values (:u, 'google', 's1')"), {"u": uid})
        c.execute(text("insert into refresh_token (user_id, family_id, token_hash, expires_at)"
                       " values (:u, gen_random_uuid(), 'h1', now())"), {"u": uid})
        c.execute(text("insert into password_reset_token (user_id, token_hash, expires_at) values (:u, 'h2', now())"), {"u": uid})
        c.execute(text("insert into user_profile (user_id, age, sex, weight_kg, height_cm, activity_level_pal, goal,"
                       " experience_level, equipment) values (:u, 30, 'male', 80, 180, 1.55, 'muscle_gain',"
                       " 'beginner', 'gym')"), {"u": uid})
        c.execute(text("insert into injury (user_id, injury_type_id, affected_muscle_group_id, severity, start_date)"
                       " values (:u, :it, :mg, 'mild', current_date)"), {"u": uid, "it": it, "mg": mg})
        c.execute(text("insert into user_allergen values (:u, :a)"), {"u": uid, "a": al})
        c.execute(text("insert into user_excluded_food values (:u, :f)"), {"u": uid, "f": fi})

        plan = _one(c, "insert into training_plan (user_id, name, goal, num_training_days, experience_level, equipment)"
                       " values (:u, 'p', 'muscle_gain', 3, 'beginner', 'gym') returning id", u=uid)
        sess = _one(c, "insert into training_session (training_plan_id, session_order, name, weekday,"
                       " estimated_duration_min) values (:p, 1, 'A', 'mon', 45) returning id", p=plan)
        se = _one(c, "insert into session_exercise (training_session_id, exercise_id, position, planned_sets,"
                     " planned_reps, rest_seconds) values (:s, :e, 1, 3, 10, 90) returning id", s=sess, e=ex)
        wl = _one(c, "insert into workout_log (user_id, training_session_id, performed_on)"
                     " values (:u, :s, current_date) returning id", u=uid, s=sess)
        st = _one(c, "insert into workout_set_log (workout_log_id, exercise_id, session_exercise_id, set_number,"
                     " reps, weight_kg) values (:w, :e, :se, 1, 10, 50) returning id", w=wl, e=ex, se=se)
        c.execute(text("insert into plan_adjustment (session_exercise_id, workout_log_id, reason)"
                       " values (:se, :w, 'baseline')"), {"se": se, "w": wl})
        c.execute(text("insert into personal_record (user_id, exercise_id, max_weight_kg, max_reps, estimated_1rm_kg,"
                       " achieved_on, source_set_id) values (:u, :e, 50, 10, 66, current_date, :st)"),
                  {"u": uid, "e": ex, "st": st})
        c.execute(text("insert into body_metrics (user_id, measured_on, weight_kg) values (:u, current_date, 80)"), {"u": uid})

        dp = _one(c, "insert into diet_plan (user_id, name, goal, meals_per_day, daily_calorie_target, protein_target_g,"
                     " fat_target_g, carbs_target_g) values (:u, 'd', 'muscle_gain', 3, 2500, 150, 70, 300)"
                     " returning id", u=uid)
        meal = _one(c, "insert into meal (diet_plan_id, day_index, meal_type, meal_order, planned_calories,"
                       " planned_protein_g, planned_fat_g, planned_carbs_g)"
                       " values (:d, 1, 'lunch', 1, 800, 40, 20, 100) returning id", d=dp)
        c.execute(text("insert into meal_food_item values (:m, :f, 150)"), {"m": meal, "f": fi})
        rec = _one(c, "insert into recognition_ai (user_id, image_url, model_name, uploaded_at, recognized_items,"
                      " estimated_calories, estimated_protein_g, estimated_fat_g, estimated_carbs_g,"
                      " confidence_score, was_edited) values (:u, 'x', 'm', now(), '[]', 100, 1, 1, 1, 0.9, false)"
                      " returning id", u=uid)
        nl = _one(c, "insert into nutrition_log (user_id, log_date, meal_type, actual_calories, actual_protein_g,"
                     " actual_fat_g, actual_carbs_g, planned_meal_id, recognition_id)"
                     " values (:u, current_date, 'lunch', 500, 30, 10, 60, :m, :r) returning id",
                  u=uid, m=meal, r=rec)
        c.execute(text("insert into nutrition_log_food_item values (:n, :f, 100, 130, 2.7, 0.3, 28)"), {"n": nl, "f": fi})
        c.execute(text("insert into progress_report (user_id, report_type, period_start, period_end)"
                       " values (:u, 'weekly', current_date - 7, current_date)"), {"u": uid})
        c.execute(text("insert into reminder (user_id, type, weekdays, time_of_day)"
                       " values (:u, 'training_reminder', '{mon}', '07:00')"), {"u": uid})
        c.execute(text("insert into notification (user_id, type, title, message) values (:u, 'achievement', 't', 'm')"), {"u": uid})
        c.execute(text("insert into device_push_token (user_id, token, platform) values (:u, 'tok', 'android')"), {"u": uid})

        for table in OWNED:  # the fixture really populated every owned table
            assert _one(c, f"select count(*) from {table} where user_id = :u", u=uid) == 1, table

    with pg_engine.begin() as c:
        c.execute(text("delete from users where id = :u"), {"u": uid})
        for table in OWNED:
            assert _one(c, f"select count(*) from {table} where user_id = :u", u=uid) == 0, table
        for table in INDIRECT:
            assert _one(c, f"select count(*) from {table}") == 0, table
