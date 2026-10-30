"""Async engines + the after_begin listener that drives RLS."""
from __future__ import annotations

import contextlib
from contextvars import ContextVar
from typing import AsyncIterator

from sqlalchemy import event, text
from sqlalchemy.orm import Session
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.orm import Session

from app.config import settings

tenant_ctx: ContextVar[str | None] = ContextVar("tenant", default=None)

app_engine = create_async_engine(
    settings.database_url,
    pool_size=settings.pool_size,
    max_overflow=settings.max_overflow,
    pool_pre_ping=True,
    future=True,
)
AppSession = async_sessionmaker(app_engine, expire_on_commit=False)

admin_engine = create_async_engine(
    settings.database_url_admin,
    pool_size=1,
    max_overflow=1,
    pool_pre_ping=True,
    future=True,
)
AdminSession = async_sessionmaker(admin_engine, expire_on_commit=False)


@event.listens_for(Session, "after_begin")
def _set_tenant(session, transaction, connection):
    facility = tenant_ctx.get()
    if facility is None:
        # App engine sessions MUST have a tenant set; admin sessions
        # (aggregator, audit reads) legitimately do not.
        if connection.engine is app_engine.sync_engine:
            raise RuntimeError(
                "tenant_ctx not set for app-session transaction - "
                "wrap the session in with_tenant(facility_id)"
            )
        return
    connection.execute(
        text("SELECT set_config('app.facility_id', :t, true)"),
        {"t": facility},
    )


@contextlib.asynccontextmanager
async def with_tenant(facility_id: str) -> AsyncIterator[AsyncSession]:
    token = tenant_ctx.set(facility_id)
    try:
        async with AppSession() as session:
            async with session.begin():
                yield session
    finally:
        tenant_ctx.reset(token)
