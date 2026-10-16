"""user_profile.activity_level_pal: numeric(3,2) -> numeric(4,3).

The API offers the PAL values 1.375 and 1.725 (docs/algorithms.md section 0), which two decimals cannot store; the
rounded value changed TDEE by up to 0.4 % and the test vectors of algorithms.md section 2 could not be reproduced.
The existing CHECK (1.20 to 2.40) is unchanged. docs/database/schema_postgres.sql shows the schema after this
migration; a test compares it with the migrated database.

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_profile ALTER COLUMN activity_level_pal TYPE numeric(4,3)")


def downgrade() -> None:
    # Values with a third decimal (1.375, 1.725) are rounded to two decimals.
    op.execute("ALTER TABLE user_profile ALTER COLUMN activity_level_pal TYPE numeric(3,2)")
