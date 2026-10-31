"""Grant SELECT on users to sentinel_admin (auth service needs it)."""
from alembic import op

revision = "006_users_grant"
down_revision = "005_facilities_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT SELECT ON users TO sentinel_admin")


def downgrade() -> None:
    op.execute("REVOKE SELECT ON users FROM sentinel_admin")
