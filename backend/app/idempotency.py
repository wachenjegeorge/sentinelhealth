import asyncio, json
import asyncpg
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

MAX = 3


async def with_idempotency(session: AsyncSession, *, key, facility_id, work):
    assert session.in_transaction()
    claim = await session.execute(text("""
        INSERT INTO idempotency_ledger (key, facility_id, status)
        VALUES (:k, :f, 'in_progress')
        ON CONFLICT (key) DO NOTHING RETURNING id
    """), {"k": key, "f": facility_id})
    claimed = claim.first() is not None

    if not claimed:
        row = (await session.execute(
            text("SELECT status, response FROM idempotency_ledger WHERE key=:k"),
            {"k": key})).one()
        status, stored = row
        if status == "completed":
            return json.loads(stored) if isinstance(stored, str) else stored
        if status == "failed":
            await session.execute(
                text("UPDATE idempotency_ledger SET status='in_progress' WHERE key=:k"),
                {"k": key})
        else:
            raise HTTPException(409, "already in progress")

    result = await work(session)
    await session.execute(text("""
        UPDATE idempotency_ledger SET status='completed', response=:r,
        completed_at=now() WHERE key=:k
    """), {"r": json.dumps(result), "k": key})
    return result


async def run_with_serializable_retry(factory):
    for attempt in range(MAX):
        try:
            return await factory()
        except DBAPIError as exc:
            orig = getattr(exc, "orig", None)
            if isinstance(orig, asyncpg.PostgresError) and orig.sqlstate == "40001":
                if attempt == MAX - 1:
                    raise
                await asyncio.sleep(0.05 * (2 ** attempt))
                continue
            raise
    raise RuntimeError("retries exhausted")
