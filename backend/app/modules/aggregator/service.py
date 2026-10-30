from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def overview(session: AsyncSession, window_hours: int = 24):
    rows = (await session.execute(text("""
        SELECT facility_id, department, shift, day, n, avg_fatigue,
               avg_heat, avg_score, p90_score, critical_share
        FROM agg_logs
        WHERE day >= date_trunc('day', now() - make_interval(hours => :h))
        ORDER BY facility_id, department, shift
    """), {"h": window_hours})).mappings().all()
    groups = [{"facility_id":r["facility_id"],"department":r["department"],
               "shift":r["shift"],"reported":int(r["n"]),
               "avg_fatigue":float(r["avg_fatigue"]),
               "avg_heat":float(r["avg_heat"]),
               "avg_score":float(r["avg_score"]),
               "p90_score":float(r["p90_score"]),
               "critical_share":float(r["critical_share"])} for r in rows]
    if groups:
        total = sum(g["reported"] for g in groups)
        pooled = sum(g["p90_score"] * g["reported"] for g in groups) / total
    else:
        pooled = 0.0
    return {"generated_at":datetime.now(timezone.utc).isoformat(),
            "pooled_wvi":round(pooled,1),"group_count":len(groups),
            "groups":groups,"k_anonymity":5}
