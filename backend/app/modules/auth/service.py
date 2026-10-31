"""Auth service - the ONLY reader of the users table.

Login handler uses `sentinel_admin` (BYPASSRLS) because at login time
there is no tenant context yet. Users table has no RLS by design -
column-level grants prevent app_user from seeing fields it does not need.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import verify_password


@dataclass
class AuthResult:
    user_id: str
    username: str
    role: str
    facility_id: str


async def authenticate(
    session: AsyncSession, username: str, password: str
) -> AuthResult | None:
    row = (await session.execute(text("""
        SELECT id, username, password_hash, role, facility_id, active
        FROM users WHERE username = :u
    """), {"u": username})).mappings().first()

    if row is None or not row["active"]:
        return None
    if not verify_password(password, row["password_hash"]):
        return None

    return AuthResult(
        user_id=row["id"], username=row["username"],
        role=row["role"], facility_id=row["facility_id"],
    )
