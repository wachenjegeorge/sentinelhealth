import hashlib, json
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import AuditLog


async def append_audit(session: AsyncSession, *, facility_id, actor, role,
                       action, resource, detail=None):
    last = await session.execute(
        select(AuditLog.self_hash).where(AuditLog.facility_id == facility_id)
        .order_by(AuditLog.id.desc()).limit(1))
    prev = last.scalar() or "0" * 64
    ts = datetime.now(timezone.utc).isoformat()
    canonical = json.dumps({"actor":actor,"role":role,"action":action,
                            "resource":resource,"detail":detail or {},"ts":ts},
                           sort_keys=True, separators=(",", ":"))
    h = hashlib.sha256((prev + canonical).encode()).hexdigest()
    session.add(AuditLog(facility_id=facility_id, actor=actor, role=role,
                         action=action, resource=resource, detail=detail or {},
                         prev_hash=prev, self_hash=h))
