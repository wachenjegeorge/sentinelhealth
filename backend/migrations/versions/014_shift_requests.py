"""Add shift_requests table for worker-initiated schedule changes."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "014_shift_requests"
down_revision = "013_wearables"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "shift_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("facility_id", sa.String(80), nullable=False),
        sa.Column("schedule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_type", sa.String(20), nullable=False), # swap, leave, sick
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"), # pending, approved, rejected
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_shift_req_facility", "shift_requests", ["facility_id", "status"])

    op.execute("GRANT SELECT, INSERT ON shift_requests TO app_user")
    op.execute("GRANT SELECT, UPDATE ON shift_requests TO sentinel_admin")
    op.execute("ALTER TABLE shift_requests ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE shift_requests FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON shift_requests
        USING (facility_id = current_setting('app.facility_id', true))
        WITH CHECK (facility_id = current_setting('app.facility_id', true))
    """)

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS shift_requests CASCADE")
