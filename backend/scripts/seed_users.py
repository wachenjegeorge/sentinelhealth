import asyncio
from sqlalchemy import text
from app.auth.passwords import hash_password
from app.db import seed_engine

DEFAULT_PASSWORD = "DemoPass2026!"


def county_slug(county):
    return county.lower().replace(" ", "-").replace("'", "")


async def seed():
    pw_hash = hash_password(DEFAULT_PASSWORD)
    created = 0
    async with seed_engine.begin() as conn:
        counties = (await conn.execute(text(
            "SELECT county, id FROM facilities WHERE keph_level = 5 ORDER BY county"
        ))).mappings().all()
        for row in counties:
            county = row["county"]
            facility_id = row["id"]
            cs = county_slug(county)
            r = await conn.execute(text(
                "INSERT INTO users (username, password_hash, role, facility_id, full_name) "
                "VALUES (:u, :p, 'health_officer', :f, :n) "
                "ON CONFLICT (username) DO NOTHING"
            ), {"u": "officer-" + cs, "p": pw_hash, "f": facility_id,
                "n": "County Health Officer - " + county})
            created += r.rowcount
            for i in range(1, 4):
                r = await conn.execute(text(
                    "INSERT INTO users (username, password_hash, role, facility_id, full_name) "
                    "VALUES (:u, :p, 'worker', :f, :n) "
                    "ON CONFLICT (username) DO NOTHING"
                ), {"u": "worker-" + cs + "-" + str(i), "p": pw_hash,
                    "f": facility_id, "n": "Worker " + str(i) + " - " + county})
                created += r.rowcount
    print("Seed: %d new users" % created)
    print("Password: %s" % DEFAULT_PASSWORD)


if __name__ == "__main__":
    asyncio.run(seed())
