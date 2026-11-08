"""Bridge fatigue_confirmations ↔ logs; rebuild agg_logs with verification filter.

Revision ID: 019_add_verification_filter
Revises: 018_dept_head_workflow
"""
from alembic import op

revision = "019_add_verification_filter"
down_revision = "018_dept_head_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Link fatigue_confirmations → logs ────────────
    op.execute("""
        ALTER TABLE fatigue_confirmations
        ADD COLUMN IF NOT EXISTS log_id UUID
            REFERENCES logs(id) ON DELETE CASCADE
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_fc_log_id
        ON fatigue_confirmations(log_id)
        WHERE log_id IS NOT NULL
    """)

    # ── 2. Rebuild agg_logs with verification filter ────
    # Preserves ALL columns and casts from 015's view.
    op.execute("DROP VIEW IF EXISTS agg_logs CASCADE")
    op.execute("""
        CREATE VIEW agg_logs
        WITH (security_invoker = true) AS
        SELECT
            facility_id,
            county,
            department,
            shift,
            date_trunc('day', created_at) AS day,
            count(*)                                            AS n,
            avg(fatigue)::numeric(5,2)                          AS avg_fatigue,
            avg(heat_exposure)::numeric(5,2)                    AS avg_heat,
            avg(risk_score)::numeric(5,1)                       AS avg_score,
            percentile_cont(0.9) WITHIN GROUP (ORDER BY risk_score)::numeric(5,1)
                                                                AS p90_score,
            (count(*) FILTER (WHERE risk_level = 'Critical'))::numeric(4,2)
              / NULLIF(count(*), 0)                             AS critical_share
        FROM logs
        WHERE verification_status IN ('confirmed', 'auto_verified')
        GROUP BY facility_id, county, department, shift,
                 date_trunc('day', created_at)
        HAVING count(*) >= 5
    """)
    op.execute("GRANT SELECT ON agg_logs TO app_user")
    op.execute("GRANT SELECT ON agg_logs TO sentinel_admin")


def downgrade() -> None:
    # Restore 015 view (no verification filter)
    op.execute("DROP VIEW IF EXISTS agg_logs CASCADE")
    op.execute("""
        CREATE VIEW agg_logs
        WITH (security_invoker = true) AS
        SELECT
            facility_id, county, department, shift,
            date_trunc('day', created_at) AS day,
            count(*) AS n,
            avg(fatigue)::numeric(5,2) AS avg_fatigue,
            avg(heat_exposure)::numeric(5,2) AS avg_heat,
            avg(risk_score)::numeric(5,1) AS avg_score,
            percentile_cont(0.9) WITHIN GROUP (ORDER BY risk_score)::numeric(5,1) AS p90_score,
            (count(*) FILTER (WHERE risk_level = 'Critical'))::numeric(4,2)
              / NULLIF(count(*), 0) AS critical_share
        FROM logs
        GROUP BY facility_id, county, department, shift, date_trunc('day', created_at)
        HAVING count(*) >= 5
    """)
    op.execute("GRANT SELECT ON agg_logs TO app_user")
    op.execute("GRANT SELECT ON agg_logs TO sentinel_admin")
    op.execute("ALTER TABLE fatigue_confirmations DROP COLUMN IF EXISTS log_id")
