from __future__ import annotations

import uuid
from datetime import date as date_type
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, Numeric, SmallInteger, String,
    Text, text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Log(Base):
    __tablename__ = "logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    facility_id: Mapped[str] = mapped_column(String(80), nullable=False)
    county: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="Unknown")
    worker_id_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    department: Mapped[str] = mapped_column(String(60), nullable=False)
    shift: Mapped[str] = mapped_column(String(8), nullable=False)
    fatigue: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    heat_exposure: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    hours_worked: Mapped[float] = mapped_column(Numeric(4, 1), nullable=False)
    symptoms: Mapped[list[str]] = mapped_column(
        ARRAY(String(40)), nullable=False, server_default=text("'{}'::varchar[]"))
    risk_score: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(12), nullable=False)
    components: Mapped[dict] = mapped_column(JSONB, nullable=False)
    client_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"))


class IdempotencyKey(Base):
    __tablename__ = "idempotency_ledger"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    facility_id: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False,
                                        server_default="in_progress")
    response: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UploadSession(Base):
    __tablename__ = "upload_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    facility_id: Mapped[str] = mapped_column(String(80), nullable=False)
    device_id: Mapped[str] = mapped_column(String(80), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"))
    pending_count: Mapped[int] = mapped_column(SmallInteger, nullable=False,
                                               server_default="0")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False,
                                            server_default=text("'{}'::jsonb"))


class AuditLog(Base):
    __tablename__ = "audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    facility_id: Mapped[str] = mapped_column(String(80), nullable=False)
    actor: Mapped[str] = mapped_column(String(80), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    resource: Mapped[str] = mapped_column(String(120), nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False,
                                         server_default=text("'{}'::jsonb"))
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    self_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AssistantConversation(Base):
    __tablename__ = "assistant_conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    facility_id: Mapped[str] = mapped_column(String(80), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    tool_results: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    engine: Mapped[str] = mapped_column(String(20), nullable=False)
    verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true")
    refusal_reason: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AssistantFeedback(Base):
    __tablename__ = "assistant_feedback"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    facility_id: Mapped[str] = mapped_column(String(80), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    correction: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"))


class RiskOutcome(Base):
    __tablename__ = "risk_outcomes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    facility_id: Mapped[str] = mapped_column(String(80), nullable=False)
    county: Mapped[str] = mapped_column(String(40), nullable=False)
    department: Mapped[str] = mapped_column(String(60), nullable=False)
    shift: Mapped[str] = mapped_column(String(8), nullable=False)
    day: Mapped[date_type] = mapped_column(Date, nullable=False)
    predicted_wvi: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False)
    predicted_level: Mapped[str] = mapped_column(String(12), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    recorded_by: Mapped[str | None] = mapped_column(String(36))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"))
