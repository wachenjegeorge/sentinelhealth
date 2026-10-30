"""Grant USAGE on sequences to app_user and sentinel_admin.

audit.id is BigInteger autoincrement, which creates audit_id_seq.
Without USAGE on the sequence, every INSERT into audit fails.
"""
from alembic import op

revision = "002_seq_grants"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sentinel_admin")


def downgrade() -> None:
    op.execute("REVOKE USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public FROM app_user")
    op.execute("REVOKE USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public FROM sentinel_admin")
