# FitPlan Pro — Task Backlog (Waterfall)

Sources: `docs/requirments.md`, `docs/decisions.md`, `docs/database/*`, `docs/Project_documentation.docx`.
Method: Waterfall, no estimates. Tasks are ordered by dependency only. Scope: everything in the requirements, including the items previously marked "out of scope / future work / open question".

## 1. How to use this file

**Roles** (from `CLAUDE.md` ownership; proposed, change freely):

| Tag  | Person                | Area                                                    |
| ---- | --------------------- | ------------------------------------------------------- |
| DATA | Kyryl                 | `database/`, `backend/app/db/`, `backend/alembic/`      |
| API  | Maksym                | `backend/app/api/`, business logic, AI service          |
| APP  | Oleksandr             | `mobile/`                                               |
| ALL  | whole team            | design reviews, gates, cross-cutting tasks              |

**Waterfall rules**
- Phases run in order: 0 Requirements → 1 Design → 2 Implementation → 3 Integration & testing → 4 Deployment → 5 Documentation. Phase N+1 starts only when the Gate N checklist is signed off by all three members.
- After a gate, a change goes through a change request: update `docs/requirments.md` and `docs/decisions.md` first, then the affected tasks.
- API and APP work in parallel inside Phase 2 because the API contract is frozen at Gate 1. APP develops against a mock server until the real endpoints land.
- Every implementation task includes its own unit/integration tests. "Done when" always implies: tests green in CI, PR reviewed (one approval), PR description cites the requirement IDs.
- Branch prefixes: `db/`, `api/`, `app/`, `docs/`. Never commit `.env`.
- Code and identifiers in English, thesis documentation in Polish.

**Task format**: `ID · title`, then Owner, Reqs, Depends on, Do, Done when.

**New requirement IDs** introduced by R-01 for items that had no ID: `FR-U8` social sign-in, `FR-N5` real-time meal suggestions, `FR-R6` report export, `FR-R7` automatic weekly report with push, `NFR-OFF` offline mode with sync. `FR-P9` is extended to server push in addition to local reminders.

## 2. Phase overview

| Phase | Gate | Tasks |
| ----- | ---- | ----- |
| 0 Requirements | G0 | R-01, R-02 |
| 1 Design | G1 | D-01 … D-11 |
| 2 Implementation: foundation & data | G2 | B-01, DB-01 … DB-06 |
| 2 Implementation: backend core | G2 | B-02 … B-17 |
| 2 Implementation: nutrition AI | G2 | B-18 … B-22 |
| 2 Implementation: analytics | G2 | B-23 … B-26 |
| 2 Implementation: extended scope | G2 | B-07, B-27, M-12 (push), M-16, M-19, M-20 (cut line, see 6) |
| 2 Implementation: mobile | G2 | M-01 … M-22 |
| 3 Integration & testing | G3 | T-01 … T-09 |
| 4 Deployment | G4 | Z-01 … Z-04 |
| 5 Documentation | G5 | W-01, W-02 |

---

# Phase 0 — Requirements baseline

### R-01 · Freeze requirements and close open questions
- **Status:** drafted (`docs/requirements.md`, `docs/decisions.md`); awaiting sign-off at G0.
- **Owner:** ALL · **Branch:** `docs/`
- **Do:** Rename `docs/requirments.md` to `requirements.md` (`CLAUDE.md` already uses the correct name). Remove the "Out of scope" section. Add FR-U8, FR-N5, FR-R6, FR-R7, NFR-OFF and extend FR-P9 (see section 1). Record the defaults below in the "Open questions" section as decided.
- **Done when:** the file has no open questions left; Gate G0 signed.

| Open question | Default decision (change at G0 only) |
| --- | --- |
| Age and height ranges | age 16–100 (Polish digital-consent age is 16, confirm), height 120–250 cm; weight 30–300 kg as specified |
| "Set with reserve" for progression | all planned reps completed on every set with RPE ≤ 7 |
| Progression / reduction step | +2.5 kg upper body, +5 kg lower body; reduction −10 % load rounded to 2.5 kg or −1 set; kept as configurable constants (D-04) |
| Real-time meal suggestions | in scope, FR-N5 |
| Report export | PDF and CSV, FR-R6 |
| Google / Apple sign-in | both, FR-U8 (Apple needs an Apple Developer account; if unavailable the task is marked blocked) |
| Automatic weekly report | weekly job, report plus push notification, FR-R7 |
| Mongo `failed` status | not stored; Vision/AI errors are returned directly |
| Photo storage | local Docker volume; unconfirmed photos deleted by a cleanup job after `expiresAt`; confirmed photos kept until account deletion |
| Mongo expiry | 6 h, as in `mongo_buffer.md` |
| Offline scope | plans, workout logs, nutrition logs, body metrics usable offline (D-07) |

### R-02 · Record decisions in `docs/decisions.md`
- **Status:** drafted (`docs/requirements.md`, `docs/decisions.md`); awaiting sign-off at G0.
- **Owner:** ALL · **Branch:** `docs/`
- **Do:** Never delete entries; mark Superseded and add new ones.
  - D1 FastAPI, D2 Expo + TypeScript, D8 PostgreSQL naming → Accepted.
  - D5 (offline to future work) → Superseded by D10: offline mode with sync is in scope.
  - D6 (local notifications only) → Superseded by D11: local reminders plus server push (Expo push).
  - D7 (external Vision API, not a self-trained model) → Superseded by D12: self-hosted pretrained model `BinhQuocNguyen/food-recognition-model` behind an `ai-service` container with a provider interface (see D-05 for the risks found in its model card).
  - D13: Manual data entry for exercises and foods, following the ERD.
  - D14: Google and Apple sign-in in addition to email/password.
  - D15: Report export (PDF/CSV) and automatic weekly report.
- **Done when:** table updated, all Proposed items resolved.

---

# Phase 1 — Design

### D-01 · Database schema redesign (PostgreSQL)
- **Status:** drafted: `docs/database/schema_postgres.sql` (36 tables, loads into PostgreSQL 16, `scripts/test_schema.sql` passes); awaiting sign-off at G1.
- **Owner:** DATA · **Branch:** `db/` · **Reqs:** all data-bearing FR, FR-U5, NFR reliability · **Depends on:** R-01, D-05, D-07
- **Do:** Produce `docs/database/schema_postgres.md` and an updated `ERD.png`. Resolve every item below, apply D8 naming (snake_case, `users` instead of `user`, `GENERATED ALWAYS AS IDENTITY`, `TIMESTAMPTZ`, CHECK constraints such as weight 30–300, RPE 1–10, hunger 1–10, one active plan per user via partial unique index).
- **Done when:** every FR maps to tables/columns; every row below is closed; reviewed by API and APP.

