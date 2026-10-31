"""Recreate agg_logs with county. k-anonymity stays in SQL."""
from alembic import op

revision = "004_view_county"
down_revision = "003_county"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS agg_logs")
    op.execute("""
        CREATE VIEW agg_logs AS
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
