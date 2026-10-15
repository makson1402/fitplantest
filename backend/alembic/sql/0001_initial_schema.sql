-- =====================================================================
-- FitPlan Pro: PostgreSQL schema (task D-01)
-- Authoritative reference for DB-01 (SQLAlchemy models + Alembic).
-- Replaces scheme_mysql.sql. Target: PostgreSQL 16.
--
-- Conventions (decision D8):
--   * snake_case, `users` (not the reserved word `user`)
--   * primary keys: GENERATED ALWAYS AS IDENTITY
--       integer  for dictionary / reference tables
--       bigint   for user-generated tables
--   * all timestamps are TIMESTAMPTZ (stored in UTC)
--   * every table owned by a user cascades on user delete (FR-U5)
--   * CHECK constraints enforce the ranges from docs/algorithms.md section 0
-- Requirement IDs in comments refer to docs/requirements.md.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Enumerations
-- ---------------------------------------------------------------------
CREATE TYPE sex_t              AS ENUM ('male', 'female', 'other');
CREATE TYPE goal_t             AS ENUM ('weight_loss', 'muscle_gain', 'strength', 'maintenance', 'general_fitness', 'endurance');
CREATE TYPE experience_level_t AS ENUM ('beginner', 'intermediate', 'advanced');
-- Declaration order matters: none < home < gym. An exercise is available to a
-- user when exercise.equipment <= user_profile.equipment (see algorithms.md 4.2).
CREATE TYPE equipment_t        AS ENUM ('none', 'home', 'gym');
CREATE TYPE severity_t         AS ENUM ('mild', 'moderate', 'severe');
CREATE TYPE meal_type_t        AS ENUM ('breakfast', 'lunch', 'dinner', 'snack');
CREATE TYPE weekday_t          AS ENUM ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun');
CREATE TYPE notification_type_t AS ENUM ('meal_reminder', 'training_reminder', 'progress_update', 'achievement', 'motivational');
CREATE TYPE report_type_t      AS ENUM ('weekly', 'monthly', 'custom');
CREATE TYPE oauth_provider_t   AS ENUM ('google', 'apple');
CREATE TYPE plan_status_t      AS ENUM ('draft', 'active', 'archived');
CREATE TYPE adjustment_reason_t AS ENUM ('baseline', 'reduce_high_rpe', 'reduce_incomplete_set', 'progression');
CREATE TYPE diet_type_t        AS ENUM ('omnivore', 'vegetarian', 'vegan');
CREATE TYPE food_role_t        AS ENUM ('protein', 'carb', 'fat', 'vegetable', 'fruit', 'dairy', 'dish', 'other');
CREATE TYPE body_region_t      AS ENUM ('upper', 'lower', 'core');

-- Server-side updated_at. Clients never set it (it is the sync cursor, see D-07).
CREATE FUNCTION set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END $$;

