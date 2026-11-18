"""Cognitive wellness: CWI columns, cognitive_confirmations, agg_cognitive_logs view.

Revision ID: 022_cognitive
Revises: 021_recommendations
"""
from alembic import op

revision = "022_cognitive"
down_revision = "021_recommendations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE logs ADD COLUMN IF NOT EXISTS cognitive_fatigue SMALLINT")
    op.execute("ALTER TABLE logs ADD COLUMN IF NOT EXISTS mental_clarity SMALLINT")
    op.execute("ALTER TABLE logs ADD COLUMN IF NOT EXISTS stress SMALLINT")
    op.execute("ALTER TABLE logs ADD COLUMN IF NOT EXISTS sleep_quality SMALLINT")
    op.execute("ALTER TABLE logs ADD COLUMN IF NOT EXISTS sleep_hours NUMERIC(4,1)")
    op.execute("ALTER TABLE logs ADD COLUMN IF NOT EXISTS cwi NUMERIC(5,1)")
    op.execute("ALTER TABLE logs ADD COLUMN IF NOT EXISTS cwi_level VARCHAR(12)")
    op.execute("ALTER TABLE logs ADD COLUMN IF NOT EXISTS cognitive_components JSONB")

    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_logs_cf') THEN
                ALTER TABLE logs ADD CONSTRAINT ck_logs_cf
                    CHECK (cognitive_fatigue IS NULL OR cognitive_fatigue BETWEEN 1 AND 10);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_logs_mc') THEN
                ALTER TABLE logs ADD CONSTRAINT ck_logs_mc
                    CHECK (mental_clarity IS NULL OR mental_clarity BETWEEN 1 AND 10);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_logs_st') THEN
                ALTER TABLE logs ADD CONSTRAINT ck_logs_st
                    CHECK (stress IS NULL OR stress BETWEEN 1 AND 10);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_logs_sq') THEN
                ALTER TABLE logs ADD CONSTRAINT ck_logs_sq
                    CHECK (sleep_quality IS NULL OR sleep_quality BETWEEN 1 AND 5);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_logs_sh') THEN
                ALTER TABLE logs ADD CONSTRAINT ck_logs_sh
                    CHECK (sleep_hours IS NULL OR sleep_hours BETWEEN 0 AND 12);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_logs_cwi') THEN
                ALTER TABLE logs ADD CONSTRAINT ck_logs_cwi
                    CHECK (cwi IS NULL OR cwi BETWEEN 0 AND 100);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_logs_cwi_lvl') THEN
                ALTER TABLE logs ADD CONSTRAINT ck_logs_cwi_lvl
                    CHECK (cwi_level IS NULL OR cwi_level IN ('Low','Moderate','Critical'));
            END IF;
        END $$;
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_logs_cwi_worker
        ON logs(worker_id_hash, created_at DESC)
        WHERE cwi IS NOT NULL
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS cognitive_confirmations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            log_id UUID REFERENCES logs(id) ON DELETE CASCADE,
            facility_id VARCHAR(80) NOT NULL,
            department VARCHAR(60) NOT NULL,
            worker_id_hash VARCHAR(64) NOT NULL,
            worker_username VARCHAR(60) NOT NULL,
            cwi NUMERIC(5,1) NOT NULL,
            cwi_level VARCHAR(12) NOT NULL,
            cognitive_fatigue SMALLINT,
            mental_clarity SMALLINT,
            stress SMALLINT,
            sleep_quality SMALLINT,
            sleep_hours NUMERIC(4,1),
            components JSONB,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            confirmed_by VARCHAR(36),
            confirmed_at TIMESTAMPTZ,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_cc_status CHECK (status IN ('pending','confirmed','denied'))
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_cc_facility_dept
        ON cognitive_confirmations(facility_id, department, status)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_cc_created
        ON cognitive_confirmations(created_at DESC)
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE ON cognitive_confirmations TO app_user")
    op.execute("GRANT SELECT ON cognitive_confirmations TO sentinel_admin")
    op.execute("ALTER TABLE cognitive_confirmations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE cognitive_confirmations FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON cognitive_confirmations
        USING (
            facility_id = current_setting('app.facility_id', true)
            AND current_setting('app.role', true) IN
                ('department_head','hospital_head','county_officer','admin')
        )
        WITH CHECK (facility_id = current_setting('app.facility_id', true))
    """)

    op.execute("DROP VIEW IF EXISTS agg_cognitive_logs CASCADE")
    op.execute("""
        CREATE VIEW agg_cognitive_logs
        WITH (security_invoker = true) AS
        SELECT
            facility_id,
            county,
            department,
            shift,
            date_trunc('day', created_at) AS day,
            count(*) AS n,
            avg(cognitive_fatigue)::numeric(5,2) AS avg_cognitive_fatigue,
            avg(mental_clarity)::numeric(5,2) AS avg_mental_clarity,
            avg(stress)::numeric(5,2) AS avg_stress,
            avg(sleep_quality)::numeric(5,2) AS avg_sleep_quality,
            avg(sleep_hours)::numeric(5,2) AS avg_sleep_hours,
            avg(cwi)::numeric(5,1) AS avg_cwi,
            percentile_cont(0.9) WITHIN GROUP (ORDER BY cwi)::numeric(5,1) AS p90_cwi,
            (count(*) FILTER (WHERE cwi_level = 'Critical'))::numeric(4,2)
              / NULLIF(count(*), 0) AS critical_cwi_share
        FROM logs
        WHERE cwi IS NOT NULL
          AND verification_status IN ('confirmed', 'auto_verified')
        GROUP BY facility_id, county, department, shift, date_trunc('day', created_at)
        HAVING count(*) >= 5
    """)
    op.execute("GRANT SELECT ON agg_cognitive_logs TO app_user")
    op.execute("GRANT SELECT ON agg_cognitive_logs TO sentinel_admin")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS agg_cognitive_logs CASCADE")
    op.execute("DROP TABLE IF EXISTS cognitive_confirmations CASCADE")
    for col in ("cognitive_fatigue","mental_clarity","stress","sleep_quality",
                "sleep_hours","cwi","cwi_level","cognitive_components"):
        op.execute(f"ALTER TABLE logs DROP COLUMN IF EXISTS {col}")