Problems found in `scheme_mysql.sql` and the change required:

| # | Problem | Change |
| - | ------- | ------ |
| 1 | `User.password_hash` has a UNIQUE index | drop it |
| 2 | All FKs are `ON DELETE NO ACTION`, which blocks FR-U5 account deletion | `ON DELETE CASCADE` for all user-owned tables |
| 3 | `user` is a reserved word; PascalCase and `User_idUser` naming | D8 naming |
| 4 | `UserProfile` has no experience level or equipment, both needed by FR-P1; `target_type DECIMAL` is unclear | add `experience_level`, `equipment`; rename to `target_weight_kg` (needed by FR-R4, confirm meaning) |
| 5 | Goal enum typo `edurance` in three tables | `endurance` |
| 6 | No allergens/intolerances (FR-P6, FR-N3) | add `allergen`, `user_allergen`, `food_item_allergen` |
| 7 | `Injury.injury_type` VARCHAR duplicates the FK; `affected_muscle_group` is free text | remove VARCHAR, FK to `muscle_group` |
| 8 | Nothing links injuries to excluded exercises (FR-P2 acceptance) | add `injury_type_excluded_exercise` (or rule by muscle group + severity, decide here) |
| 9 | `Exercise.main/secondary_muscle_group` VARCHARs duplicate `Exercise_has_MuscleGroup`; `required_equipment` is free text and cannot be filtered | main muscle group FK, secondary via junction, `equipment` as enum (gym/home/none); name length 100 |
| 10 | `BodyMetrics` primary key is the user only, so only one row per user and no history; weight is INT | surrogate PK plus unique `(user_id, measured_on)`; weight `DECIMAL(5,2)` |
| 11 | `WorkoutLog` holds one set/reps/weight value per session; the junction table has no data | `workout_log` (session level) plus `workout_set_log` (exercise, set no, reps, weight, rpe, completed) for FR-A2/A4/A5, tonnage and PR |
| 12 | FR-A4 changes must be explainable | add `plan_adjustment` (session_exercise, reason, old/new values) |
| 13 | `Meal.time` is a DATE; `FoodItem` carries `Meal_idMeal`/`Meal_DietPlan_idDietPlan`, which breaks the M:N relation | fix time type and day index; remove those FK columns from `food_item` |
| 14 | `Meal_has_FoodItem` and `NutritionLog_has_FoodItem` have no `grams` | add `grams` and computed macros |
| 15 | `FoodItem.category` VARCHAR duplicates `FoodCategory` | drop it; add `default_portion_g` and nullable unique `recognition_label` for AI mapping |
| 16 | `NutritionLog.RecognitionAI` FK is NOT NULL (blocks manual logs); hunger columns NOT NULL | make nullable; add nullable `meal_id` (planned meal) for FR-R2 diet compliance |
| 17 | `ProgressReport.estimated_goal_completion_date` NOT NULL (FR-R4/R5 need "no prediction"); no diet compliance; `raport_type` typo | nullable; add diet/workout compliance %; `report_type` |
| 18 | `Notification` is not suitable for local reminders (`is_sent`, `is_dismissed`) | add `recurrence`, `is_enabled`; add `device_push_token` |
| 19 | Missing auth tables | `password_reset_token` (FR-U3), `refresh_token` (B-02), `oauth_identity` (FR-U8) |
| 20 | No sync metadata | `client_uuid`, `updated_at`, `deleted_at` on offline-capable tables (from D-07) |
| 21 | `SessionExercise.order` is a reserved word | `position` |

### D-02 · MongoDB buffer spec update
- **Owner:** DATA · **Branch:** `docs/` · **Depends on:** D-05
- **Do:** Update `mongo_buffer.md`: add `labelCandidates` (top-K from the model), `defaultPortionUsed`, allergy warnings per item, photo path convention, cleanup job behaviour.
- **Done when:** the document matches D-05 and the confirm transaction in B-20.

### D-03 · API contract (OpenAPI), frozen at G1
- **Status:** drafted in `docs/api/openapi.yaml` (84 operations, structural check `scripts/check_openapi.py` passes); awaiting sign-off at G1. The table below is the original plan; the YAML wins on any difference.
- **Owner:** API + APP · **Branch:** `docs/` · **Depends on:** R-01, D-01, D-04
- **Do:** Write `docs/api/openapi.yaml` (versioned `/api/v1`) with schemas, a common error model (field-level validation errors, stable error codes), pagination, auth scheme, upload limits. Starting endpoint list:

| Area | Endpoints |
| --- | --- |
| Auth | `POST /auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/password/forgot`, `/auth/password/reset`, `/auth/google`, `/auth/apple` |
| Account | `GET /users/me`, `POST /users/me/delete`, `POST /users/me/email`, `POST /users/me/password`, `GET/PUT /users/me/profile`, `GET/POST/PATCH/DELETE /users/me/injuries`, `GET/PUT /users/me/allergies`, `GET /injury-types`, `GET /allergens` |
| Library | `GET /muscle-groups`, `GET /exercises`, `GET /exercises/{id}`, `GET /exercises/{id}/alternatives`, `GET /foods`, `GET /foods/{id}`, `GET /food-categories` |
| Plans | `GET /nutrition/targets`, `POST /training-plans/generate`, `GET /training-plans/active`, `POST /training-plans/{id}/accept`, `PUT /session-exercises/{id}/swap`, `POST /diet-plans/generate`, `GET /diet-plans/active`, `POST /diet-plans/{id}/accept` |
| Schedule | `GET/PUT /reminders`, `POST /devices/push-token` |
| Workouts | `GET /sessions/next`, `POST /workouts`, `GET /workouts` (RPE and hunger are sent inside `POST /workouts`; there is no separate feedback endpoint) |
| Nutrition | `POST /meals/recognitions` (multipart), `GET /meals/recognitions/{id}`, `POST /meals/recognitions/{id}/items`, `PATCH/DELETE /meals/recognitions/{id}/items/{index}`, `POST /meals/recognitions/{id}/confirm`, `DELETE /meals/recognitions/{id}`, `POST/GET /nutrition-logs`, `GET /nutrition/daily-summary`, `GET /nutrition/suggestions` |
| Body | `POST/GET /body-metrics` |
| Analytics | `GET /analytics/{metric}?period=`, `GET /analytics/goal-prediction`, `GET /reports`, `GET /reports/{id}`, `GET /reports/{id}/export?format=pdf\|csv` |
| Sync | `POST /sync/push`, `GET /sync/pull?cursor=` |
| Meta | `GET /health` |

