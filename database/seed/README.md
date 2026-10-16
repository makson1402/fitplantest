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

Exercises, foods and exercise exclusions follow in DB-04 and DB-05.
