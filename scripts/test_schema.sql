-- Behavioural tests for schema_postgres.sql. Run against a database that already has the schema:
--   psql -v ON_ERROR_STOP=1 -d <db> -f scripts/test_schema.sql
-- Every check raises an exception on failure; the script ends with "ALL SCHEMA CHECKS PASSED".
-- Data is committed on purpose (no wrapping transaction): the user-delete check must see rows from
-- earlier transactions, exactly as in production. The script truncates its own data at the end.

CREATE FUNCTION pg_temp.expect_fail(sql text, what text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  BEGIN
    EXECUTE sql;
  EXCEPTION WHEN check_violation OR unique_violation OR not_null_violation OR foreign_key_violation THEN
    RETURN;
  END;
  RAISE EXCEPTION 'expected failure did not happen: %', what;
END $$;

-- reference data
INSERT INTO muscle_group (name, body_region) VALUES ('chest', 'upper'), ('quadriceps', 'lower');
INSERT INTO injury_type (name) VALUES ('sprain');
INSERT INTO allergen (name) VALUES ('gluten');
INSERT INTO exercise (name, main_muscle_group_id, difficulty_level, equipment, description, instruction)
  VALUES ('Push-up', 1, 'beginner', 'none', 'd', 'i'), ('Barbell squat', 2, 'intermediate', 'gym', 'd', 'i');
INSERT INTO food_item (name, calories_per_100g, protein_per_100g, fat_per_100g, carbs_per_100g, role)
  VALUES ('Chicken breast', 165, 31, 3.6, 0, 'protein');

-- equipment ordering rule: none < home < gym
DO $$ BEGIN
  IF NOT ('none'::equipment_t <= 'home'::equipment_t AND 'home'::equipment_t <= 'gym'::equipment_t) THEN
    RAISE EXCEPTION 'equipment_t order broken';
  END IF;
  IF 'gym'::equipment_t <= 'home'::equipment_t THEN RAISE EXCEPTION 'equipment_t order broken (2)'; END IF;
END $$;

-- users and profile ranges (FR-U7)
INSERT INTO users (email, password_hash) VALUES ('a@example.com', 'x') RETURNING id \gset u_
SELECT pg_temp.expect_fail($$INSERT INTO users (email) VALUES ('A@Example.com')$$, 'uppercase email');
SELECT pg_temp.expect_fail($$INSERT INTO users (email) VALUES ('a@example.com')$$, 'duplicate email');

INSERT INTO user_profile (user_id, age, sex, weight_kg, height_cm, activity_level_pal, goal, experience_level, equipment)
  VALUES (:u_id, 25, 'male', 30, 180, 1.55, 'muscle_gain', 'beginner', 'home');
UPDATE user_profile SET weight_kg = 300 WHERE user_id = :u_id;
SELECT pg_temp.expect_fail(format('UPDATE user_profile SET weight_kg = 29.99 WHERE user_id = %s', :u_id), 'weight 29.99');
SELECT pg_temp.expect_fail(format('UPDATE user_profile SET weight_kg = 300.01 WHERE user_id = %s', :u_id), 'weight 300.01');
SELECT pg_temp.expect_fail(format('UPDATE user_profile SET age = 15 WHERE user_id = %s', :u_id), 'age 15');
SELECT pg_temp.expect_fail(format('UPDATE user_profile SET height_cm = 119 WHERE user_id = %s', :u_id), 'height 119');

-- one active / one draft training plan per user (FR-P7)
INSERT INTO training_plan (user_id, name, goal, num_training_days, experience_level, equipment, status)
  VALUES (:u_id, 'p1', 'muscle_gain', 3, 'beginner', 'home', 'active');
SELECT pg_temp.expect_fail(format($f$INSERT INTO training_plan (user_id, name, goal, num_training_days, experience_level, equipment, status)
  VALUES (%s, 'p2', 'muscle_gain', 3, 'beginner', 'home', 'active')$f$, :u_id), 'two active plans');
INSERT INTO training_plan (user_id, name, goal, num_training_days, experience_level, equipment, status)
  VALUES (:u_id, 'p3', 'muscle_gain', 3, 'beginner', 'home', 'draft') RETURNING id \gset p_
SELECT pg_temp.expect_fail(format($f$INSERT INTO training_plan (user_id, name, goal, num_training_days, experience_level, equipment, status)
  VALUES (%s, 'p4', 'muscle_gain', 3, 'beginner', 'home', 'draft')$f$, :u_id), 'two draft plans');
INSERT INTO training_session (training_plan_id, session_order, name, weekday, estimated_duration_min)
  VALUES (:p_id, 1, 'A', 'mon', 45) RETURNING id \gset s_
INSERT INTO session_exercise (training_session_id, exercise_id, position, planned_sets, planned_reps, rest_seconds)
  VALUES (:s_id, 1, 1, 3, 10, 90) RETURNING id \gset se_

-- workout log aggregate, RPE range, sync behaviour (FR-A2, D-07)
INSERT INTO workout_log (user_id, training_session_id, performed_on, overall_rpe) VALUES (:u_id, :s_id, current_date, 9) RETURNING id, updated_at \gset w_
SELECT pg_temp.expect_fail(format('INSERT INTO workout_log (user_id, performed_on, overall_rpe) VALUES (%s, current_date, 11)', :u_id), 'rpe 11');
SELECT pg_temp.expect_fail(format('INSERT INTO workout_log (user_id, performed_on, overall_rpe) VALUES (%s, current_date, 0)', :u_id), 'rpe 0');
INSERT INTO workout_set_log (workout_log_id, exercise_id, session_exercise_id, set_number, reps, weight_kg, completed)
  VALUES (:w_id, 1, :se_id, 1, 10, 0, true), (:w_id, 1, :se_id, 2, 8, 0, false);
SELECT pg_temp.expect_fail(format('INSERT INTO workout_set_log (workout_log_id, exercise_id, set_number, reps) VALUES (%s, 1, 2, 5)', :w_id), 'duplicate set number');
INSERT INTO plan_adjustment (session_exercise_id, workout_log_id, reason, old_sets, new_sets) VALUES (:se_id, :w_id, 'reduce_high_rpe', 3, 2);
INSERT INTO personal_record (user_id, exercise_id, max_weight_kg, max_reps, estimated_1rm_kg, achieved_on) VALUES (:u_id, 1, 0, 10, 0, current_date);
SELECT pg_temp.expect_fail(format('INSERT INTO personal_record (user_id, exercise_id, max_weight_kg, max_reps, estimated_1rm_kg, achieved_on) VALUES (%s, 1, 0, 12, 0, current_date)', :u_id), 'two current PRs');

-- server-assigned updated_at moves forward on update (clients cannot fake the sync cursor)
SELECT pg_sleep(0.01);
UPDATE workout_log SET notes = 'x', updated_at = '2000-01-01' WHERE id = :w_id;
DO $$ BEGIN
  IF (SELECT updated_at FROM workout_log LIMIT 1) < now() - interval '1 minute' THEN
    RAISE EXCEPTION 'updated_at trigger did not override the client value';
  END IF;
END $$;

-- body metrics: one per day, tombstone frees the day (FR-R1, D-07)
INSERT INTO body_metrics (user_id, measured_on, weight_kg) VALUES (:u_id, '2026-10-01', 80);
SELECT pg_temp.expect_fail(format($f$INSERT INTO body_metrics (user_id, measured_on, weight_kg) VALUES (%s, '2026-10-01', 81)$f$, :u_id), 'two measurements same day');
UPDATE body_metrics SET deleted_at = now() WHERE user_id = :u_id;
INSERT INTO body_metrics (user_id, measured_on, weight_kg) VALUES (:u_id, '2026-10-01', 81);
SELECT pg_temp.expect_fail(format($f$INSERT INTO body_metrics (user_id, measured_on, weight_kg) VALUES (%s, '2026-10-02', 301)$f$, :u_id), 'weight 301');

-- diet plan, meals, nutrition logs, manual log without recognition (FR-A3, FR-R2)
INSERT INTO diet_plan (user_id, name, goal, meals_per_day, status, daily_calorie_target, protein_target_g, fat_target_g, carbs_target_g)
  VALUES (:u_id, 'd1', 'muscle_gain', 4, 'active', 3078, 144, 85, 380) RETURNING id \gset d_
INSERT INTO meal (diet_plan_id, day_index, meal_type, meal_order, planned_calories, planned_protein_g, planned_fat_g, planned_carbs_g)
  VALUES (:d_id, 1, 'breakfast', 1, 770, 36, 21, 95) RETURNING id \gset m_
INSERT INTO meal_food_item (meal_id, food_item_id, grams) VALUES (:m_id, 1, 150);
INSERT INTO nutrition_log (user_id, log_date, meal_type, actual_calories, actual_protein_g, actual_fat_g, actual_carbs_g, planned_meal_id, hunger_level_before)
  VALUES (:u_id, current_date, 'breakfast', 700, 30, 20, 90, :m_id, 7) RETURNING id \gset n_
SELECT pg_temp.expect_fail(format($f$INSERT INTO nutrition_log (user_id, log_date, meal_type, actual_calories, actual_protein_g, actual_fat_g, actual_carbs_g, hunger_level_after)
  VALUES (%s, current_date, 'lunch', 1, 1, 1, 1, 11)$f$, :u_id), 'hunger 11');
INSERT INTO nutrition_log_food_item VALUES (:n_id, 1, 150, 247.5, 46.5, 5.4, 0);

-- food item sanity (FR-P8)
SELECT pg_temp.expect_fail($$INSERT INTO food_item (name, calories_per_100g, protein_per_100g, fat_per_100g, carbs_per_100g, role) VALUES ('bad', 100, 60, 60, 0, 'other')$$, 'macros above 100 g');
SELECT pg_temp.expect_fail($$INSERT INTO food_item (name, calories_per_100g, protein_per_100g, fat_per_100g, carbs_per_100g, role, is_vegan, is_vegetarian) VALUES ('bad2', 100, 1, 1, 1, 'other', true, false)$$, 'vegan but not vegetarian');

-- reminders: meal reminder needs a meal_type, training reminder must not have one
INSERT INTO reminder (user_id, type, meal_type, weekdays, time_of_day) VALUES (:u_id, 'meal_reminder', 'lunch', '{mon,tue}', '12:30');
SELECT pg_temp.expect_fail(format($f$INSERT INTO reminder (user_id, type, weekdays, time_of_day) VALUES (%s, 'meal_reminder', '{mon}', '12:00')$f$, :u_id), 'meal reminder without meal type');
SELECT pg_temp.expect_fail(format($f$INSERT INTO reminder (user_id, type, weekdays, time_of_day) VALUES (%s, 'achievement', '{mon}', '12:00')$f$, :u_id), 'non-reminder type');

-- reports: weekly job idempotency (B-26)
INSERT INTO progress_report (user_id, report_type, period_start, period_end) VALUES (:u_id, 'weekly', '2026-10-05', '2026-10-11');
SELECT pg_temp.expect_fail(format($f$INSERT INTO progress_report (user_id, report_type, period_start, period_end) VALUES (%s, 'weekly', '2026-10-05', '2026-10-11')$f$, :u_id), 'duplicate weekly report');

-- auth tables
INSERT INTO refresh_token (user_id, family_id, token_hash, expires_at) VALUES (:u_id, gen_random_uuid(), 'h1', now() + interval '30 days');
INSERT INTO password_reset_token (user_id, token_hash, expires_at) VALUES (:u_id, 'h2', now() + interval '1 hour');
INSERT INTO oauth_identity (user_id, provider, provider_subject) VALUES (:u_id, 'google', 'sub-1');
INSERT INTO user_allergen VALUES (:u_id, 1);
INSERT INTO user_excluded_food VALUES (:u_id, 1);
INSERT INTO injury (user_id, injury_type_id, affected_muscle_group_id, severity, start_date) VALUES (:u_id, 1, 1, 'mild', current_date);
INSERT INTO notification (user_id, type, title, message) VALUES (:u_id, 'progress_update', 't', 'm');
INSERT INTO device_push_token (user_id, token, platform) VALUES (:u_id, 'ExponentPushToken[x]', 'android');
INSERT INTO recognition_ai (user_id, image_url, model_name, uploaded_at, recognized_items, estimated_calories, estimated_protein_g, estimated_fat_g, estimated_carbs_g, confidence_score, was_edited)
  VALUES (:u_id, 'meals/a.jpg', 'm', now(), '[]', 100, 1, 1, 1, 0.87, false);

-- FR-U5: deleting the user must remove every row that belongs to them, in every table
DO $$
DECLARE r record; n bigint; uid bigint;
BEGIN
  SELECT id INTO uid FROM users LIMIT 1;
  DELETE FROM users WHERE id = uid;
  FOR r IN SELECT table_name FROM information_schema.columns
           WHERE table_schema = 'public' AND column_name = 'user_id' LOOP
    EXECUTE format('SELECT count(*) FROM %I WHERE user_id = $1', r.table_name) INTO n USING uid;
    IF n <> 0 THEN RAISE EXCEPTION 'table % still has % rows after user delete', r.table_name, n; END IF;
  END LOOP;
  -- tables that hang off user-owned rows must be empty as well
  FOR r IN SELECT unnest(ARRAY['training_session','session_exercise','plan_adjustment','workout_set_log','meal','meal_food_item','nutrition_log_food_item']) AS t LOOP
    EXECUTE format('SELECT count(*) FROM %I', r.t) INTO n;
    IF n <> 0 THEN RAISE EXCEPTION 'child table % still has % rows after user delete', r.t, n; END IF;
  END LOOP;
END $$;

TRUNCATE users, muscle_group, injury_type, allergen, exercise, food_item RESTART IDENTITY CASCADE;
DO $$ BEGIN RAISE NOTICE 'ALL SCHEMA CHECKS PASSED'; END $$;
