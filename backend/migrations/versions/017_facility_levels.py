"""Add detailed KEPH facility levels and department mappings."""
from alembic import op
import sqlalchemy as sa

revision = "017_facility_levels"
down_revision = "016_department_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add KEPH sub-level for detailed classification
    op.add_column("facilities", sa.Column("keph_sub_level", sa.String(20), nullable=True))
    op.add_column("facilities", sa.Column("ownership", sa.String(30), nullable=True,
                                          server_default="County Government"))
    op.add_column("facilities", sa.Column("mfl_code", sa.String(20), nullable=True))

    # Index for fast lookup by level
    op.create_index("ix_facilities_county_level", "facilities",
                    ["county", "keph_level"])

    # Update existing facilities with a sub-level based on their current level
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
    op.drop_index("ix_facilities_county_level", table_name="facilities")
    op.drop_column("facilities", "mfl_code")
    op.drop_column("facilities", "ownership")
    op.drop_column("facilities", "keph_sub_level")
