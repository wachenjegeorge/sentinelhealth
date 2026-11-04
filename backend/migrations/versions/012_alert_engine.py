"""Add autonomous alerts table."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "012_alert_engine"
down_revision = "011_worker_dashboard"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "autonomous_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", sa.String(80), nullable=False),
        sa.Column("county", sa.String(40), nullable=False),
        sa.Column("department", sa.String(60), nullable=False),
        sa.Column("shift", sa.String(10), nullable=False),
        sa.Column("alert_type", sa.String(40), nullable=False), # heat_strain, fatigue_spike, biometric_drift
        sa.Column("severity", sa.String(20), nullable=False), # critical, warning
        sa.Column("details", postgresql.JSONB, nullable=False),
        sa.Column("ai_protocol", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"), # active, acknowledged, resolved
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_alerts_facility_status", "autonomous_alerts", ["facility_id", "status"])

    op.execute("GRANT SELECT, INSERT, UPDATE ON autonomous_alerts TO app_user")
    op.execute("GRANT SELECT ON autonomous_alerts TO sentinel_admin")
    op.execute("ALTER TABLE autonomous_alerts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE autonomous_alerts FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON autonomous_alerts
        USING (facility_id = current_setting('app.facility_id', true))
        WITH CHECK (facility_id = current_setting('app.facility_id', true))
    """)

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS autonomous_alerts CASCADE")
