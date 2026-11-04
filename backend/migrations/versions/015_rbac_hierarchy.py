"""Production RBAC: 4 roles, hierarchical approval, account deletion."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "015_rbac_hierarchy"
down_revision = "014_shift_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Extend users table ──────────────────────────────────────
    op.add_column("users", sa.Column("occupation", sa.String(80), nullable=True))
    op.add_column("users", sa.Column("google_sub", sa.String(120), nullable=True, unique=True))
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("deletion_reason", sa.Text, nullable=True))
    op.add_column("users", sa.Column("verification_status", sa.String(20),
                                     nullable=False, server_default="pending"))
    op.add_column("users", sa.Column("verification_notes", sa.Text, nullable=True))

    # Expand role constraint (drop old, add new)
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role")
    op.execute("""
        ALTER TABLE users ADD CONSTRAINT ck_users_role
        CHECK (role IN ('admin','county_officer','hospital_head','department_head','worker','health_officer'))
    """)
    # health_officer kept for backward compat — treated as county_officer

    # verification_status check
    op.execute("""
        ALTER TABLE users ADD CONSTRAINT ck_users_verification
        CHECK (verification_status IN ('pending','verified','rejected'))
    """)

    # ── 2. Recreate agg_logs to include facility_id (needed for hospital_head) ──
    op.execute("DROP VIEW IF EXISTS agg_logs")
    op.execute("""
        CREATE VIEW agg_logs
        WITH (security_invoker = true) AS
        SELECT
            facility_id,
            county,
            department,
            shift,
            date_trunc('day', created_at) AS day,
            count(*)                                          AS n,
            avg(fatigue)::numeric(5,2)                        AS avg_fatigue,
            avg(heat_exposure)::numeric(5,2)                  AS avg_heat,
            avg(risk_score)::numeric(5,1)                     AS avg_score,
            percentile_cont(0.9) WITHIN GROUP (ORDER BY risk_score)::numeric(5,1) AS p90_score,
            (count(*) FILTER (WHERE risk_level = 'Critical'))::numeric(4,2)
              / NULLIF(count(*), 0)                           AS critical_share
        FROM logs
        GROUP BY facility_id, county, department, shift, date_trunc('day', created_at)
        HAVING count(*) >= 5
    """)
    op.execute("GRANT SELECT ON agg_logs TO app_user")
    op.execute("GRANT SELECT ON agg_logs TO sentinel_admin")

    # ── 3. Recreate RLS on logs to be role-aware ────────────────────
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON logs")
    op.execute("""
        CREATE POLICY tenant_isolation ON logs
        USING (
          -- County Officer: sees all logs in their county
          (current_setting('app.role', true) IN ('county_officer','health_officer')
            AND county = (
              SELECT f.county FROM facilities f
              WHERE f.id = current_setting('app.facility_id', true)
            ))
          -- Hospital Head / Department Head / Worker: sees their facility only
          OR (current_setting('app.role', true) IN ('hospital_head','department_head','worker')
            AND facility_id = current_setting('app.facility_id', true))
        )
        WITH CHECK (facility_id = current_setting('app.facility_id', true))
    """)

    # ── 4. Grant sentinel_admin (DB role) can do everything for admin path ──
    op.execute("""
        GRANT SELECT ON logs, users, facilities, idempotency_ledger,
                        upload_sessions, audit, assistant_conversations,
                        assistant_messages, assistant_feedback, risk_outcomes,
                        worker_schedules, medical_history, wearable_metrics,
                        autonomous_alerts, shift_requests
        TO sentinel_admin
    """)

    # ── 5. Add index for verification queries ──
    op.create_index("ix_users_verification_status", "users",
                    ["verification_status", "facility_id"])


def downgrade() -> None:
    op.drop_index("ix_users_verification_status", table_name="users")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON logs")
    op.execute("""
        CREATE POLICY tenant_isolation ON logs
        USING (
          (current_setting('app.role', true) = 'health_officer'
            AND county = (SELECT f.county FROM facilities f
                          WHERE f.id = current_setting('app.facility_id', true)))
          OR (coalesce(current_setting('app.role', true), '') <> 'health_officer'
            AND facility_id = current_setting('app.facility_id', true))
        )
        WITH CHECK (facility_id = current_setting('app.facility_id', true))
    """)
    op.execute("""
        ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_verification
    """)
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role")
    op.execute("""
        ALTER TABLE users ADD CONSTRAINT ck_users_role
        CHECK (role IN ('worker','health_officer','admin'))
    """)
    for c in ("verification_notes", "verification_status", "deletion_reason",
              "deleted_at", "google_sub", "occupation"):
        op.drop_column("users", c)
