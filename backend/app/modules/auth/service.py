"""Auth service - full RBAC hierarchy with approval workflow."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import hash_password, verify_password


@dataclass
class AuthResult:
    user_id: str
    username: str
    role: str
    facility_id: str
    county: Optional[str]
    verification_status: str


@dataclass
class UserProfile:
    id: str
    username: str
    role: str
    facility_id: str
    county: Optional[str]
    full_name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    occupation: Optional[str]
    primary_department: Optional[str]
    active: bool
    verification_status: str
    must_change_password: bool
    last_login_at: Optional[datetime]
    deleted_at: Optional[datetime]


# ── AUTHENTICATE ──────────────────────────────────────────────
async def authenticate(session: AsyncSession, username: str, password: str) -> AuthResult | None:
    row = (await session.execute(text("""
        SELECT u.id, u.username, u.password_hash, u.role, u.facility_id,
               u.active, u.verification_status, u.deleted_at, f.county
        FROM users u LEFT JOIN facilities f ON f.id = u.facility_id
        WHERE u.username = :u
    """), {"u": username})).mappings().first()

    if row is None or not row["active"] or row["deleted_at"]:
        return None
    if row["verification_status"] != "verified":
        return None  # Not approved yet
    if not verify_password(password, row["password_hash"]):
        return None

    await session.execute(text(
        "UPDATE users SET last_login_at = now() WHERE id = :id"),
        {"id": row["id"]})

    return AuthResult(
        user_id=row["id"], username=row["username"], role=row["role"],
        facility_id=row["facility_id"], county=row["county"],
        verification_status=row["verification_status"],
    )


# ── PROFILE ──────────────────────────────────────────────────
async def get_profile(session: AsyncSession, user_id: str) -> UserProfile | None:
    row = (await session.execute(text("""
        SELECT u.id, u.username, u.role, u.facility_id, u.full_name,
               u.email, u.phone, u.occupation, u.primary_department,
               u.active, u.verification_status, u.must_change_password,
               u.last_login_at, u.deleted_at, f.county
        FROM users u LEFT JOIN facilities f ON f.id = u.facility_id
        WHERE u.id = :id
    """), {"id": user_id})).mappings().first()
    if row is None:
        return None
    return UserProfile(**{k: row[k] for k in row.keys()})


async def update_profile(session: AsyncSession, user_id: str, **fields) -> None:
    """Only editable fields are whitelisted here."""
    allowed = {"full_name", "email", "phone", "primary_department", "occupation"}
    sets, params = [], {"id": user_id}
    for key, val in fields.items():
        if key in allowed and val is not None:
            sets.append(f"{key} = :{key}")
            params[key] = val
    if sets:
        await session.execute(
            text(f"UPDATE users SET {', '.join(sets)} WHERE id = :id"), params)


async def change_password(session: AsyncSession, user_id: str,
                          old_password: str, new_password: str) -> bool:
    row = (await session.execute(text(
        "SELECT password_hash FROM users WHERE id = :id"), {"id": user_id})).scalar()
    if row is None or not verify_password(old_password, row):
        return False
    await session.execute(text("""
        UPDATE users SET password_hash = :p, must_change_password = false
        WHERE id = :id
    """), {"p": hash_password(new_password), "id": user_id})
    return True


# ── REGISTRATION (each role has its own upline verifier) ─────
async def register_county_officer(session: AsyncSession, *,
    username: str, password: str, full_name: str, county: str,
    email: str, phone: str) -> str:
    """Officer is registered PENDING. Only ADMIN can verify."""
    if (await session.execute(text("SELECT 1 FROM users WHERE username = :u"),
            {"u": username})).scalar():
        raise ValueError("username already taken")

    # Attach officer to the county referral hospital of their county
    fac = (await session.execute(text("""
        SELECT id FROM facilities WHERE county = :c AND keph_level = 5 LIMIT 1
    """), {"c": county})).scalar()
    if fac is None:
        raise ValueError(f"No Level 5 hospital for county: {county}")

    user_id = str(uuid.uuid4())
    await session.execute(text("""
        INSERT INTO users
            (id, username, password_hash, role, facility_id, full_name,
             email, phone, active, verification_status)
        VALUES
            (:id, :u, :p, 'county_officer', :f, :n, :e, :ph, false, 'pending')
    """), {"id": user_id, "u": username, "p": hash_password(password),
           "f": fac, "n": full_name, "e": email, "ph": phone})
    return user_id


async def register_hospital_head(session: AsyncSession, *,
    username: str, password: str, full_name: str, occupation: str,
    phone: str, facility_id: str, created_by: str) -> str:
    """Created by County Officer. Verified by the same County Officer."""
    if (await session.execute(text("SELECT 1 FROM users WHERE username = :u"),
            {"u": username})).scalar():
        raise ValueError("username already taken")

    user_id = str(uuid.uuid4())
    await session.execute(text("""
        INSERT INTO users
            (id, username, password_hash, role, facility_id, full_name,
             phone, occupation, active, verification_status)
        VALUES
            (:id, :u, :p, 'hospital_head', :f, :n, :ph, :o, false, 'pending')
    """), {"id": user_id, "u": username, "p": hash_password(password),
           "f": facility_id, "n": full_name, "ph": phone, "o": occupation})
    return user_id


async def register_worker(session: AsyncSession, *,
    username: str, password: str, full_name: str, occupation: str,
    phone: str, facility_id: str, primary_department: str,
    created_by: str) -> str:
    """Created by Hospital Head. Verified by the same Hospital Head."""
    if (await session.execute(text("SELECT 1 FROM users WHERE username = :u"),
            {"u": username})).scalar():
        raise ValueError("username already taken")

    user_id = str(uuid.uuid4())
    await session.execute(text("""
        INSERT INTO users
            (id, username, password_hash, role, facility_id, full_name,
             phone, occupation, primary_department, active, verification_status)
        VALUES
            (:id, :u, :p, 'worker', :f, :n, :ph, :o, :d, false, 'pending')
    """), {"id": user_id, "u": username, "p": hash_password(password),
           "f": facility_id, "n": full_name, "ph": phone,
           "o": occupation, "d": primary_department})
    return user_id


# ── VERIFICATION (approval workflow) ─────────────────────────
async def verify_user(session: AsyncSession, user_id: str,
                      verifier_id: str, approve: bool) -> None:
    status = "verified" if approve else "rejected"
    await session.execute(text("""
        UPDATE users
        SET verification_status = :s,
            active = :a,
            approved_at = CASE WHEN :a THEN now() ELSE approved_at END,
            approved_by = :by
        WHERE id = :id AND verification_status = 'pending'
    """), {"s": status, "a": approve, "by": verifier_id, "id": user_id})


async def list_pending_officers(session: AsyncSession) -> list[dict]:
    """For admin: list officers waiting for national approval."""
    rows = (await session.execute(text("""
        SELECT u.id, u.username, u.full_name, u.email, u.phone,
               f.county, u.created_at
        FROM users u JOIN facilities f ON f.id = u.facility_id
        WHERE u.role = 'county_officer' AND u.verification_status = 'pending'
        ORDER BY u.created_at DESC
    """))).mappings().all()
    return [dict(r) | {"created_at": r["created_at"].isoformat()} for r in rows]


async def list_pending_for_officer(session: AsyncSession, county: str) -> list[dict]:
    """For officer: hospital heads waiting for their approval."""
    rows = (await session.execute(text("""
        SELECT u.id, u.username, u.full_name, u.occupation, u.phone,
               f.name AS facility_name, u.created_at
        FROM users u JOIN facilities f ON f.id = u.facility_id
        WHERE u.role = 'hospital_head' AND u.verification_status = 'pending'
          AND f.county = :c
        ORDER BY u.created_at DESC
    """), {"c": county})).mappings().all()
    return [dict(r) | {"created_at": r["created_at"].isoformat()} for r in rows]


async def list_pending_for_head(session: AsyncSession, facility_id: str) -> list[dict]:
    """For hospital head: workers waiting for their approval."""
    rows = (await session.execute(text("""
        SELECT id, username, full_name, occupation, phone,
               primary_department, created_at
        FROM users
        WHERE role = 'worker' AND verification_status = 'pending'
          AND facility_id = :f
        ORDER BY created_at DESC
    """), {"f": facility_id})).mappings().all()
    return [dict(r) | {"created_at": r["created_at"].isoformat()} for r in rows]


# ── ACCOUNT DELETION (soft delete + PII purge) ──────────────
async def request_deletion(session: AsyncSession, user_id: str, reason: str) -> None:
    """User requests their account be deleted. Soft-deleted immediately; PII purged."""
    await session.execute(text("""
        UPDATE users
        SET deleted_at = now(),
            active = false,
            deletion_reason = :r,
            email = NULL,
            phone = NULL,
            full_name = NULL
        WHERE id = :id
    """), {"r": reason, "id": user_id})


async def purge_deleted_user(session: AsyncSession, user_id: str) -> None:
    """Admin hard-deletes after retention period (30 days). Removes all PII."""
    await session.execute(text("DELETE FROM users WHERE id = :id AND deleted_at IS NOT NULL"),
                          {"id": user_id})


# ── GOOGLE SIGN-IN (stub — configure OAuth credentials) ──────
async def find_or_link_google_user(session: AsyncSession, google_sub: str,
                                    email: str) -> AuthResult | None:
    """Look up a user by google_sub, or by email if a matching account exists."""
    row = (await session.execute(text("""
        SELECT u.id, u.username, u.role, u.facility_id, u.verification_status,
               u.active, f.county
        FROM users u LEFT JOIN facilities f ON f.id = u.facility_id
        WHERE u.google_sub = :g OR (u.email = :e AND u.google_sub IS NULL)
        LIMIT 1
    """), {"g": google_sub, "e": email})).mappings().first()

    if row is None or not row["active"]:
        return None
    if row["verification_status"] != "verified":
        return None

    # Link the google_sub for future sign-ins
    await session.execute(text("UPDATE users SET google_sub = :g WHERE id = :id"),
                          {"g": google_sub, "id": row["id"]})

    return AuthResult(
        user_id=row["id"], username=row["username"], role=row["role"],
        facility_id=row["facility_id"], county=row["county"],
        verification_status=row["verification_status"],
    )
