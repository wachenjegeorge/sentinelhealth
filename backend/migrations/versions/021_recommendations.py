"""Officer recommendations to hospital heads.

Revision ID: 021_recommendations
Revises: 019_add_verification_filter
"""
from alembic import op

revision = "021_recommendations"
down_revision = "019_add_verification_filter"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS recommendations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            facility_id VARCHAR(80) NOT NULL,
            from_user_id VARCHAR(36) NOT NULL,
            from_username VARCHAR(60) NOT NULL,
            from_role VARCHAR(30) NOT NULL,
            to_role VARCHAR(30) NOT NULL DEFAULT 'hospital_head',
            department VARCHAR(60),
            severity VARCHAR(20) NOT NULL DEFAULT 'medium',
            subject VARCHAR(120) NOT NULL,
            message TEXT NOT NULL,
            related_wvi NUMERIC(5,1),
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            acknowledged_at TIMESTAMPTZ,
            acknowledged_by VARCHAR(36)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_recs_to_facility
        ON recommendations(facility_id, status, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_recs_from_user
        ON recommendations(from_user_id, created_at DESC)
    """)
    op.execute("ALTER TABLE recommendations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE recommendations FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY recs_scope ON recommendations
        USING (
            facility_id = current_setting('app.facility_id', true)
            OR from_user_id = current_setting('app.user_id', true)
        )
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE ON recommendations TO app_user")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS recommendations CASCADE")
