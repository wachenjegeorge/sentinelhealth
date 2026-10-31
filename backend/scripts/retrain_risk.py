import asyncio
from sqlalchemy import text
from app.db import admin_engine


async def main():
    async with admin_engine.connect() as conn:
        rows = (await conn.execute(text("""
            SELECT predicted_level,
                   count(*) AS n,
                   count(*) FILTER (WHERE outcome = 'intervention') AS interventions,
                   count(*) FILTER (WHERE outcome = 'adverse_event') AS events
            FROM risk_outcomes
            GROUP BY predicted_level
            ORDER BY predicted_level
        """))).mappings().all()

        if not rows:
            print("No outcome data yet. Record outcomes via POST /api/bff/assistant/outcome")
            return

        print("Calibration report:")
        print(f"{'level':<12} {'n':>5} {'interv.':>8} {'events':>7} {'rate':>7}")
        print("-" * 45)
        for r in rows:
            n = r["n"]
            events = r["events"] or 0
            interventions = r["interventions"] or 0
            rate = (events + interventions) / n if n else 0
            print(f"{r['predicted_level']:<12} {n:>5} {interventions:>8} "
                  f"{events:>7} {rate:>6.1%}")
        print()
        print("If 'Critical' rows have a rate well below 65%, the model is")
        print("over-alerting. If far above, it is under-alerting. Adjust CRIT")
        print("and MOD constants in app/modules/risk_engine/service.py.")


if __name__ == "__main__":
    asyncio.run(main())