-- =====================================================================
-- 1. ACCOUNT AND AUTH (FR-U1..U5, FR-U8)
-- =====================================================================
CREATE TABLE users (
  id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email             text NOT NULL CHECK (email = lower(email) AND length(email) <= 254),
  -- NULL for accounts that only use Google/Apple sign-in
  password_hash     text,
  name              text,
  surname           text,
  -- IANA name, used for reminders, weekly report schedule and day boundaries
  timezone          text NOT NULL DEFAULT 'UTC',
  is_active         boolean NOT NULL DEFAULT true,
  email_verified_at timestamptz,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX users_email_key ON users (email);
CREATE TRIGGER users_set_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE oauth_identity (                               -- FR-U8
  id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id          bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider         oauth_provider_t NOT NULL,
  provider_subject text NOT NULL,                           -- the provider's stable user id ("sub")
  email            text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (provider, provider_subject)
);
CREATE INDEX oauth_identity_user_idx ON oauth_identity (user_id);

CREATE TABLE refresh_token (                                -- FR-U2, rotation with reuse detection
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id     bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  family_id   uuid NOT NULL,                                -- all tokens descending from one login
  token_hash  text NOT NULL UNIQUE,                         -- SHA-256 of the opaque token, never the token
  expires_at  timestamptz NOT NULL,
  revoked_at  timestamptz,
  device_label text,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX refresh_token_user_idx ON refresh_token (user_id);
CREATE INDEX refresh_token_family_idx ON refresh_token (family_id);

CREATE TABLE password_reset_token (                         -- FR-U3
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id     bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash  text NOT NULL UNIQUE,
  expires_at  timestamptz NOT NULL,
  used_at     timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX password_reset_token_user_idx ON password_reset_token (user_id);

-- =====================================================================
-- 2. REFERENCE DATA (filled by seeds DB-03..DB-05, read-only for the API)
-- =====================================================================
CREATE TABLE muscle_group (
  id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name        text NOT NULL UNIQUE,
  description text NOT NULL DEFAULT '',
  image_url   text,
  -- upper/lower decides the progression step (+2.5 kg vs +5 kg), algorithms.md 6.3
  body_region body_region_t NOT NULL
);

CREATE TABLE injury_type (
  id                    integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name                  text NOT NULL UNIQUE,
  description           text NOT NULL DEFAULT '',
  avg_healing_time_days integer NOT NULL DEFAULT 0 CHECK (avg_healing_time_days >= 0)
);

CREATE TABLE allergen (                                     -- FR-P6, FR-N3
  id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name        text NOT NULL UNIQUE,
  description text NOT NULL DEFAULT ''
);

CREATE TABLE food_category (
  id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name        text NOT NULL UNIQUE,
  description text NOT NULL DEFAULT ''
);

CREATE TABLE food_item (                                    -- FR-P8, FR-P6, FR-N2
  id                 integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name               text NOT NULL UNIQUE,
  calories_per_100g  numeric(6,2) NOT NULL CHECK (calories_per_100g BETWEEN 0 AND 900),
  protein_per_100g   numeric(5,2) NOT NULL CHECK (protein_per_100g BETWEEN 0 AND 100),
  fat_per_100g       numeric(5,2) NOT NULL CHECK (fat_per_100g BETWEEN 0 AND 100),
  carbs_per_100g     numeric(5,2) NOT NULL CHECK (carbs_per_100g BETWEEN 0 AND 100),
  CHECK (protein_per_100g + fat_per_100g + carbs_per_100g <= 100.5),
  -- role in a generated meal (algorithms.md 5.3); 'dish' = composite food, e.g. pizza
  role               food_role_t NOT NULL,
  suitable_meal_types meal_type_t[] NOT NULL DEFAULT '{breakfast,lunch,dinner,snack}',
  is_vegetarian      boolean NOT NULL DEFAULT false,
  is_vegan           boolean NOT NULL DEFAULT false,
  CHECK (NOT is_vegan OR is_vegetarian),
  -- portion bounds used when the diet generator scales grams
  default_portion_g  integer NOT NULL DEFAULT 100 CHECK (default_portion_g > 0),
  min_portion_g      integer NOT NULL DEFAULT 10   CHECK (min_portion_g > 0),
  max_portion_g      integer NOT NULL DEFAULT 400  CHECK (max_portion_g > 0),
  portion_step_g     integer NOT NULL DEFAULT 5    CHECK (portion_step_g > 0),
  CHECK (min_portion_g <= default_portion_g AND default_portion_g <= max_portion_g),
  -- AI model label (Food-101 class name) this item answers to; NULL when not recognisable
  recognition_label  text UNIQUE,
  is_active          boolean NOT NULL DEFAULT true
);

CREATE TABLE food_category_food_item (
  food_category_id integer NOT NULL REFERENCES food_category(id) ON DELETE CASCADE,
  food_item_id     integer NOT NULL REFERENCES food_item(id) ON DELETE CASCADE,
  PRIMARY KEY (food_item_id, food_category_id)
);
CREATE INDEX food_category_food_item_cat_idx ON food_category_food_item (food_category_id);

CREATE TABLE food_item_allergen (
  food_item_id integer NOT NULL REFERENCES food_item(id) ON DELETE CASCADE,
  allergen_id  integer NOT NULL REFERENCES allergen(id) ON DELETE CASCADE,
  PRIMARY KEY (food_item_id, allergen_id)
);
CREATE INDEX food_item_allergen_allergen_idx ON food_item_allergen (allergen_id);

CREATE TABLE exercise (                                     -- FR-P1, FR-P8
  id                   integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name                 text NOT NULL UNIQUE,
  main_muscle_group_id integer NOT NULL REFERENCES muscle_group(id),
  difficulty_level     experience_level_t NOT NULL,
  -- minimum environment needed: none = bodyweight, home = basic gear, gym = machines/barbells
  equipment            equipment_t NOT NULL,
  is_compound          boolean NOT NULL DEFAULT false,
  -- bodyweight exercises progress by reps, not kg (algorithms.md 6.3)
  is_bodyweight        boolean NOT NULL DEFAULT false,
  description          text NOT NULL,
  instruction          text NOT NULL                          -- FR-P8: text instruction
);
CREATE INDEX exercise_main_muscle_idx ON exercise (main_muscle_group_id);

CREATE TABLE exercise_secondary_muscle_group (
  exercise_id     integer NOT NULL REFERENCES exercise(id) ON DELETE CASCADE,
  muscle_group_id integer NOT NULL REFERENCES muscle_group(id),
  PRIMARY KEY (exercise_id, muscle_group_id)
);

-- Exercises that a given injury type explicitly rules out (in addition to the
-- muscle-group rule in algorithms.md 4.3). FR-P2.
CREATE TABLE injury_type_excluded_exercise (
  injury_type_id integer NOT NULL REFERENCES injury_type(id) ON DELETE CASCADE,
  exercise_id    integer NOT NULL REFERENCES exercise(id) ON DELETE CASCADE,
  PRIMARY KEY (injury_type_id, exercise_id)
);

-- =====================================================================
-- 3. USER PROFILE (FR-U6, FR-U7)
-- =====================================================================
CREATE TABLE user_profile (
  user_id            bigint PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  age                smallint NOT NULL CHECK (age BETWEEN 16 AND 100),
  sex                sex_t NOT NULL,
  weight_kg          numeric(5,2) NOT NULL CHECK (weight_kg BETWEEN 30 AND 300),
  height_cm          smallint NOT NULL CHECK (height_cm BETWEEN 120 AND 250),
  activity_level_pal numeric(3,2) NOT NULL CHECK (activity_level_pal BETWEEN 1.20 AND 2.40),
  goal               goal_t NOT NULL,
  target_weight_kg   numeric(5,2) CHECK (target_weight_kg BETWEEN 30 AND 300),   -- needed by FR-R4
  experience_level   experience_level_t NOT NULL,
  equipment          equipment_t NOT NULL,
  -- cache of the last computed TDEE; recomputed on every profile change
  tdee_kcal          integer CHECK (tdee_kcal > 0),
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER user_profile_set_updated_at BEFORE UPDATE ON user_profile FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE injury (
  id                       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id                  bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  injury_type_id           integer NOT NULL REFERENCES injury_type(id),
  affected_muscle_group_id integer NOT NULL REFERENCES muscle_group(id),
  severity                 severity_t NOT NULL,
  start_date               date NOT NULL,
  is_active                boolean NOT NULL DEFAULT true,
  notes                    text,
  created_at               timestamptz NOT NULL DEFAULT now(),
  updated_at               timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX injury_user_idx ON injury (user_id);
CREATE TRIGGER injury_set_updated_at BEFORE UPDATE ON injury FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE user_allergen (                                -- FR-P6, FR-N3
  user_id     bigint  NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  allergen_id integer NOT NULL REFERENCES allergen(id),
  PRIMARY KEY (user_id, allergen_id)
);

CREATE TABLE user_excluded_food (                           -- FR-P6 preferences
  user_id      bigint  NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  food_item_id integer NOT NULL REFERENCES food_item(id) ON DELETE CASCADE,
  PRIMARY KEY (user_id, food_item_id)
);

-- =====================================================================
-- 4. TRAINING (FR-P1..P3, FR-P7, FR-A1, FR-A2, FR-A4, FR-A5)
-- =====================================================================
CREATE TABLE training_plan (
  id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id           bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name              text NOT NULL,
  goal              goal_t NOT NULL,
  num_training_days smallint NOT NULL CHECK (num_training_days BETWEEN 1 AND 7),
  experience_level  experience_level_t NOT NULL,             -- snapshot at generation time
  equipment         equipment_t NOT NULL,                    -- snapshot at generation time
  status            plan_status_t NOT NULL DEFAULT 'draft',  -- draft until the user accepts (FR-P7)
  -- muscle groups left out because of active injuries, see algorithms.md 4.3
  skipped_muscle_group_ids integer[] NOT NULL DEFAULT '{}',
  generated_at      timestamptz NOT NULL DEFAULT now(),
  start_date        date,                                    -- set on accept
  end_date          date,                                    -- set on accept
  CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date)
);
CREATE INDEX training_plan_user_idx ON training_plan (user_id);
CREATE UNIQUE INDEX training_plan_one_active ON training_plan (user_id) WHERE status = 'active';
CREATE UNIQUE INDEX training_plan_one_draft  ON training_plan (user_id) WHERE status = 'draft';

CREATE TABLE training_session (                             -- one row = one weekly session of the plan
  id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  training_plan_id   bigint NOT NULL REFERENCES training_plan(id) ON DELETE CASCADE,
  session_order      smallint NOT NULL CHECK (session_order >= 1),
  name               text NOT NULL,                          -- e.g. "Upper A"
  weekday            weekday_t NOT NULL,                     -- FR-P9, user can change it
  estimated_duration_min smallint NOT NULL CHECK (estimated_duration_min > 0),
  UNIQUE (training_plan_id, session_order),
  UNIQUE (training_plan_id, weekday)
);

CREATE TABLE session_exercise (
  id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  training_session_id bigint NOT NULL REFERENCES training_session(id) ON DELETE CASCADE,
  exercise_id         integer NOT NULL REFERENCES exercise(id),
  original_exercise_id integer REFERENCES exercise(id),      -- set when swapped (FR-A1)
  position            smallint NOT NULL CHECK (position >= 1),
  planned_sets        smallint NOT NULL CHECK (planned_sets BETWEEN 1 AND 10),
  planned_reps        smallint NOT NULL CHECK (planned_reps BETWEEN 1 AND 50),
  -- NULL until the first logged workout (the plan does not know the user's strength)
  planned_weight_kg   numeric(6,2) CHECK (planned_weight_kg >= 0),
  rest_seconds        smallint NOT NULL CHECK (rest_seconds BETWEEN 0 AND 600),
  UNIQUE (training_session_id, position)
);
CREATE INDEX session_exercise_exercise_idx ON session_exercise (exercise_id);

-- Every automatic change of a session_exercise (FR-A4/A5) is explainable
CREATE TABLE plan_adjustment (
  id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  session_exercise_id bigint NOT NULL REFERENCES session_exercise(id) ON DELETE CASCADE,
  workout_log_id      bigint,                                -- FK added below (workout_log defined later)
  reason              adjustment_reason_t NOT NULL,
  old_sets            smallint, new_sets   smallint,
  old_reps            smallint, new_reps   smallint,
  old_weight_kg       numeric(6,2), new_weight_kg numeric(6,2),
  created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX plan_adjustment_se_idx ON plan_adjustment (session_exercise_id);

-- Offline-capable aggregate (D-07): last write wins on updated_at, deleted_at = tombstone
CREATE TABLE workout_log (                                  -- FR-A2
  id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id             bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  client_uuid         uuid NOT NULL DEFAULT gen_random_uuid(),
  training_session_id bigint REFERENCES training_session(id) ON DELETE SET NULL,
  performed_on        date NOT NULL,
  started_at          timestamptz,
  finished_at         timestamptz,
  overall_rpe         smallint CHECK (overall_rpe BETWEEN 1 AND 10),
  notes               text,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  deleted_at          timestamptz,
  UNIQUE (user_id, client_uuid)
);
CREATE INDEX workout_log_user_date_idx ON workout_log (user_id, performed_on DESC);
CREATE INDEX workout_log_user_updated_idx ON workout_log (user_id, updated_at);
CREATE TRIGGER workout_log_set_updated_at BEFORE INSERT OR UPDATE ON workout_log FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE plan_adjustment
  ADD CONSTRAINT plan_adjustment_workout_log_fk FOREIGN KEY (workout_log_id) REFERENCES workout_log(id) ON DELETE SET NULL;

CREATE TABLE workout_set_log (
  id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workout_log_id      bigint NOT NULL REFERENCES workout_log(id) ON DELETE CASCADE,
  exercise_id         integer NOT NULL REFERENCES exercise(id),
  session_exercise_id bigint REFERENCES session_exercise(id) ON DELETE SET NULL,
  set_number          smallint NOT NULL CHECK (set_number >= 1),
  reps                smallint NOT NULL CHECK (reps BETWEEN 0 AND 200),
  weight_kg           numeric(6,2) NOT NULL DEFAULT 0 CHECK (weight_kg >= 0),
  rpe                 smallint CHECK (rpe BETWEEN 1 AND 10),
  completed           boolean NOT NULL DEFAULT true,         -- false = "set could not be completed" (FR-A4)
  UNIQUE (workout_log_id, exercise_id, set_number)
);
CREATE INDEX workout_set_log_exercise_idx ON workout_set_log (exercise_id);

CREATE TABLE personal_record (                              -- FR-R1 (strength in key exercises)
  id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id           bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  exercise_id       integer NOT NULL REFERENCES exercise(id),
  max_weight_kg     numeric(6,2) NOT NULL CHECK (max_weight_kg >= 0),
  max_reps          smallint NOT NULL CHECK (max_reps >= 1),
  estimated_1rm_kg  numeric(6,2) NOT NULL CHECK (estimated_1rm_kg >= 0),   -- Epley, algorithms.md 6.5
  achieved_on       date NOT NULL,
  is_current        boolean NOT NULL DEFAULT true,
  source_set_id     bigint REFERENCES workout_set_log(id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX personal_record_one_current ON personal_record (user_id, exercise_id) WHERE is_current;

CREATE TABLE body_metrics (                                 -- FR-R1 (weight), offline-capable
  id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id          bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  client_uuid      uuid NOT NULL DEFAULT gen_random_uuid(),
  measured_on      date NOT NULL,
  weight_kg        numeric(5,2) NOT NULL CHECK (weight_kg BETWEEN 30 AND 300),
  chest_cm         numeric(5,2) CHECK (chest_cm > 0),
  waist_cm         numeric(5,2) CHECK (waist_cm > 0),
  thigh_cm         numeric(5,2) CHECK (thigh_cm > 0),
  bicep_cm         numeric(5,2) CHECK (bicep_cm > 0),
  hip_cm           numeric(5,2) CHECK (hip_cm > 0),
  calf_cm          numeric(5,2) CHECK (calf_cm > 0),
  body_fat_percent numeric(4,2) CHECK (body_fat_percent BETWEEN 2 AND 70),
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  deleted_at       timestamptz,
  UNIQUE (user_id, client_uuid)
);
-- one measurement per user per day (a second save the same day updates it)
CREATE UNIQUE INDEX body_metrics_user_day ON body_metrics (user_id, measured_on) WHERE deleted_at IS NULL;
CREATE INDEX body_metrics_user_updated_idx ON body_metrics (user_id, updated_at);
CREATE TRIGGER body_metrics_set_updated_at BEFORE INSERT OR UPDATE ON body_metrics FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =====================================================================
-- 5. DIET AND NUTRITION (FR-P4..P7, FR-A3, FR-N1..N5)
-- =====================================================================
CREATE TABLE diet_plan (
  id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id              bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name                 text NOT NULL,
  goal                 goal_t NOT NULL,
  diet_type            diet_type_t NOT NULL DEFAULT 'omnivore',
  meals_per_day        smallint NOT NULL CHECK (meals_per_day BETWEEN 3 AND 5),
  status               plan_status_t NOT NULL DEFAULT 'draft',
  daily_calorie_target integer NOT NULL CHECK (daily_calorie_target > 0),
  protein_target_g     numeric(6,2) NOT NULL CHECK (protein_target_g >= 0),
  fat_target_g         numeric(6,2) NOT NULL CHECK (fat_target_g >= 0),
  carbs_target_g       numeric(6,2) NOT NULL CHECK (carbs_target_g >= 0),
  dietary_restrictions text NOT NULL DEFAULT '',             -- free-text note shown to the user
  generated_at         timestamptz NOT NULL DEFAULT now(),
  start_date           date,
  end_date             date,
  CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date)
);
CREATE INDEX diet_plan_user_idx ON diet_plan (user_id);
CREATE UNIQUE INDEX diet_plan_one_active ON diet_plan (user_id) WHERE status = 'active';
CREATE UNIQUE INDEX diet_plan_one_draft  ON diet_plan (user_id) WHERE status = 'draft';

CREATE TABLE meal (                                         -- one planned meal of one day of the 7-day rotation
  id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  diet_plan_id     bigint NOT NULL REFERENCES diet_plan(id) ON DELETE CASCADE,
  day_index        smallint NOT NULL CHECK (day_index BETWEEN 1 AND 7),
  meal_type        meal_type_t NOT NULL,
  meal_order       smallint NOT NULL CHECK (meal_order >= 1),
  scheduled_time   time,                                     -- FR-P9
  planned_calories numeric(6,2) NOT NULL CHECK (planned_calories >= 0),
  planned_protein_g numeric(6,2) NOT NULL CHECK (planned_protein_g >= 0),
  planned_fat_g    numeric(6,2) NOT NULL CHECK (planned_fat_g >= 0),
  planned_carbs_g  numeric(6,2) NOT NULL CHECK (planned_carbs_g >= 0),
  UNIQUE (diet_plan_id, day_index, meal_order)
);

CREATE TABLE meal_food_item (
  meal_id      bigint  NOT NULL REFERENCES meal(id) ON DELETE CASCADE,
  food_item_id integer NOT NULL REFERENCES food_item(id),
  grams        numeric(6,1) NOT NULL CHECK (grams > 0),
  PRIMARY KEY (meal_id, food_item_id)
);

-- Confirmed result of a photo recognition (the unconfirmed one lives in MongoDB, D3)
CREATE TABLE recognition_ai (                               -- FR-N1..N4
  id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id          bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  image_url        text NOT NULL,
  model_name       text NOT NULL,
  model_version    text,
  uploaded_at      timestamptz NOT NULL,
  recognized_items jsonb NOT NULL,                           -- as returned by the model, before user edits
  estimated_calories integer NOT NULL CHECK (estimated_calories >= 0),
  estimated_protein_g numeric(6,2) NOT NULL,
  estimated_fat_g  numeric(6,2) NOT NULL,
  estimated_carbs_g numeric(6,2) NOT NULL,
  confidence_score numeric(3,2) NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
  was_edited       boolean NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX recognition_ai_user_idx ON recognition_ai (user_id);

CREATE TABLE nutrition_log (                                -- FR-A3, FR-R2, offline-capable
  id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id            bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  client_uuid        uuid NOT NULL DEFAULT gen_random_uuid(),
  log_date           date NOT NULL,
  meal_type          meal_type_t NOT NULL,
  meal_photo_url     text,
  actual_calories    numeric(6,2) NOT NULL CHECK (actual_calories >= 0),
  actual_protein_g   numeric(6,2) NOT NULL CHECK (actual_protein_g >= 0),
  actual_fat_g       numeric(6,2) NOT NULL CHECK (actual_fat_g >= 0),
  actual_carbs_g     numeric(6,2) NOT NULL CHECK (actual_carbs_g >= 0),
  hunger_level_before smallint CHECK (hunger_level_before BETWEEN 1 AND 10),
  hunger_level_after  smallint CHECK (hunger_level_after BETWEEN 1 AND 10),
  planned_meal_id    bigint REFERENCES meal(id) ON DELETE SET NULL,          -- eaten from the plan (FR-R2)
  recognition_id     bigint REFERENCES recognition_ai(id) ON DELETE SET NULL, -- NULL for manual logs
  logged_at          timestamptz NOT NULL DEFAULT now(),
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  deleted_at         timestamptz,
  UNIQUE (user_id, client_uuid)
);
CREATE INDEX nutrition_log_user_date_idx ON nutrition_log (user_id, log_date DESC);
CREATE INDEX nutrition_log_user_updated_idx ON nutrition_log (user_id, updated_at);
CREATE TRIGGER nutrition_log_set_updated_at BEFORE INSERT OR UPDATE ON nutrition_log FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE nutrition_log_food_item (
  nutrition_log_id bigint  NOT NULL REFERENCES nutrition_log(id) ON DELETE CASCADE,
  food_item_id     integer NOT NULL REFERENCES food_item(id),
  grams            numeric(6,1) NOT NULL CHECK (grams > 0),
  calories         numeric(6,2) NOT NULL CHECK (calories >= 0),
  protein_g        numeric(6,2) NOT NULL CHECK (protein_g >= 0),
  fat_g            numeric(6,2) NOT NULL CHECK (fat_g >= 0),
  carbs_g          numeric(6,2) NOT NULL CHECK (carbs_g >= 0),
  PRIMARY KEY (nutrition_log_id, food_item_id)
);

-- =====================================================================
-- 6. REPORTS (FR-R1..R7)
-- =====================================================================
CREATE TABLE progress_report (
  id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id               bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  report_type           report_type_t NOT NULL,
  period_start          date NOT NULL,
  period_end            date NOT NULL,
  weight_difference_kg  numeric(5,2),
  training_volume_kg    numeric(10,2) NOT NULL DEFAULT 0,    -- tonnage
  training_sessions_completed smallint NOT NULL DEFAULT 0,
  training_sessions_planned   smallint NOT NULL DEFAULT 0,
  workout_compliance_pct numeric(5,2),                       -- FR-R2
  diet_compliance_pct    numeric(5,2),                       -- FR-R2
  avg_daily_calories    integer,
  estimated_goal_completion_date date,                       -- NULL = no prediction (FR-R4/R5)
  irregular_data        boolean NOT NULL DEFAULT false,      -- FR-R4 warning
  is_auto               boolean NOT NULL DEFAULT false,      -- FR-R7
  details               jsonb NOT NULL DEFAULT '{}',         -- chart series and key lifts for display/export
  generated_at          timestamptz NOT NULL DEFAULT now(),
  CHECK (period_end >= period_start),
  -- makes the weekly job idempotent (B-26)
  UNIQUE (user_id, report_type, period_start, period_end)
);

-- =====================================================================
-- 7. REMINDERS AND NOTIFICATIONS (FR-P9, FR-R7)
-- =====================================================================
CREATE TABLE reminder (                                     -- recurring local reminder, scheduled on the device
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id     bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  type        notification_type_t NOT NULL CHECK (type IN ('meal_reminder', 'training_reminder')),
  meal_type   meal_type_t,
  weekdays    weekday_t[] NOT NULL CHECK (cardinality(weekdays) BETWEEN 1 AND 7),
  time_of_day time NOT NULL,
  message     text,
  is_enabled  boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  CHECK ((type = 'meal_reminder') = (meal_type IS NOT NULL))
);
CREATE INDEX reminder_user_idx ON reminder (user_id);
CREATE TRIGGER reminder_set_updated_at BEFORE UPDATE ON reminder FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE notification (                                 -- server-sent push + in-app inbox
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id    bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  type       notification_type_t NOT NULL,
  title      text NOT NULL,
  message    text NOT NULL,
  data       jsonb NOT NULL DEFAULT '{}',                    -- deep link, e.g. {"report_id": 12}
  created_at timestamptz NOT NULL DEFAULT now(),
  sent_at    timestamptz,
  read_at    timestamptz
);
CREATE INDEX notification_user_created_idx ON notification (user_id, created_at DESC);

CREATE TABLE device_push_token (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id      bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token        text NOT NULL UNIQUE,                         -- Expo push token
  platform     text NOT NULL CHECK (platform IN ('android', 'ios')),
  created_at   timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX device_push_token_user_idx ON device_push_token (user_id);
