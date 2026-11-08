"""Add detailed KEPH facility levels and department mappings.

Revision ID: 017_facility_levels
Revises: 016_department_heads
"""
from alembic import op

revision = "017_facility_levels"
down_revision = "016_department_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add KEPH sub-level and metadata (idempotent — columns may exist
    # from an earlier partial attempt)
    op.execute("""
        ALTER TABLE facilities
        ADD COLUMN IF NOT EXISTS keph_sub_level VARCHAR(20)
    """)
    op.execute("""
        ALTER TABLE facilities
        ADD COLUMN IF NOT EXISTS ownership VARCHAR(30)
            DEFAULT 'County Government'
    """)
    op.execute("""
        ALTER TABLE facilities
        ADD COLUMN IF NOT EXISTS mfl_code VARCHAR(20)
    """)

    # Index — also idempotent
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_facilities_county_level
        ON facilities(county, keph_level)
    """)

    # Backfill — safe: WHERE clause skips already-filled rows
    op.execute("""
        UPDATE facilities SET keph_sub_level =
            CASE keph_level
                WHEN 1 THEN 'CHU'
                WHEN 2 THEN 'Dispensary'
                WHEN 3 THEN 'Health Centre'
                WHEN 4 THEN 'Sub-County Hospital'
                WHEN 5 THEN 'County Referral'
                WHEN 6 THEN 'National Referral'
                ELSE 'Unknown'
            END
        WHERE keph_sub_level IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_facilities_county_level")
    op.execute("ALTER TABLE facilities DROP COLUMN IF EXISTS mfl_code")
    op.execute("ALTER TABLE facilities DROP COLUMN IF EXISTS ownership")
    op.execute("ALTER TABLE facilities DROP COLUMN IF EXISTS keph_sub_level")
