# Kickoff prompt: agent DATA (database and seed data)

Paste this as the first message in a fresh session on the DATA computer, with the repository checked out on `main`.

---
You are the DATA agent for the FitPlan Pro project (repository in the current directory). Your human reviewer is Kyryl.

1. Read `CLAUDE.md`, then `docs/requirements.md`, `docs/decisions.md`, `docs/tasks.md` (sections 1, 2 and your tasks), `docs/database/schema_postgres.sql`, `docs/database/schema_postgres.md`, `docs/database/mongo_buffer.md`, `docs/algorithms.md` (sections 4, 5, 11).
2. Your area: `database/`, `backend/app/db/`, `backend/alembic/`, DB scripts. Do not edit other areas.
3. Your tasks, in order (each on its own branch and PR): 
   - Phase 1: D-01 and D-02 are drafted; review them against the DDL, fix anything inconsistent, run `scripts/test_schema.sql`, then ask for G1 sign-off. Co-own D-06 (security: token tables, deletion cascade) and D-10 with API.
   - Phase 2, after G1: B-01 (repo scaffolding, docker-compose with Postgres, Mongo, healthchecks), DB-01 (SQLAlchemy 2.0 models and Alembic migrations that create exactly the schema in `schema_postgres.sql`; add a test that the migrated schema equals the SQL file), DB-02 (Mongo buffer layer: collection, indexes, repository), DB-03 (reference seeds: muscle groups, injury types and their excluded exercises, allergens, food categories), DB-04 (exercises), DB-05 (foods), DB-06 (seed validation in CI).
   - Later: T-05, T-08, Z-01 as listed in `docs/tasks.md`.
4. Seed data rules (DB-04, DB-05): data is filled manually per the schema; you prepare it, humans spot-check it. Use idempotent seed scripts (SQL or Python) under `database/seed/`. Source for nutrition values: USDA FoodData Central or the project's `nutritional_database.json` where verified; record the source per row in a comment or sibling CSV. Write `scripts/validate_seed.py`: kcal must agree with 4P + 9F + 4C within 10 %, every non-empty muscle group has exercises for each (equipment, level) combination the generator needs (see algorithms.md section 4), every Food-101 label in `docs/database/food101_labels.txt` that the team keeps has a `food_item.recognition_label`, no duplicate names, portions satisfy min <= default <= max. Aim for broad coverage: at least 8 exercises per main muscle group across all three equipment levels, and at least 150 foods covering all meal types, vegetarian and vegan options and every allergen.
5. Stop and write to `docs/questions.md` when the spec is silent. Do not change the schema silently: schema changes need a PR that updates the SQL, `schema_postgres.md`, the test script and notifies API and APP.
6. Humans must supply: nothing before G1; at DB-04/05 time, a review of the seed data (sample of rows).
Start now with the review in step 3, first bullet.
