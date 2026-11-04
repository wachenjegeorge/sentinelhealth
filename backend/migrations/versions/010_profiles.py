"""Add profile fields to users and allow sentinel_admin to INSERT users."""
from alembic import op
import sqlalchemy as sa

revision = "010_profiles"
down_revision = "009_assistant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Profile columns - all nullable so existing 188 users are unaffected
    op.add_column("users", sa.Column("email", sa.String(120), nullable=True))
    op.add_column("users", sa.Column("phone", sa.String(20), nullable=True))
    op.add_column("users", sa.Column("primary_department", sa.String(60), nullable=True))
    op.add_column("users", sa.Column("must_change_password", sa.Boolean,
                                     nullable=False, server_default="false"))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True),
                                     nullable=True))
    op.add_column("users", sa.Column("approved_at", sa.DateTime(timezone=True),
                                     nullable=True))
    op.add_column("users", sa.Column("approved_by", sa.String(36), nullable=True))
    op.add_column("users", sa.Column("notes", sa.Text, nullable=True))

    op.create_index("ix_users_email", "users", ["email"], unique=True,
                    postgresql_where=sa.text("email IS NOT NULL"))

    # Register endpoint needs INSERT on users. sentinel_admin has SELECT
    # already (from migration 006). Grant INSERT so the auth service can
    # create new users without requiring superuser.
    op.execute("GRANT INSERT ON users TO sentinel_admin")
    op.execute("GRANT UPDATE ON users TO sentinel_admin")


def downgrade() -> None:
    op.execute("REVOKE INSERT ON users FROM sentinel_admin")
    op.execute("REVOKE UPDATE ON users FROM sentinel_admin")
    op.drop_index("ix_users_email", table_name="users")
    for c in ("notes", "approved_by", "approved_at", "last_login_at",
              "must_change_password", "primary_department", "phone", "email"):
        op.drop_column("users", c)
