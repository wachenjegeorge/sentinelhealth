"""Assistant conversations, messages, feedback, and risk outcomes.

The improvement loop is here: risk_outcomes captures whether an alert
was followed by an intervention. That is the label the risk engine
learns from. assistant_feedback captures officer ratings for KB tuning.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "009_assistant"
down_revision = "008_view_security_invoker"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", sa.String(80), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_conv_facility_created", "assistant_conversations",
                    ["facility_id", sa.text("created_at DESC")])

    op.create_table(
        "assistant_messages",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("role", sa.String(20), nullable=False),  # user|assistant|tool
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("tool_calls", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("tool_results", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("engine", sa.String(20), nullable=False),   # deterministic|ollama
        sa.Column("verified", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("refusal_reason", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_msg_conv", "assistant_messages", ["conversation_id"])

    op.create_table(
        "assistant_feedback",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("message_id", sa.BigInteger,
                  sa.ForeignKey("assistant_messages.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("facility_id", sa.String(80), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("rating", sa.SmallInteger, nullable=False),  # 1..5
        sa.Column("correction", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_fb_rating"),
    )
    op.create_index("ix_fb_facility", "assistant_feedback",
                    ["facility_id", sa.text("created_at DESC")])

    # The label the risk engine learns from.
    op.create_table(
        "risk_outcomes",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("facility_id", sa.String(80), nullable=False),
        sa.Column("county", sa.String(40), nullable=False),
        sa.Column("department", sa.String(60), nullable=False),
        sa.Column("shift", sa.String(8), nullable=False),
        sa.Column("day", sa.Date, nullable=False),
        sa.Column("predicted_wvi", sa.Numeric(5, 1), nullable=False),
        sa.Column("predicted_level", sa.String(12), nullable=False),
        # Outcome: was there an actual adverse event or intervention?
        sa.Column("outcome", sa.String(20), nullable=False),
        # 'intervention' | 'adverse_event' | 'no_event' | 'unknown'
        sa.Column("recorded_by", sa.String(36), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "outcome IN ('intervention','adverse_event','no_event','unknown')",
            name="ck_outcome"),
    )
    op.create_index("ix_outcome_county_dept_day", "risk_outcomes",
                    ["county", "department", "day"])

    # Grants
    op.execute("GRANT SELECT, INSERT ON assistant_conversations, assistant_messages, "
               "assistant_feedback TO app_user")
    op.execute("GRANT SELECT, INSERT ON risk_outcomes TO app_user")
    op.execute("GRANT SELECT ON assistant_conversations, assistant_messages, "
               "assistant_feedback, risk_outcomes TO sentinel_admin")
    op.execute("GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO app_user")

    # RLS - same tenant rule as logs
    for t in ("assistant_conversations", "assistant_messages",
              "assistant_feedback", "risk_outcomes"):
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        if t == "assistant_messages":
            op.execute(f"""
                CREATE POLICY tenant_isolation ON {t}
                USING (conversation_id IN (
                    SELECT id FROM assistant_conversations
                    WHERE facility_id = current_setting('app.facility_id', true)))
                WITH CHECK (conversation_id IN (
                    SELECT id FROM assistant_conversations
                    WHERE facility_id = current_setting('app.facility_id', true)))
            """)
        elif t == "assistant_feedback":
            op.execute(f"""
                CREATE POLICY tenant_isolation ON {t}
                USING (facility_id = current_setting('app.facility_id', true))
                WITH CHECK (facility_id = current_setting('app.facility_id', true))
            """)
        else:
            op.execute(f"""
                CREATE POLICY tenant_isolation ON {t}
                USING (facility_id = current_setting('app.facility_id', true))
                WITH CHECK (facility_id = current_setting('app.facility_id', true))
            """)


def downgrade() -> None:
    for t in ("risk_outcomes", "assistant_feedback",
              "assistant_messages", "assistant_conversations"):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
