"""Add wearable metrics for advanced worker health tracking."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "013_wearables"
down_revision = "012_alert_engine"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "wearable_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("facility_id", sa.String(80), nullable=False),
        sa.Column("metric_date", sa.Date, nullable=False),
        sa.Column("steps", sa.Integer, nullable=False, server_default="0"),
        sa.Column("calories_burned", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sleep_hours", sa.Numeric(4, 1), nullable=False, server_default="0"),
        sa.Column("active_minutes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "metric_date", name="uq_wearable_user_date")
    )
    op.create_index("ix_wearable_user", "wearable_metrics", ["user_id", "metric_date"])

    op.execute("GRANT SELECT, INSERT, UPDATE ON wearable_metrics TO app_user")
    op.execute("GRANT SELECT ON wearable_metrics TO sentinel_admin")
    op.execute("ALTER TABLE wearable_metrics ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE wearable_metrics FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON wearable_metrics
        USING (facility_id = current_setting('app.facility_id', true) AND user_id = current_setting('app.user_id', true))
        WITH CHECK (facility_id = current_setting('app.facility_id', true) AND user_id = current_setting('app.user_id', true))
    """)

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS wearable_metrics CASCADE")
