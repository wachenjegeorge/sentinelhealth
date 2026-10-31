"""Real facilities registry and real user accounts."""
from alembic import op
import sqlalchemy as sa


revision = "005_facilities_users"
down_revision = "004_view_county"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "facilities",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("county", sa.String(40), nullable=False, index=True),
        sa.Column("sub_county", sa.String(80), nullable=True),
        sa.Column("keph_level", sa.SmallInteger, nullable=False),
        sa.Column("facility_type", sa.String(60), nullable=False),
        sa.Column("mfl_code", sa.String(20), nullable=True, unique=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_facilities_county_level",
                    "facilities", ["county", "keph_level"])

    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True,
                  server_default=sa.text("gen_random_uuid()::text")),
        sa.Column("username", sa.String(60), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("facility_id", sa.String(80), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("role IN ('worker','health_officer','admin')",
                           name="ck_users_role"),
    )
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_facility", "users", ["facility_id"])

    op.create_foreign_key(
        "fk_users_facility", "users", "facilities",
        ["facility_id"], ["id"], ondelete="RESTRICT",
    )

    # Wipe old test data. TRUNCATE is table-level and bypasses FORCE RLS.
    op.execute("TRUNCATE TABLE audit, idempotency_ledger, logs")

    # FK: logs.facility_id -> facilities.id
    op.create_foreign_key(
        "fk_logs_facility", "logs", "facilities",
        ["facility_id"], ["id"], ondelete="RESTRICT",
    )

    # Grants — app_user needs SELECT on facilities (RLS subquery + login page)
    op.execute("GRANT SELECT ON facilities TO app_user")
    op.execute("GRANT SELECT ON facilities TO sentinel_admin")
    # Column-level on users: only auth fields visible to app_user
    op.execute("GRANT SELECT (id, username, password_hash, role, facility_id, active) "
               "ON users TO app_user")
    # No INSERT/UPDATE/DELETE for app_user on users. Superuser only.

    # Role-based RLS on logs so officers see their county, workers see their facility
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON logs")
    op.execute("""
        CREATE POLICY tenant_isolation ON logs
        USING (
          (
            current_setting('app.role', true) = 'health_officer'
            AND county = (
              SELECT f.county FROM facilities f
              WHERE f.id = current_setting('app.facility_id', true)
            )
          )
          OR (
            coalesce(current_setting('app.role', true), '') <> 'health_officer'
            AND facility_id = current_setting('app.facility_id', true)
          )
        )
        WITH CHECK (facility_id = current_setting('app.facility_id', true))
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON logs")
    op.execute("ALTER TABLE logs DROP CONSTRAINT IF EXISTS fk_logs_facility")
    op.drop_table("users")
    op.drop_table("facilities")
