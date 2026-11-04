import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from app.db import admin_engine
from app.security import hash_worker_id

async def seed():
    # We need the user ID for worker-mombasa-1
    async with admin_engine.begin() as conn:
        user = (await conn.execute(text(
            "SELECT id, facility_id FROM users WHERE username = 'worker-mombasa-1'"
        ))).mappings().first()
        
        if not user:
            print("worker-mombasa-1 not found. Run seed_users.py first.")
            return

        uid = user["id"]
        fid = user["facility_id"]
        
        now = datetime.now(timezone.utc)
        
        # Insert schedules
        schedules = [
            (fid, uid, "ICU / Critical Care", "night", now + timedelta(days=1), now + timedelta(days=1, hours=12), "scheduled"),
            (fid, uid, "ICU / Critical Care", "day", now + timedelta(days=2), now + timedelta(days=2, hours=12), "scheduled"),
            (fid, uid, "Emergency Department", "night", now + timedelta(days=4), now + timedelta(days=4, hours=12), "scheduled"),
        ]
        
        for s in schedules:
            await conn.execute(text("""
                INSERT INTO worker_schedules (facility_id, user_id, department, shift_type, start_time, end_time, status)
                VALUES (:f, :u, :d, :t, :st, :et, :s)
            """), {"f": s[0], "u": s[1], "d": s[2], "t": s[3], "st": s[4], "et": s[5], "s": s[6]})

        # Insert medical history
        meds = [
            (fid, uid, (now - timedelta(days=30)).date(), "vaccination", "Annual Influenza Vaccine", False),
            (fid, uid, (now - timedelta(days=90)).date(), "injury", "Lower back strain from lifting patient", True),
        ]
        
        for m in meds:
            await conn.execute(text("""
                INSERT INTO medical_history (facility_id, user_id, record_date, record_type, description, restricted_duty)
                VALUES (:f, :u, :d, :t, :desc, :r)
            """), {"f": m[0], "u": m[1], "d": m[2], "t": m[3], "desc": m[4], "r": m[5]})

        print("Seeded schedules and medical history for worker-mombasa-1")

if __name__ == "__main__":
    asyncio.run(seed())
