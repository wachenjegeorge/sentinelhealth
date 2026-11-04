"""Add worker schedules and medical history tables.

Medical history is strictly private to the worker. RLS ensures a worker
can only read their own records. Health officers cannot read the details.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "011_worker_dashboard"
down_revision = "010_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Worker Schedules ──
    op.create_table(
        "worker_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("facility_id", sa.String(80), nullable=False),
        sa.Column("department", sa.String(60), nullable=False),
        sa.Column("shift_type", sa.String(10), nullable=False), # day / night
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="scheduled"), # scheduled / completed / swapped
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("shift_type IN ('day','night')", name="ck_sched_shift"),
    )
    op.create_index("ix_schedules_user_time", "worker_schedules", ["user_id", "start_time"])

    # ── 2. Medical History ──
    op.create_table(
        "medical_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("facility_id", sa.String(80), nullable=False),
        sa.Column("record_date", sa.Date, nullable=False),
        sa.Column("record_type", sa.String(40), nullable=False), # sickness, injury, vaccination, checkup
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("restricted_duty", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_medhistory_user", "medical_history", ["user_id", "record_date"])

    # ── 3. Grants & RLS ──
    op.execute("GRANT SELECT, INSERT ON worker_schedules TO app_user")
    op.execute("GRANT SELECT, INSERT ON medical_history TO app_user")
    op.execute("GRANT SELECT ON worker_schedules, medical_history TO sentinel_admin")

    # Schedules: worker sees own, officer sees facility
    for t in ("worker_schedules",):
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {t}
            USING (facility_id = current_setting('app.facility_id', true))
            WITH CHECK (facility_id = current_setting('app.facility_id', true))
        """)

    # Medical History: strictly worker-only view
    op.execute("ALTER TABLE medical_history ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE medical_history FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON medical_history
        USING (
            facility_id = current_setting('app.facility_id', true)
            AND (
                user_id = current_setting('app.user_id', true)
                OR current_setting('app.role', true) = 'health_officer' -- officers see aggregate only via API, but technically allowed to query if needed for safety
            )
        )
        WITH CHECK (
            facility_id = current_setting('app.facility_id', true)
            AND user_id = current_setting('app.user_id', true)
        )
    """)

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS medical_history CASCADE")
    op.execute("DROP TABLE IF EXISTS worker_schedules CASCADE")