- **Done when:** every FR is reachable through at least one endpoint; APP and API sign off; the spec lints without errors.

### D-04 · Algorithm specification
- **Status:** drafted: `docs/algorithms.md` + `scripts/algorithms_reference.py --check` (test vectors); awaiting sign-off at G1.
- **Owner:** API · **Branch:** `docs/` · **Reqs:** FR-P1…P6, FR-A4, FR-A5, FR-R2, FR-R4 · **Depends on:** R-01
- **Do:** Write `docs/algorithms.md` with formulas, constants and worked examples that become test vectors:
  - BMR (Mifflin-St Jeor), TDEE = BMR × PAL, calorie adjustment per goal, macro split per goal.
  - Training split by number of days, exercise selection (muscle group, level, equipment, injuries), sets/reps/rest by goal and level, behaviour on insufficient exercises (FR-P3).
  - Diet generation: meal slots, product selection (allergies, preferences), gram scaling with tolerance (proposed ±5 % kcal and macros).
  - Adaptation: reduction on RPE ≥ 9 or failed set, progression on "set with reserve", no change without a signal.
  - Plan compliance %, goal-date prediction (linear regression of weight over time), irregular-data criterion.
- **Done when:** every formula has at least two worked examples; constants are listed in one table.

### D-05 · AI module design and model feasibility
- **Owner:** API · **Branch:** `docs/` · **Reqs:** FR-N1…N4, NFR photo analysis ≤ 10 s · **Depends on:** R-01
- **Do:** Evaluate `huggingface.co/BinhQuocNguyen/food-recognition-model` before anything is built on it. What its public page shows:
  - Claims EfficientNet-B0 classification over 101 Food-101 categories plus YOLO detection and calorie estimation, TensorFlow, MIT licence.
  - The repository has only five files: `README.md`, `config.json`, `nutritional_database.json` (17 kB), `.gitattributes` and `classification_model.h5`, which is listed at 121 bytes. That size is typical of a pointer file, so the weights may be missing. The folder total is 22.3 kB, which supports this. It was not possible to download the file to confirm.
  - `config.json` has no architecture and no labels; there is no YOLO weights file; no Inference API provider; about 32 downloads last month; the stated metrics have no evaluation details.
  - Food-101 labels are whole dishes (pizza, sushi, …), not ingredients like "pierś z kurczaka" or "ryż biały", and a classifier gives one label per image, while FR-N2 asks for a list of products with grams.
- **Steps:** (1) download the repo and check whether the weights load and what the label list is; (2) run on a sample set of at least 50 photos, including typical Polish meals; (3) measure top-1 / top-3 accuracy and CPU latency; (4) decide with the thresholds below.
- **Design decisions to record:**
  - Provider interface `RecognitionProvider.predict(image) -> list[Candidate]`, so the model can be replaced.
  - Run the model in a separate `ai-service` container (keeps TensorFlow out of the backend image); backend calls it over HTTP with a timeout.
  - Return the top-K labels (K=3) as candidates, plus manual add/remove in the review step (FR-N4).
  - Grams: the model does not give a documented, reliable weight estimate, so use `food_item.default_portion_g` as the starting value and let the user correct it (FR-N4).
  - Label → `FoodItem` mapping through `food_item.recognition_label`; unmatched labels return `foodItemId: null` as in the Mongo spec.
  - Check whether `nutritional_database.json` can seed DB-05 (verify values manually).
- **Go / no-go (proposed thresholds, tune at the gate):** Go if the weights load and top-3 accuracy is at least 80 % on the Food-101 sample and at least 60 % on the Polish sample, with CPU latency that leaves the whole request under 10 s. Otherwise the fallback is another pretrained Food-101 classifier from the Hugging Face Hub, or fine-tuning EfficientNet-B0 on the public Food-101 dataset. The interface and the rest of the design do not change.
- **Done when:** a written verdict with measured numbers is in `docs/ai_evaluation.md` and D12 is updated.

### D-06 · Security design
- **Owner:** API + DATA · **Branch:** `docs/` · **Reqs:** NFR security, FR-U2…U5
- **Do:** Access and refresh token lifetimes with rotation and revocation; bcrypt cost; login rate limiting and lockout; password reset token (hashed, single use, expiry, no user enumeration); account deletion cascade including Mongo documents and photo files; CORS, security headers, upload validation and EXIF stripping; log hygiene (no passwords, tokens or full emails); object-level authorization rule (a user can only read own rows); HTTPS-only deployment.
- **Done when:** a checklist exists that T-05 can execute.

### D-07 · Offline mode and sync design
- **Owner:** API + APP · **Branch:** `docs/` · **Reqs:** NFR-OFF · **Depends on:** R-01
- **Do:** List the entities usable offline (active plans read-only, workout logs, nutrition logs, body metrics). Local SQLite schema, client-generated UUIDs, `updated_at` and tombstones, push/pull protocol with cursor, idempotency, conflict policy (decided: optimistic concurrency, the client sends `base_updated_at`; a stale write is rejected with `conflict` and the server version is returned; workout and nutrition logs are append-only), what is explicitly online-only (plan generation, photo recognition, reports).
- **Done when:** the protocol is in the OpenAPI spec and the sync columns are in D-01.

### D-08 · Notifications design
- **Owner:** API + APP · **Branch:** `docs/` · **Reqs:** FR-P9, FR-R7 · **Depends on:** D-01
- **Do:** Local reminders (training days, meal times) scheduled on the device from the stored schedule; server push through the Expo push service for the weekly report and achievements; token registration and revocation; message types from the ERD enum; behaviour when permission is denied.
- **Done when:** both flows are described end to end with the endpoints used.

### D-09 · Mobile app design
- **Owner:** APP · **Branch:** `docs/` · **Reqs:** NFR usability, UI, compatibility
- **Do:** Navigation map; full screen inventory including screens with no mockup in chapter 7 (forgot/reset password, settings, libraries, workout session, recognition review, body metrics, reports, offline states); wireframes for those; design tokens for light and dark theme; empty/loading/error/offline states; form validation rules mirrored from the API; stack choice (Expo, TypeScript, React Navigation or Expo Router, TanStack Query, react-hook-form with zod, `expo-secure-store`, `expo-camera`/`expo-image-picker`, `expo-notifications`, `expo-sqlite`, a chart library). Nielsen-heuristics checklist.
- **Done when:** every FR with a UI part has a screen; stack recorded in `decisions.md`.

