import asyncio, random, uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from app.db import admin_engine
from app.auth.passwords import hash_password
from app.security import hash_worker_id

KENYAN_NAMES = [
    "Joy Mwende", "Brian Omondi", "Faith Wanjiku", "Kevin Mutua", 
    "Mercy Chepngetich", "David Kipchoge", "Esther Achieng", "Samuel Njoroge",
    "Grace Muthoni", "Peter Barasa", "Lydia Wambui", "Jameson Kamau"
]

async def seed():
    pw_hash = hash_password("DemoPass2026!")
    async with admin_engine.begin() as conn:
        fac = (await conn.execute(text("SELECT id FROM facilities WHERE county = 'Mombasa' LIMIT 1"))).scalar()
        
        # Create real staff and store their real hashed IDs for the logs
        hashes = []
        for i, name in enumerate(KENYAN_NAMES):
            username = f"staff-{i+1}"
            await conn.execute(text("""
                INSERT INTO users (id, username, password_hash, role, facility_id, full_name, active)
                VALUES (:id, :u, :p, 'worker', :f, :n, true)
                ON CONFLICT (username) DO UPDATE SET full_name = :n
            """), {"id": str(uuid.uuid4()), "u": username, "p": pw_hash, "f": fac, "n": name})
            hashes.append(hash_worker_id(username))

        # Inject 30 Days of history using REAL hashes
        depts = ["ICU / Critical Care", "Emergency Department", "Maternity", "Laboratory"]
        for day in range(30, 0, -1):
            date_offset = datetime.now(timezone.utc) - timedelta(days=day)
            for _ in range(random.randint(3, 6)):
                base_fatigue = 4 + (day % 7) * 0.5 + random.uniform(-1, 2)
                base_heat = 5 + random.uniform(-2, 3) if day % 2 == 0 else 4
                score = base_fatigue * 6 + base_heat * 3
                
                await conn.execute(text("""
                    INSERT INTO logs (id, facility_id, county, worker_id_hash, department, shift, fatigue, heat_exposure, hours_worked, risk_score, risk_level, components, created_at)
                    VALUES (:id, :f, 'Mombasa', :w, :d, :s, :fat, :heat, 10, :score, :lvl, '{}', :ts)
                """), {
                    "id": str(uuid.uuid4()), "f": fac, "w": random.choice(hashes),
                    "d": random.choice(depts), "s": random.choice(["day", "night"]),
                    "fat": min(10, max(1, int(base_fatigue))), "heat": min(10, max(1, int(base_heat))),
                    "score": score, "lvl": "Critical" if score > 65 else "Moderate" if score > 35 else "Low",
                    "ts": date_offset.replace(hour=random.randint(6, 22))
                })
        print("Seeded 30 days of real-world history with accurate hashes.")

if __name__ == "__main__":
    asyncio.run(seed())
