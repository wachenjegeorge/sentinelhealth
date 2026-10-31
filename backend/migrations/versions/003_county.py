"""Add county to logs for county-scoped aggregation."""
from alembic import op
import sqlalchemy as sa

revision = "003_county"
down_revision = "002_seq_grants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "logs",
        sa.Column("county", sa.String(40), nullable=False,
                  server_default="Unknown"),
    )
    op.create_index(
        "ix_logs_county_dept_shift",
        "logs",
        ["county", "department", "shift", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_logs_county_created",
        "logs",
        ["county", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_logs_county_created", table_name="logs")
    op.drop_index("ix_logs_county_dept_shift", table_name="logs")
    op.drop_column("logs", "county")