### D-10 · Deployment and environments design
- **Owner:** ALL · **Branch:** `docs/`
- **Do:** Containers (`postgres`, `mongo`, `backend`, `ai-service`, SMTP catcher for dev), volumes (photos, database), reverse proxy with TLS, environments (dev, test, prod-like), secrets handling, CI stages, hosting choice, backup approach.
- **Done when:** a diagram plus the list of environment variables for `.env.example`.

### D-11 · Test plan
- **Owner:** ALL · **Branch:** `docs/`
- **Do:** Test levels, tools (pytest, Jest with React Native Testing Library, Maestro for end-to-end, k6 or Locust for load, schemathesis for the contract), requirement-to-test traceability, measurement method for each NFR, usability test protocol, exit criteria for G3.
- **Done when:** every FR and NFR has at least one planned test.

**Gate G1 checklist:** D-01…D-11 reviewed; OpenAPI frozen; AI verdict recorded; no open design question.

---

# Phase 2 — Implementation

## 2.1 Foundation and data

### B-01 · Repository scaffolding and local stack
- **Owner:** DATA (compose, CI) + API (app skeleton) · **Branch:** `db/`, `api/` · **Depends on:** D-10
- **Do:** Add the missing `docker-compose.yml` (README already promises `docker compose up -d`) with postgres, mongo, backend, ai-service and an SMTP catcher; update `.env.example`. FastAPI app factory, settings via environment, `/health`, structured logging, global error handler producing the contract error model, ruff, pytest, GitHub Actions (lint, tests, OpenAPI export).
- **Done when:** `cp .env.example .env && docker compose up -d` gives a healthy stack on a clean machine; CI is green.

### DB-01 · PostgreSQL models and Alembic migrations
- **Owner:** DATA · **Branch:** `db/` · **Depends on:** D-01, B-01
- **Do:** SQLAlchemy 2.0 models in `backend/app/db/models/`, initial migration, indexes, CHECK constraints, enums, naming convention.
- **Done when:** `alembic upgrade head` works from an empty database and `downgrade` works; a test deletes a user and verifies all owned rows are gone.

### DB-02 · MongoDB buffer layer
- **Owner:** DATA · **Branch:** `db/` · **Reqs:** FR-N4 · **Depends on:** D-02, B-01
- **Do:** `meal_recognitions` repository, TTL index on `expiresAt` and `(userId, status)` index created at startup, queries that ignore documents already past `expiresAt` (the TTL monitor runs about once a minute).
- **Done when:** tests prove an expired-but-not-yet-deleted document is never returned.

### DB-03 · Seed reference data
- **Owner:** DATA · **Branch:** `db/` · **Depends on:** DB-01
- **Do:** SQL seed files in `database/seed/` for muscle groups, injury types, food categories, allergens, plus an idempotent loader.
- **Done when:** running the loader twice gives identical data.

### DB-04 · Seed exercises (manual, following the ERD)
- **Owner:** DATA · **Branch:** `db/` · **Reqs:** FR-P1, FR-P2, FR-P3, FR-P8 · **Depends on:** DB-03
- **Do:** Enter exercises with name, main and secondary muscle groups, level, equipment, description, text instruction and injury exclusions. Write a coverage script: for every goal's main muscle groups × equipment (gym/home/none) × level, count exercises and report gaps. Gaps are allowed, because FR-P3 defines what the app does for them, but each must be a conscious one.
- **Done when:** every exercise has all fields filled; the coverage report is committed; the generator tests in B-11 pass on this data.

### DB-05 · Seed foods (manual, following the ERD)
- **Owner:** DATA · **Branch:** `db/` · **Reqs:** FR-N2, FR-P6, FR-P8 · **Depends on:** DB-03, D-05
- **Do:** Enter foods with per-100 g values, category, allergens, `default_portion_g` and `recognition_label`. Cover every label the chosen model can output (unmapped labels become `null` matches), plus common Polish staples such as chicken breast, white rice, eggs, oats, dairy, vegetables and fruit, so the diet generator can balance protein, carbs and fat. A validation script checks that kcal is roughly 4·protein + 4·carbs + 9·fat (tolerance proposed ±10 %).
- **Done when:** the validation script passes; every recognition label is mapped or listed as intentionally unmapped.

### DB-06 · Seed validation in CI
- **Owner:** DATA · **Branch:** `db/` · **Depends on:** DB-03…DB-05
- **Do:** CI step that loads the seeds into a clean database and runs the coverage and validation scripts.
- **Done when:** CI fails on a deliberately broken seed row.

## 2.2 Backend core

### B-02 · Security primitives
- **Owner:** API · **Branch:** `api/` · **Reqs:** FR-U2, NFR security · **Depends on:** D-06, DB-01
- **Do:** bcrypt hashing, JWT access plus refresh tokens with rotation and a revocation table, `get_current_user` dependency, rate limiting on auth routes, object-level authorization helper.
- **Done when:** tests cover expired, tampered and revoked tokens and a reused refresh token.

### B-03 · Registration, login, refresh, logout
- **Owner:** API · **Branch:** `api/` · **Reqs:** FR-U1, FR-U2 · **Depends on:** B-02
- **Done when:** duplicate email gives the contract error; wrong password and unknown email give the same response; passwords are never logged or returned.

### B-04 · Password reset by email
- **Owner:** API · **Branch:** `api/` · **Reqs:** FR-U3 · **Depends on:** B-03
- **Do:** Reset token table, SMTP sender with templates, single-use and expiring tokens (stored hashed), same response whether or not the email exists, all refresh tokens revoked after a reset.
- **Done when:** an end-to-end test reads the mail from the SMTP catcher and completes the reset; reusing the token fails.

### B-05 · Account settings and deletion
- **Owner:** API · **Branch:** `api/` · **Reqs:** FR-U4, FR-U5 · **Depends on:** B-03, DB-02
- **Do:** Change email and password (current password required); `DELETE /users/me` removes Postgres rows, Mongo documents and photo files.
- **Done when:** after deletion a data audit query finds nothing for that user in any store.

### B-06 · Biometric profile, injuries, allergies
- **Owner:** API · **Branch:** `api/` · **Reqs:** FR-U6, FR-U7 · **Depends on:** B-03, DB-03
- **Do:** Endpoints with Pydantic validation (ranges from R-01) returning field-level errors; TDEE recomputed when relevant fields change.
- **Done when:** boundary tests (29/30/300/301 kg and the other ranges) pass; missing fields give a clear error per field.

