"""Department Head role + fatigue confirmation queue."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "016_department_heads"
down_revision = "015_rbac_hierarchy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fatigue confirmation queue: dept head validates high-fatigue reports
    op.create_table(
        "fatigue_confirmations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("log_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("facility_id", sa.String(80), nullable=False),
        sa.Column("department", sa.String(60), nullable=False),
        sa.Column("worker_id_hash", sa.String(64), nullable=False),
        sa.Column("worker_display_name", sa.String(120), nullable=True),
        sa.Column("worker_username", sa.String(60), nullable=False),
        sa.Column("fatigue", sa.SmallInteger, nullable=False),
        sa.Column("heat_exposure", sa.SmallInteger, nullable=False),
        sa.Column("shift", sa.String(8), nullable=False),
        sa.Column("ai_verdict", sa.String(20), nullable=True),     # likely_real / outlier / uncertain
        sa.Column("ai_reasoning", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),  # pending / confirmed / denied
        sa.Column("confirmed_by", sa.String(36), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('pending','confirmed','denied')",
                           name="ck_fc_status"),
        sa.CheckConstraint("ai_verdict IN ('likely_real','outlier','uncertain') OR ai_verdict IS NULL",
                           name="ck_fc_verdict"),
    )
    op.create_index("ix_fc_facility_dept", "fatigue_confirmations",
                    ["facility_id", "department", "status"])
    op.create_index("ix_fc_created", "fatigue_confirmations",
                    [sa.text("created_at DESC")])

    op.execute("GRANT SELECT, INSERT, UPDATE ON fatigue_confirmations TO app_user")
    op.execute("GRANT SELECT ON fatigue_confirmations TO sentinel_admin")
    op.execute("ALTER TABLE fatigue_confirmations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE fatigue_confirmations FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON fatigue_confirmations
        USING (
            facility_id = current_setting('app.facility_id', true)
            AND (current_setting('app.role', true) IN ('department_head','hospital_head','county_officer','admin'))
        )
        WITH CHECK (facility_id = current_setting('app.facility_id', true))
    """)

    # Add department to users (already exists as primary_department, but ensure index)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_users_facility_dept
        ON users (facility_id, primary_department)
        WHERE role = 'department_head'
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_users_facility_dept")
    op.execute("DROP TABLE IF EXISTS fatigue_confirmations CASCADE")
