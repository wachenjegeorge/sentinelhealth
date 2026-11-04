"""Create the national super-admin account.

═══════════════════════════════════════════════════════════════
⚠️  SENTINEL ADMIN PASSWORD — CHANGE BEFORE PRODUCTION
    This is the ONLY account with national scope. Its credentials
    must be stored in a password manager, not in code, in prod.
    Override via env: SENTINEL_ADMIN_PASSWORD=...
═══════════════════════════════════════════════════════════════
"""
import asyncio
import os
import uuid

from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import admin_engine

# ──────────────────────────────────────────────────────────────
# ★ ADMIN CREDENTIALS — CHANGE THIS LINE ↓
# ──────────────────────────────────────────────────────────────
SENTINEL_ADMIN_USERNAME = "sentinel"
SENTINEL_ADMIN_PASSWORD = os.getenv("SENTINEL_ADMIN_PASSWORD", "SentinelHealth#2026!")
SENTINEL_ADMIN_EMAIL    = "admin@sentinelhealth.ke"
SENTINEL_ADMIN_PHONE    = "+254700000000"
# ──────────────────────────────────────────────────────────────


async def seed() -> None:
    """Create SENTINEL admin if it does not already exist."""
    async with admin_engine.begin() as conn:
        existing = (await conn.execute(
            text("SELECT id FROM users WHERE username = :u"),
            {"u": SENTINEL_ADMIN_USERNAME},
        )).scalar()

        if existing:
            print(f"Admin '{SENTINEL_ADMIN_USERNAME}' already exists.")
            print(f"Username: {SENTINEL_ADMIN_USERNAME}")
            print(f"Password: (use the password you set previously)")
            return

        # Admin is attached to the first facility only because facility_id
        # is NOT NULL on the users table. Admin ignores facility scope via
        # the AdminSession path (bypasses RLS).
        any_fac = (await conn.execute(
            text("SELECT id FROM facilities LIMIT 1")
        )).scalar()
        if any_fac is None:
            raise RuntimeError("No facilities found. Run seed_facilities.py first.")

        await conn.execute(text("""
            INSERT INTO users
                (id, username, password_hash, role, facility_id,
                 full_name, email, phone, active, verification_status,
                 must_change_password)
            VALUES
                (:id, :u, :p, 'admin', :f,
                 'Sentinel National Admin', :e, :ph, true, 'verified',
                 false)
        """), {
            "id": str(uuid.uuid4()),
            "u": SENTINEL_ADMIN_USERNAME,
            "p": hash_password(SENTINEL_ADMIN_PASSWORD),
            "f": any_fac,
            "e": SENTINEL_ADMIN_EMAIL,
            "ph": SENTINEL_ADMIN_PHONE,
        })

        print("═══════════════════════════════════════════════════")
        print("  ADMIN ACCOUNT CREATED")
        print("═══════════════════════════════════════════════════")
        print(f"  Username: {SENTINEL_ADMIN_USERNAME}")
        print(f"  Password: {SENTINEL_ADMIN_PASSWORD}")
        print(f"  Email:    {SENTINEL_ADMIN_EMAIL}")
        print("═══════════════════════════════════════════════════")
        print("  CHANGE THE PASSWORD IMMEDIATELY IN PRODUCTION.")
        print("  Set env: SENTINEL_ADMIN_PASSWORD=YourSecurePass")
        print("  Then re-run: python -m scripts.seed_admin")
        print("═══════════════════════════════════════════════════")


if __name__ == "__main__":
    asyncio.run(seed())