### B-07 · Google and Apple sign-in
- **Owner:** API · **Branch:** `api/` · **Reqs:** FR-U8 · **Depends on:** B-03, DB-01
- **Do:** Verify the provider ID token server-side, create or link an account by verified email, store `oauth_identity`, issue the normal JWT pair.
- **Done when:** a forged or expired provider token is rejected; an existing email account is linked, not duplicated. Apple is blocked until an Apple Developer account exists.

### B-08 · Exercise library endpoints
- **Owner:** API · **Branch:** `api/` · **Reqs:** FR-P8, FR-A1 · **Depends on:** DB-04
- **Do:** List with filters (muscle group, equipment, level, text search) and pagination, detail with instructions, and `/alternatives` (same main muscle group, compatible with the user's equipment, level and injuries).
- **Done when:** alternatives never include an exercise excluded by the user's injuries.

### B-09 · Food library endpoints
- **Owner:** API · **Branch:** `api/` · **Reqs:** FR-P8 · **Depends on:** DB-05
- **Done when:** search by name and category works with pagination; nutrition values are returned per 100 g.

### B-10 · Nutrition calculator
- **Owner:** API · **Branch:** `api/` · **Reqs:** FR-P4, FR-P5 · **Depends on:** D-04, B-06
- **Do:** BMR/TDEE, goal calorie target, macro split; `GET /nutrition/targets`.
- **Done when:** the worked examples from D-04 pass as unit tests.

### B-11 · Training plan generator
- **Owner:** API · **Branch:** `api/` · **Reqs:** FR-P1, FR-P2, FR-P3, FR-P7 · **Depends on:** D-04, DB-04, B-06
- **Do:** Generate, accept and regenerate plans; persist `training_plan`, sessions and session exercises; return the structured "not enough exercises" result with suggested alternatives (goal or equipment).
- **Done when:** a property test over all goal × level × equipment × injury combinations shows at least one exercise per main muscle group of the goal and none excluded by injuries; plan generation takes at most 3 s (95th percentile) on the seeded database.

### B-12 · Diet plan generator
- **Owner:** API · **Branch:** `api/` · **Reqs:** FR-P6, FR-P7 · **Depends on:** D-04, B-10, DB-05
- **Do:** Meals per day, product choice respecting allergies and preferences, gram scaling to the targets, accept and regenerate.
- **Done when:** daily kcal and macros are within the D-04 tolerance for every goal in tests; no product with a user's allergen is ever selected.

### B-13 · Exercise swap
- **Owner:** API · **Branch:** `api/` · **Reqs:** FR-A1 · **Depends on:** B-08, B-11
- **Done when:** a swap keeps sets, reps and rest, rejects an exercise from another muscle group, and rejects one excluded by injuries.

### B-14 · Schedule and reminders
- **Owner:** API · **Branch:** `api/` · **Reqs:** FR-P9 · **Depends on:** D-08, B-11, B-12
- **Do:** Store training days and meal times; endpoints to read and update; recompute proposed reminders when a plan is accepted.
- **Done when:** the schedule round-trips and respects the user's time zone.

### B-15 · Workout logging and feedback
- **Owner:** API · **Branch:** `api/` · **Reqs:** FR-A2, FR-A3 · **Depends on:** B-11, DB-01
- **Do:** `POST /workouts` with per-set data, RPE 1–10, "set not completed" flag; update `personal_record` on a new best; `GET /sessions/next`.
- **Done when:** RPE outside 1–10 is rejected; a PR is detected and stored only when it is a real improvement.

### B-16 · Adaptation engine
- **Owner:** API · **Branch:** `api/` · **Reqs:** FR-A4, FR-A5 · **Depends on:** D-04, B-15
- **Do:** After a workout, reduce the next session only on RPE ≥ 9 or an incomplete set; increase load on "set with reserve"; write each change to `plan_adjustment`.
- **Done when:** a test shows no adjustment is ever created without an explicit signal; reductions and progressions match the D-04 examples.

### B-17 · Body metrics
- **Owner:** API · **Branch:** `api/` · **Reqs:** FR-R1 (data), FR-U6 · **Depends on:** DB-01
- **Do:** Add and list measurements (weight plus optional circumferences and body fat); update the current weight in the profile.
- **Done when:** history is kept (several rows per user per period); values are range-validated.

## 2.3 Nutrition AI

### B-18 · `ai-service` (inference microservice)
- **Owner:** API · **Branch:** `api/` · **Reqs:** FR-N2, NFR photo ≤ 10 s · **Depends on:** D-05, B-01
- **Do:** Container that loads the verified model at startup, exposes `/predict` and `/health`, validates image type and size, resizes, returns top-K labels with confidence; request timeout; model name and version in the response.
- **Done when:** the container starts offline from the stored weights, and median inference time is documented.

### B-19 · Recognition: upload and analysis
- **Owner:** API · **Branch:** `api/` · **Reqs:** FR-N1, FR-N2, FR-N3 · **Depends on:** B-18, DB-02, DB-05
- **Do:** Multipart upload (type, size, EXIF stripped), store the photo, call `ai-service` through the provider interface, map labels to foods, apply default portions, compute nutrition per item, attach allergy warnings from the user's allergens, write the Mongo document with `status: pending`.
- **Done when:** the end-to-end request takes at most 10 s in the test setup; an allergen in a recognised item is flagged; an unknown label gives `foodItemId: null`.

### B-20 · Recognition: review, correct, confirm
- **Owner:** API · **Branch:** `api/` · **Reqs:** FR-N4 · **Depends on:** B-19
- **Do:** Edit, add and remove items and change grams (nutrition recalculated, `corrected` set); confirm writes `nutrition_log`, `nutrition_log_has_food_item` and `recognition_ai` in one transaction, then deletes the document; scheduled cleanup removes photos of expired, unconfirmed recognitions.
- **Done when:** a failure in the middle of the confirm transaction leaves PostgreSQL unchanged and the Mongo document intact; no orphan photo remains after expiry.

### B-21 · Manual nutrition log and daily summary
- **Owner:** API · **Branch:** `api/` · **Reqs:** FR-A3, FR-R2 · **Depends on:** B-12, DB-05
- **Do:** Log a meal manually or from the plan, hunger before/after, `GET /nutrition/daily-summary` with totals against targets.
- **Done when:** totals match the sum of logged items; hunger values are validated.

### B-22 · Real-time meal suggestions
- **Owner:** API · **Branch:** `api/` · **Reqs:** FR-N5 · **Depends on:** B-21, B-10
- **Do:** From the remaining calories and macros of the day, rank foods or plan meals that fit, respecting allergies.
- **Done when:** suggestions never exceed the remaining kcal beyond a stated tolerance and never contain an allergen.

## 2.4 Analytics and reports

### B-23 · Analytics aggregation
- **Owner:** API · **Branch:** `api/` · **Reqs:** FR-R1, FR-R2, FR-R3, FR-R5 · **Depends on:** B-15, B-17, B-21
- **Do:** Weight change, strength in key exercises, tonnage, workouts per week, calorie intake, diet and workout compliance %, for week / month / 3 months. Fewer than 7 days of data returns a "not enough data" status.
- **Done when:** results match hand-computed fixtures; the 6-day and 7-day boundary is tested.

### B-24 · Goal date prediction
- **Owner:** API · **Branch:** `api/` · **Reqs:** FR-R4 · **Depends on:** D-04, B-23
- **Do:** Linear trend of weight against `target_weight_kg`; warning when data is irregular; no date when the trend moves away from the goal.
- **Done when:** fixtures cover regular, irregular, flat and wrong-direction data.

### B-25 · Reports and export
- **Owner:** API · **Branch:** `api/` · **Reqs:** FR-R1, FR-R6 · **Depends on:** B-23, B-24
- **Do:** Generate and persist `progress_report` (weekly, monthly, custom), list and detail endpoints, PDF and CSV export.
- **Done when:** the CSV values equal the report values; the PDF opens and contains the same figures.

### B-26 · Scheduler and push
- **Owner:** API · **Branch:** `api/` · **Reqs:** FR-R7, FR-P9 · **Depends on:** D-08, B-25
- **Do:** Scheduled jobs: weekly report generation plus push, expired-photo cleanup; push sender through Expo; token registration endpoint; invalid tokens removed.
- **Done when:** a weekly job creates exactly one report per user per week even if it runs twice.

## 2.5 Extended scope: offline sync (backend)

### B-27 · Sync endpoints
- **Owner:** API · **Branch:** `api/` · **Reqs:** NFR-OFF · **Depends on:** D-07, DB-01
- **Do:** `POST /sync/push` (idempotent by client UUID) and `GET /sync/pull?cursor=` with tombstones and the conflict policy from D-07.
- **Done when:** replaying the same push twice changes nothing; two devices editing the same record converge.

## 2.6 Backend cross-cutting

### B-28 · Contract conformance
- **Owner:** API · **Branch:** `api/` · **Depends on:** D-03
- **Do:** Check that the generated OpenAPI equals the frozen spec; fail CI on drift; run schemathesis against the app.
- **Done when:** CI blocks an undeclared change to a response schema.

### B-29 · Hardening and capacity
- **Owner:** API · **Branch:** `api/` · **Reqs:** NFR scalability, security · **Depends on:** B-03
- **Do:** Request IDs, CORS, security headers, body size limits, database pool and worker configuration aimed at 500 concurrent sessions.
- **Done when:** the settings are documented and a smoke load test shows no connection pool exhaustion.

## 2.7 Mobile

### M-01 · App scaffolding
- **Owner:** APP · **Branch:** `app/` · **Depends on:** D-03, D-09
- **Do:** Expo + TypeScript project in `mobile/`, folder structure, navigation, linting, environment config, API client generated from the OpenAPI spec, a mock server for the contract, central error handling.
- **Done when:** the app builds and runs on an Android emulator against the mock server; CI runs lint and tests.

### M-02 · Design system and theming
- **Owner:** APP · **Branch:** `app/` · **Reqs:** NFR UI, usability · **Depends on:** M-01
- **Do:** Tokens, light and dark theme (follows the system, manual override persisted), shared components (button, input, card, tabs, chart card, toast, empty and error states), layouts tested on 4.7 to 6.7 inch screens.
- **Done when:** every shared component renders in both themes; no horizontal overflow at 4.7 in.

### M-03 · Auth session handling
- **Owner:** APP · **Branch:** `app/` · **Reqs:** FR-U2 · **Depends on:** M-01
- **Do:** Tokens in `expo-secure-store`, refresh interceptor, session restore on launch, logout, auth guard.
- **Done when:** an expired access token is refreshed transparently; a failed refresh sends the user to login.

### M-04 · Login and registration screens
- **Owner:** APP · **Branch:** `app/` · **Reqs:** FR-U1, FR-U2, FR-U8 · **Depends on:** M-03
- **Do:** "Create Account" and "Welcome Back" from the mockups, validation, Google and Apple buttons.
- **Done when:** server validation errors appear next to the correct field.

### M-05 · Forgot and reset password
- **Owner:** APP · **Branch:** `app/` · **Reqs:** FR-U3 · **Depends on:** M-04
- **Do:** Request screen, deep link from the email into the reset screen, success and expired-link states.
- **Done when:** the link opens the app and completes a reset against a dev backend.

### M-06 · Profile onboarding wizard
- **Owner:** APP · **Branch:** `app/` · **Reqs:** FR-U6, FR-U7 · **Depends on:** M-04
- **Do:** "Set Up Your Profile" with progress indicator: age, sex, weight, height, PAL list, goal, experience level, equipment, injuries, allergies; client-side range validation matching the API with clear messages.
- **Done when:** values outside the ranges (for example 29 or 301 kg) show a message and cannot be submitted; completing the wizard lands on Home.

### M-07 · Home screen
- **Owner:** APP · **Branch:** `app/` · **Depends on:** M-02
- **Do:** 2×2 Quick Actions (Training Plan, Diet Plan, AI Food Scanner, Analytics), offline banner.
- **Done when:** every tile navigates to its feature.

### M-08 · Settings and profile management
- **Owner:** APP · **Branch:** `app/` · **Reqs:** FR-U4, FR-U5, FR-U6 · **Depends on:** M-06
- **Do:** Edit biometric profile, change email and password, delete account with double confirmation, theme switch, reminder settings, logout.
- **Done when:** after deletion the app clears all local data and returns to login.

### M-09 · Exercise and food libraries
- **Owner:** APP · **Branch:** `app/` · **Reqs:** FR-P8 · **Depends on:** M-02
- **Do:** Search, filters and detail pages with text instructions and nutrition values.
- **Done when:** long lists scroll smoothly with pagination.

### M-10 · Training plan screens
- **Owner:** APP · **Branch:** `app/` · **Reqs:** FR-P1, FR-P3, FR-P7, FR-A1 · **Depends on:** M-06
- **Do:** Generation form (goal, days, level, equipment), day tabs, "Regenerate Plan", accept, the "not enough exercises" message with suggestions, exercise swap sheet, edit.
- **Done when:** the insufficient-exercises result shows its suggestions; a swap updates the plan immediately.

### M-11 · Diet plan screens
- **Owner:** APP · **Branch:** `app/` · **Reqs:** FR-P4…P7 · **Depends on:** M-06
- **Do:** TDEE and Target header, daily targets, today's totals, meals with product cards and macros, "Regenerate Plan", accept, preference and allergy edit.
- **Done when:** the displayed values equal the API response.

### M-12 · Schedule and reminders
- **Owner:** APP · **Branch:** `app/` · **Reqs:** FR-P9, FR-R7 · **Depends on:** M-10, M-11, D-08
- **Do:** Pick training days and meal times; schedule local notifications with `expo-notifications`; reschedule when the plan changes; handle denied permission; register the push token.
- **Done when:** a reminder fires at the configured time on a real Android 10+ device.

### M-13 · Workout session screen
- **Owner:** APP · **Branch:** `app/` · **Reqs:** FR-A2, FR-A4, FR-A5 · **Depends on:** M-10
- **Do:** Run a session, log sets (reps, weight), rest timer, "could not complete" marker, RPE 1–10 at the end, message when the next session is adjusted, load increase suggestions, PR highlight.
- **Done when:** an RPE of 9 or more or a failed set is sent to the API and the resulting change is shown.

### M-14 · Nutrition logging
- **Owner:** APP · **Branch:** `app/` · **Reqs:** FR-A3 · **Depends on:** M-11
- **Do:** Hunger before and after a meal, manual add from the food library, daily totals against targets.
- **Done when:** totals update after each entry.

### M-15 · AI Food Scanner
- **Owner:** APP · **Branch:** `app/` · **Reqs:** FR-N1…N4 · **Depends on:** M-02, B-19 contract
- **Do:** Camera or gallery picker, upload with progress, review screen (items, grams editor, replace, add, remove, confidence, allergy warnings), confirm or discard, slow-request and error handling with retry, "Today's Nutrition" cards.
- **Done when:** a corrected grams value is reflected in the totals before confirming; an allergy warning is visible before saving.

### M-16 · Meal suggestions UI
- **Owner:** APP · **Branch:** `app/` · **Reqs:** FR-N5 · **Depends on:** M-14
- **Do:** Show the remaining kcal and macros and the suggested foods or meals; add a suggestion to the log in one tap.
- **Done when:** suggestions refresh after a new log entry.

### M-17 · Body metrics screen
- **Owner:** APP · **Branch:** `app/` · **Reqs:** FR-R1 (data) · **Depends on:** M-02
- **Do:** Add weight and circumferences, history list.
- **Done when:** entries appear in the weight chart.

### M-18 · Analytics screen
- **Owner:** APP · **Branch:** `app/` · **Reqs:** FR-R1…R5 · **Depends on:** M-17, B-23 contract
- **Do:** Week / Month / 3 Months tabs, four metric tiles, Goal Prediction card with the irregular-data warning, Weight Progress, Weekly Workouts, Calorie Intake and tonnage charts, compliance %, "not enough data" state.
- **Done when:** every state (loading, no data, normal, irregular warning) is reachable and matches the mockups.

### M-19 · Reports and export
- **Owner:** APP · **Branch:** `app/` · **Reqs:** FR-R1, FR-R6, FR-R7 · **Depends on:** M-18
- **Do:** Report list and detail, export and share PDF or CSV, push notification opens the report.
- **Done when:** the exported file opens in an external app and matches the on-screen figures.

### M-20 · Offline mode
- **Owner:** APP · **Branch:** `app/` · **Reqs:** NFR-OFF · **Depends on:** D-07, B-27 contract
- **Do:** `expo-sqlite` store, repository layer, sync queue with background sync on reconnect and app foreground, offline indicator, clear online-only messages.
- **Done when:** a workout and a nutrition entry made in airplane mode appear on the server after reconnecting, without duplicates.

### M-21 · Performance and compatibility pass
- **Owner:** APP · **Branch:** `app/` · **Reqs:** NFR performance, compatibility · **Depends on:** M-01…M-20
- **Do:** Profile and fix slow screens (list virtualisation, memoisation, image sizes), check install size against the ~200 MB budget, run on Android 10+ and 4 GB RAM devices.
- **Done when:** interactions respond within 300 ms on the reference device; the release build stays within the size budget.

### M-22 · Mobile tests
- **Owner:** APP · **Branch:** `app/` · **Depends on:** M-01…M-20
- **Do:** Jest unit tests, component tests, and Maestro flows for registration + profile, plan generation, meal scan, workout logging, analytics.
- **Done when:** all flows pass in CI or on a documented local run.

**Gate G2 checklist:** every FR/NFR has its implementation task closed; all unit and integration tests green; seeds validated; OpenAPI matches the code.

---

# Phase 3 — Integration and testing

### T-01 · Integration against the real stack
- **Owner:** ALL · **Depends on:** G2
- **Do:** Replace the mock server with the compose stack, fix contract drift, run schemathesis.
- **Done when:** all M-22 flows pass on the real backend.

### T-02 · System tests for requirements and scenarios
- **Owner:** ALL · **Depends on:** T-01
- **Do:** Execute the traceability matrix (section 7), including scenarios S1–S3 of chapter 6.1, the FR-P2 acceptance property test, and the negative FR-A4 test (no signal, no change).
- **Done when:** every FR has a passing test or a documented defect.

### T-03 · AI accuracy evaluation
- **Owner:** API · **Depends on:** T-01
- **Do:** Run the final pipeline on a labelled set of meal photos including Polish dishes; report top-1 and top-3 accuracy, latency and the effect of default portions; set the confidence threshold shown in the app.
- **Done when:** the results are in `docs/ai_evaluation.md` for the thesis.

### T-04 · Performance tests
- **Owner:** API + APP · **Depends on:** T-01
- **Do:** Load test with 500 concurrent sessions (k6 or Locust) against the baseline (degradation at most 20 %); plan generation at most 3 s; photo analysis at most 10 s on a throttled 4G profile; UI interaction at most 300 ms.
- **Done when:** results table with pass or fail per NFR.

### T-05 · Security tests
- **Owner:** API + DATA · **Depends on:** T-01, D-06
- **Do:** Execute the D-06 checklist: object-level access (user A cannot read user B), token tampering, brute force, reset-link enumeration, upload abuse, injection attempts, HTTPS only, dependency audit.
- **Done when:** no open high or critical finding.

### T-06 · Compatibility tests
- **Owner:** APP · **Depends on:** T-01
- **Do:** Android 10 and newer, several screen sizes from 4.7 to 6.7 inch, light and dark mode.
- **Done when:** a device matrix with results.

### T-07 · Usability tests
- **Owner:** APP · **Depends on:** T-01
- **Do:** Heuristic review against Nielsen's list plus sessions with representative users on four tasks (register and profile, generate a plan, scan a meal, read analytics); collect a SUS questionnaire.
- **Done when:** findings of severity 1 and 2 are fixed or consciously accepted.

### T-08 · GDPR deletion check
- **Owner:** DATA + API · **Depends on:** T-01
- **Do:** Delete an account with data in every store and verify nothing remains in Postgres, Mongo, photo files or logs.
- **Done when:** a written audit with the queries used.

### T-09 · Defect closure and regression
- **Owner:** ALL · **Depends on:** T-02…T-08
- **Done when:** all defects closed or accepted; full regression passes. Gate G3 signed.

---

# Phase 4 — Deployment

### Z-01 · Production-like deployment
- **Owner:** DATA + API · **Depends on:** G3, D-10
- **Do:** Compose production profile, reverse proxy with TLS and HSTS (HTTPS only), secrets outside the repository, healthchecks, resource limits for `ai-service`, database backup job and a restore test.
- **Done when:** the stack runs on the target host over HTTPS and a backup restores into a clean instance.

### Z-02 · Mobile release build
- **Owner:** APP · **Depends on:** G3
- **Do:** Signed Android build (EAS Build or local), version number, per-environment API URL, release checklist.
- **Done when:** the installed build works against the production-like server.

### Z-03 · Logs and runbook
- **Owner:** API · **Depends on:** Z-01
- **Do:** Log collection and a short runbook: start, stop, backup, restore, rotate secrets.
- **Done when:** someone other than the author can follow it.

### Z-04 · Release acceptance
- **Owner:** ALL · **Depends on:** Z-01, Z-02
- **Do:** Run the demo scenario end to end on the release build and sign the final traceability matrix. Gate G4.

---

# Phase 5 — Documentation

### W-01 · Update the thesis documentation (Polish)
- **Owner:** ALL · **Branch:** `docs/`
- **Do:** Bring the diagrams and text in line with what was built: deployment diagram (self-hosted AI service), DFD, class diagram, ERD (schema changes from D-01), offline and push flows, implementation chapters, test results, and a short user manual.
- **Done when:** no statement in the document contradicts `decisions.md` or the code.

### W-02 · Developer documentation
- **Owner:** ALL · **Branch:** `docs/`
- **Do:** README with working setup steps, API docs from OpenAPI, seed data guide, contribution workflow.
- **Done when:** a new developer gets a working stack from the README alone.

---

# 6. Scheduling note

The extended-scope items (B-07, B-27, M-20, M-16, M-19 export/push parts, Apple sign-in) add a lot of work to a fixed deadline of 6 Dec 2026. They sit last in each group so the core product (auth, plans, logging, adaptation, scanner, analytics) is complete first. If time runs out, the cut line is: Apple sign-in, then offline sync, then push, then export, then suggestions. Any cut is a change request against the requirements, not a silent omission.

# 7. Traceability matrix

| Requirement | Design | Implementation | Verification |
| --- | --- | --- | --- |
| FR-U1 | D-03 | B-03, M-04 | T-02 |
| FR-U2 | D-06 | B-02, B-03, M-03, M-04 | T-02, T-05 |
| FR-U3 | D-06 | B-04, M-05 | T-02, T-05 |
| FR-U4 | D-03 | B-05, M-08 | T-02 |
| FR-U5 | D-01, D-06 | DB-01, B-05, M-08 | T-08 |
| FR-U6 | D-01 | B-06, M-06, M-08 | T-02 |
| FR-U7 | D-04 | B-06, M-06 | T-02 |
| FR-U8 (new) | D-06 | B-07, M-04 | T-02, T-05 |
| FR-P1 | D-04 | B-11, M-10 | T-02 |
| FR-P2 | D-04 | DB-04, B-11 | T-02 |
| FR-P3 | D-04 | DB-04, B-11, M-10 | T-02 |
| FR-P4 | D-04 | B-10, M-11 | T-02 |
| FR-P5 | D-04 | B-10, M-11 | T-02 |
| FR-P6 | D-04 | DB-05, B-12, M-11 | T-02 |
| FR-P7 | D-03 | B-11, B-12, M-10, M-11 | T-02 |
| FR-P8 | D-03 | DB-04, DB-05, B-08, B-09, M-09 | T-02 |
| FR-P9 | D-08 | B-14, B-26, M-12 | T-02 |
| FR-A1 | D-04 | B-08, B-13, M-10 | T-02 |
| FR-A2 | D-04 | B-15, M-13 | T-02 |
| FR-A3 | D-04 | B-15, B-21, M-14 | T-02 |
| FR-A4 | D-04 | B-16, M-13 | T-02 (negative test) |
| FR-A5 | D-04 | B-16, M-13 | T-02 |
| FR-N1 | D-05 | B-19, M-15 | T-02 |
| FR-N2 | D-05 | B-18, B-19, M-15 | T-02, T-03 |
| FR-N3 | D-05 | DB-05, B-19, M-15 | T-02 |
| FR-N4 | D-02 | DB-02, B-20, M-15 | T-02 |
| FR-N5 (new) | D-04 | B-22, M-16 | T-02 |
| FR-R1 | D-04 | B-23, B-25, M-18, M-19 | T-02 |
| FR-R2 | D-04 | B-21, B-23, M-18 | T-02 |
| FR-R3 | D-04 | B-23, M-18 | T-02 |
| FR-R4 | D-04 | B-24, M-18 | T-02 |
| FR-R5 | D-04 | B-23, M-18 | T-02 |
| FR-R6 (new) | D-03 | B-25, M-19 | T-02 |
| FR-R7 (new) | D-08 | B-26, M-19 | T-02 |
| NFR UI ≤ 300 ms | D-09 | M-21 | T-04 |
| NFR plan ≤ 3 s | D-04 | B-11 | T-04 |
| NFR photo ≤ 10 s | D-05 | B-18, B-19 | T-03, T-04 |
| NFR 500 sessions | D-10 | B-29 | T-04 |
| NFR compatibility | D-09 | M-21 | T-06 |
| NFR security | D-06 | B-02, B-29, Z-01 | T-05 |
| NFR validation / ORM | D-06 | B-06, DB-01 | T-05 |
| NFR reliability (transactions) | D-01 | DB-01, B-20 | T-02 |
| NFR usability | D-09 | M-02 | T-07 |
| NFR light / dark | D-09 | M-02 | T-06 |
| NFR-OFF (new) | D-07 | B-27, M-20 | T-02 |
