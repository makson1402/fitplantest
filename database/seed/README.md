# Seed data

Idempotent SQL (`INSERT ... ON CONFLICT (name) DO UPDATE`), applied in file-name order by `load.py` in one transaction.
Names are the natural key, so re-running never duplicates rows and never changes ids.

```
docker compose up -d postgres
cd backend && uv run alembic upgrade head
uv run python ../database/seed/load.py
```

| File | Content | Task |
| --- | --- | --- |
| `001_muscle_groups.sql` | 10 muscle groups (docs/algorithms.md section 3) | DB-03 |
| `002_injury_types.sql` | injury dictionary | DB-03 |
| `003_allergens.sql` | EU 14 allergens plus lactose | DB-03 |
| `004_food_categories.sql` | food categories | DB-03 |
| `005_exercises.sql` | 112 exercises (all 10 groups, 3 levels, 3 equipment tiers) | DB-04 |
| `006_exercise_secondary_muscles.sql` | secondary muscle groups (injury rule 3) | DB-04 |
| `007_injury_excluded_exercises.sql` | exercises each injury type rules out (FR-P2) | DB-04 |

Check and coverage report (also run in CI by DB-06):

```
cd backend && uv run python ../scripts/validate_seed.py --report ../docs/database/exercise_coverage.md
```

Foods follow in DB-05. Each exercise/exclusion file aborts the load if it names an unknown muscle group, exercise or injury type.
