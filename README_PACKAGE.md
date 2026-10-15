# FitPlan Pro: execution package

Copy the contents of this folder into the repository root (keep paths). Then give each agent its prompt from `docs/agents/`.
Replace the old `CLAUDE.md`, `docs/requirments.md` (now `docs/requirements.md`), `docs/decisions.md`, `docs/database/mongo_buffer.md`.
Obsolete: `docs/database/scheme_mysql.sql`, `docs/database/ERD.png` (delete after G1).

Checks you can run: `python3 scripts/algorithms_reference.py --check`, `python3 scripts/check_openapi.py`, and the schema load + `scripts/test_schema.sql` on any PostgreSQL 16.
