import asyncio, uuid
from sqlalchemy import text
from app.db import admin_engine
from app.auth.passwords import hash_password

PASSWORD = "TestPass2026!"

async def seed():
    pw_hash = hash_password(PASSWORD)
    async with admin_engine.begin() as c:
        # 1. Get the Mombasa Level 5 Facility
        fac = (await c.execute(text(
            "SELECT id FROM facilities WHERE county = 'Mombasa' AND keph_level = 5 LIMIT 1"
        ))).scalar()
        
        if not fac:
            print("ERROR: Mombasa Level 5 facility not found. Run seed_all_facilities first.")
            return

        # 2. Ensure Admin exists
        await c.execute(text("""
            INSERT INTO users (id, username, password_hash, role, facility_id, full_name, active, verification_status)
            VALUES (:id, 'sentinel', :p, 'admin', :f, 'National Admin', true, 'verified')
            ON CONFLICT (username) DO UPDATE SET password_hash = :p, verification_status = 'verified', active = true
        """), {"id": str(uuid.uuid4()), "p": pw_hash, "f": fac})

        # 3. Create test accounts for all other roles
        test_users = [
            ("test-officer",   "county_officer",  "Mombasa County Officer"),
            ("test-head",      "hospital_head",   "Dr. Hospital Head"),
            ("test-dept-head", "department_head", "Nurse ICU In-charge"),
            ("test-worker",    "worker",          "Nurse Test Worker"),
        ]

        for username, role, full_name in test_users:
            await c.execute(text("""
                INSERT INTO users (id, username, password_hash, role, facility_id, full_name, primary_department, active, verification_status)
                VALUES (:id, :u, :p, :r, :f, :n, 'ICU / Critical Care', true, 'verified')
                ON CONFLICT (username) DO UPDATE SET password_hash = :p, verification_status = 'verified', active = true
            """), {"id": str(uuid.uuid4()), "u": username, "p": pw_hash, "r": role, "f": fac, "n": full_name})

        print(f"SUCCESS: Test accounts seeded. Password for all: {PASSWORD}")
        print("  sentinel (admin)")
        print("  test-officer (county_officer)")
        print("  test-head (hospital_head)")
        print("  test-dept-head (department_head)")
        print("  test-worker (worker)")

asyncio.run(seed())
