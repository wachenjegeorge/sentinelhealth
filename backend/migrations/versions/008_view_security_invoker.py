"""Recreate agg_logs with security_invoker so caller's RLS applies.

Views in PostgreSQL execute with the OWNER's privileges by default.
The view was created by `sentinel` (superuser), so every query against
agg_logs ran as superuser and bypassed FORCE ROW LEVEL SECURITY on logs.
The result: any officer saw every county's data.

security_invoker = true forces the view to execute as the CALLER, so
app_user's RLS policy on logs is evaluated and county scoping works.
"""
from alembic import op

revision = "008_view_security_invoker"
down_revision = "006_users_grant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS agg_logs")
    op.execute("""
        CREATE VIEW agg_logs
        WITH (security_invoker = true) AS
        SELECT
            county, department, shift,
            date_trunc('day', created_at) AS day,
            count(*)                                          AS n,
            avg(fatigue)::numeric(5,2)                        AS avg_fatigue,
            avg(heat_exposure)::numeric(5,2)                  AS avg_heat,
            avg(risk_score)::numeric(5,1)                     AS avg_score,
            percentile_cont(0.9) WITHIN GROUP (ORDER BY risk_score)::numeric(5,1)
                                                              AS p90_score,
            (count(*) FILTER (WHERE risk_level = 'Critical'))::numeric(4,2)
              / NULLIF(count(*), 0)                           AS critical_share
        FROM logs
        GROUP BY county, department, shift, date_trunc('day', created_at)
        HAVING count(*) >= 5
    """)
    op.execute("GRANT SELECT ON agg_logs TO app_user")
    op.execute("GRANT SELECT ON agg_logs TO sentinel_admin")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS agg_logs")
