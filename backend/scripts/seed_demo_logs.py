import asyncio
import random
from sqlalchemy import text
from app.db import admin_engine, with_tenant
from app.idempotency import with_idempotency
from app.modules.ingestion.service import ingest

HOTSPOTS = {
    "Turkana": 0.92, "Mandera": 0.90, "Wajir": 0.88, "Garissa": 0.86,
    "Marsabit": 0.84, "Narok": 0.80, "West Pokot": 0.72, "Samburu": 0.70,
    "Mombasa": 0.62, "Kisumu": 0.60, "Nairobi": 0.55,
}
DEPARTMENTS = ["Emergency Department", "ICU / Critical Care", "Maternity",
               "Paediatrics", "Laboratory", "Kitchen & Laundry", "Community Health"]


async def seed():
    rng = random.Random(20261030)
    created = 0
    skipped = 0
    async with admin_engine.connect() as conn:
        facilities = (await conn.execute(text(
            "SELECT id, county FROM facilities WHERE keph_level = 5 ORDER BY county"
        ))).mappings().all()

    for row in facilities:
        county = row["county"]
        facility_id = row["id"]
        pressure = HOTSPOTS.get(county, rng.uniform(0.25, 0.55))
        n = int(50 + pressure * 80)

        async with with_tenant(facility_id, role="worker") as session:
            for i in range(n):
                idem_key = "seedlog-%s-%d" % (facility_id, i)
                fatigue = max(1, min(10, int(round(2.5 + pressure*6.5 + rng.gauss(0, 1.1)))))
                heat = max(1, min(10, int(round(2.0 + pressure*7.0 + rng.gauss(0, 1.0)))))
                hours = max(4.0, min(16.0, 8.0 + pressure*3.5 + rng.gauss(0, 0.8)))
                symptoms = []
                if pressure > 0.5 and rng.random() < pressure - 0.2:
                    symptoms = rng.sample(
                        ["headache","dizziness","nausea","cough","muscle_strain"],
                        k=rng.randint(1, 2))
                dept = rng.choice(DEPARTMENTS)
                shift = "night" if rng.random() < 0.45 else "day"
                worker = "seed-%s-%d" % (facility_id, i)

                async def work(s, _f=facility_id, _w=worker, _d=dept, _sh=shift,
                               _fa=fatigue, _he=heat, _ho=hours, _sy=symptoms):
                    return await ingest(
                        s, facility_id=_f, worker_id=_w, department=_d, shift=_sh,
                        fatigue=_fa, heat_exposure=_he, hours_worked=_ho, symptoms=_sy)

                try:
                    await with_idempotency(session, key=idem_key,
                                          facility_id=facility_id, work=work)
                    created += 1
                except Exception as e:
                    if skipped == 0:
                        import traceback
                        print("SEED FAILED FIRST:", type(e).__name__, str(e))
                        traceback.print_exc()
                    skipped += 1

    print("Seed: %d created, %d skipped" % (created, skipped))


if __name__ == "__main__":
    asyncio.run(seed())
