# Domain core (API role)

`app/domain/` holds the pure business rules from `docs/algorithms.md`: no database, no FastAPI.
Routers and services (B-02 ... B-29) call these functions and map rows to the small dataclasses.

| Module | Spec | Task |
| --- | --- | --- |
| nutrition.py | sections 1-2 | B-10 |
| training.py | section 4 | B-11, B-13 |
| diet.py, meal_scaling.py | section 5 | B-12 |
| adaptation.py | section 6 | B-16 |
| compliance.py | sections 7-8 | B-23 |
| prediction.py | section 9 | B-24 |
| suggestions.py | section 10 | B-22 |
| constants.py | section 0 | all |

Run tests (needs numpy and scipy): `cd backend && PYTHONPATH=. python3 -m unittest discover -s tests -t .`

Finding for DATA (DB-05/DB-06): `generate_diet` fails with `insufficient_foods` when portion limits make the daily target unreachable
(for example only low-energy carbs with max 450 g). `scripts/validate_seed.py` should check that for every meal type the sum of
`max_portion_g x kcal/100` of the densest item per role can reach 100 % of a 3500 kcal day.
