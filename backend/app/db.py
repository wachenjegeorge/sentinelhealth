"""Async engines + after_begin listener that drives RLS."""
from __future__ import annotations

import contextlib
from contextvars import ContextVar
from typing import AsyncIterator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.orm import Session

from app.config import settings

tenant_ctx: ContextVar[str | None] = ContextVar("tenant", default=None)
role_ctx: ContextVar[str | None] = ContextVar("role", default=None)
# NEW: Context variable for the user_id
user_ctx: ContextVar[str | None] = ContextVar("user", default=None)

app_engine = create_async_engine(
    settings.database_url,
    pool_size=settings.pool_size, max_overflow=settings.max_overflow,
    pool_pre_ping=True, future=True)
AppSession = async_sessionmaker(app_engine, expire_on_commit=False)

admin_engine = create_async_engine(
    settings.database_url_admin,
    pool_size=1, max_overflow=1, pool_pre_ping=True, future=True)
AdminSession = async_sessionmaker(admin_engine, expire_on_commit=False)

seed_engine = create_async_engine(
    settings.database_url_migration,
    pool_size=1, max_overflow=1, pool_pre_ping=True, future=True)
SeedSession = async_sessionmaker(seed_engine, expire_on_commit=False)


@event.listens_for(Session, "after_begin")
def _set_tenant(session, transaction, connection):
    facility = tenant_ctx.get()
    if facility is None:
        if connection.engine is app_engine.sync_engine:
            raise RuntimeError(
                "tenant_ctx not set for app-session transaction - "
                "wrap the session in with_tenant(facility_id)")
        return
    connection.execute(
        text("SELECT set_config('app.facility_id', :t, true)"),
        {"t": facility})
    
    role = role_ctx.get() or "worker"
    connection.execute(
        text("SELECT set_config('app.role', :r, true)"),
        {"r": role})
        
    # NEW: Set user_id if it exists
    user_id = user_ctx.get()
    if user_id:
        connection.execute(
            text("SELECT set_config('app.user_id', :u, true)"),
            {"u": user_id})


@contextlib.asynccontextmanager
async def with_tenant(facility_id: str, role: str = "worker", user_id: str = "") -> AsyncIterator[AsyncSession]:
    t = tenant_ctx.set(facility_id)
    r = role_ctx.set(role)
    u = user_ctx.set(user_id)  # NEW: Set the user_id
    try:
        async with AppSession() as session:
            async with session.begin():
                yield session
    finally:
        user_ctx.reset(u)  # NEW: Clean up
        role_ctx.reset(r)
        tenant_ctx.reset(t)
