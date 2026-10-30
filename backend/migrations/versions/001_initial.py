from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None

APP = "app_user"; ADM = "sentinel_admin"


def upgrade():
    op.create_table("logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", sa.String(80), nullable=False),
        sa.Column("worker_id_hash", sa.String(64), nullable=False),
        sa.Column("department", sa.String(60), nullable=False),
        sa.Column("shift", sa.String(8), nullable=False),
        sa.Column("fatigue", sa.SmallInteger, nullable=False),
        sa.Column("heat_exposure", sa.SmallInteger, nullable=False),
        sa.Column("hours_worked", sa.Numeric(4,1), nullable=False),
        sa.Column("symptoms", postgresql.ARRAY(sa.String(40)),
                  nullable=False, server_default=sa.text("'{}'::varchar[]")),
        sa.Column("risk_score", sa.Numeric(5,1), nullable=False),
        sa.Column("risk_level", sa.String(12), nullable=False),
        sa.Column("components", postgresql.JSONB, nullable=False),
        sa.Column("client_updated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("fatigue BETWEEN 1 AND 10", name="ck_logs_f"),
        sa.CheckConstraint("heat_exposure BETWEEN 1 AND 10", name="ck_logs_h"),
        sa.CheckConstraint("hours_worked BETWEEN 0 AND 24", name="ck_logs_hw"),
        sa.CheckConstraint("risk_score BETWEEN 0 AND 100", name="ck_logs_s"),
        sa.CheckConstraint("risk_level IN ('Low','Moderate','Critical')", name="ck_logs_l"),
        sa.CheckConstraint("shift IN ('day','night')", name="ck_logs_sh"))
    op.create_index("ix_logs_facility_created", "logs",
                    ["facility_id", sa.text("created_at DESC")])

    op.create_table("idempotency_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("facility_id", sa.String(80), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="in_progress"),
        sa.Column("response", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("key", name="uq_idem_key"),
        sa.CheckConstraint("status IN ('in_progress','completed','failed')", name="ck_idem"))

    op.create_table("upload_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", sa.String(80), nullable=False),
        sa.Column("device_id", sa.String(80), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("pending_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("metadata", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")))

    op.create_table("audit",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("facility_id", sa.String(80), nullable=False),
        sa.Column("actor", sa.String(80), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("resource", sa.String(120), nullable=False),
        sa.Column("detail", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("self_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")))

    op.execute("""
        CREATE VIEW agg_logs AS
        SELECT facility_id, department, shift,
               date_trunc('day', created_at) AS day,
               count(*) AS n,
               avg(fatigue)::numeric(5,2) AS avg_fatigue,
               avg(heat_exposure)::numeric(5,2) AS avg_heat,
               avg(risk_score)::numeric(5,1) AS avg_score,
               percentile_cont(0.9) WITHIN GROUP (ORDER BY risk_score)::numeric(5,1) AS p90_score,
               (count(*) FILTER (WHERE risk_level='Critical'))::numeric(4,2)
                 / NULLIF(count(*),0) AS critical_share
        FROM logs
        GROUP BY 1,2,3,4 HAVING count(*) >= 5
    """)

    op.execute(f"""DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{APP}') THEN
        CREATE ROLE {APP} LOGIN PASSWORD 'app-pw-changeme';
      END IF; END $$;""")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP}")
    op.execute(f"GRANT SELECT,INSERT,UPDATE,DELETE ON logs,idempotency_ledger,upload_sessions,audit TO {APP}")
    op.execute(f"GRANT SELECT ON agg_logs TO {APP}")

    for t in ("logs","idempotency_ledger","upload_sessions","audit"):
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        op.execute(f"""CREATE POLICY tenant_isolation ON {t}
          USING (facility_id = current_setting('app.facility_id', true))
          WITH CHECK (facility_id = current_setting('app.facility_id', true))""")

    op.execute(f"REVOKE UPDATE, DELETE ON audit FROM {APP}")

    op.execute(f"""DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{ADM}') THEN
        CREATE ROLE {ADM} LOGIN PASSWORD 'admin-pw-changeme' BYPASSRLS;
      END IF; END $$;""")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {ADM}")
    op.execute(f"GRANT SELECT ON agg_logs TO {ADM}")


def downgrade():
    op.execute("DROP VIEW IF EXISTS agg_logs")
    for t in ("audit","upload_sessions","idempotency_ledger","logs"):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
