"""Department head verification + anomaly triage columns.

Revision ID: 018_dept_head_workflow
Revises: 017_facility_levels

Note: users.id is VARCHAR (UUID-as-string). Reference columns below
must be VARCHAR too, or FK constraints fail with "incompatible types".
"""
from alembic import op

revision = "018_dept_head_workflow"
down_revision = "017_facility_levels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── logs: verification status ───────────────────────
    op.execute("""
        ALTER TABLE logs
        ADD COLUMN IF NOT EXISTS verification_status VARCHAR(16)
            NOT NULL DEFAULT 'auto_verified'
    """)
    # users.id is VARCHAR → verified_by must be VARCHAR (no FK,
    # to avoid length-family mismatch through Neon's pooler)
    op.execute("""
        ALTER TABLE logs
        ADD COLUMN IF NOT EXISTS verified_by VARCHAR
    """)
    op.execute("""
        ALTER TABLE logs
        ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'logs_verification_status_check'
            ) THEN
                ALTER TABLE logs ADD CONSTRAINT logs_verification_status_check
                    CHECK (verification_status IN
                        ('pending','confirmed','denied','auto_verified'));
            END IF;
        END $$;
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_logs_verification
        ON logs(facility_id, department, verification_status)
        WHERE verification_status = 'pending'
    """)

    # ── autonomous_alerts: triage workflow ──────────────
    op.execute("""
        ALTER TABLE autonomous_alerts
        ADD COLUMN IF NOT EXISTS assigned_to_level VARCHAR(20)
            NOT NULL DEFAULT 'department_head'
    """)
    # Same VARCHAR treatment for all user references
    op.execute("""
        ALTER TABLE autonomous_alerts
        ADD COLUMN IF NOT EXISTS assigned_to_user_id VARCHAR
    """)
    op.execute("""
        ALTER TABLE autonomous_alerts
        ADD COLUMN IF NOT EXISTS acknowledged_by VARCHAR
    """)
    op.execute("""
        ALTER TABLE autonomous_alerts
        ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMPTZ
    """)
    op.execute("""
        ALTER TABLE autonomous_alerts
        ADD COLUMN IF NOT EXISTS escalation_chain JSONB
            NOT NULL DEFAULT '[]'::jsonb
    """)
    op.execute("""
        ALTER TABLE autonomous_alerts
        ADD COLUMN IF NOT EXISTS false_positive_reason TEXT
    """)
    op.execute("""
        ALTER TABLE autonomous_alerts
        ADD COLUMN IF NOT EXISTS resolution_notes TEXT
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_alerts_assignment
        ON autonomous_alerts(facility_id, assigned_to_level, status)
        WHERE status IN ('active','acknowledged','escalated')
    """)


def downgrade() -> None:
    for col in (
        "assigned_to_level", "assigned_to_user_id", "acknowledged_by",
        "acknowledged_at", "escalation_chain", "false_positive_reason",
        "resolution_notes",
    ):
        op.execute(f"ALTER TABLE autonomous_alerts DROP COLUMN IF EXISTS {col}")
    for col in ("verification_status", "verified_by", "verified_at"):
        op.execute(f"ALTER TABLE logs DROP COLUMN IF EXISTS {col}")
