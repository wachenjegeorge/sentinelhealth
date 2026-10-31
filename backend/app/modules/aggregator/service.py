"""Aggregator - the ONLY reader of `agg_logs`.

RLS on logs enforces officer county scope. Worker queries use facility scope.
No cross-county data is possible from the API - the DB enforces it.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def overview(session: AsyncSession, window_hours: int = 24) -> dict:
    rows = (await session.execute(text("""
        SELECT county, department, shift, day,
               n, avg_fatigue, avg_heat, avg_score, p90_score, critical_share
        FROM agg_logs
        WHERE day >= date_trunc('day', now() - make_interval(hours => :h))
        ORDER BY county, department, shift
    """), {"h": window_hours})).mappings().all()

    groups = [{
        "county": r["county"],
        "department": r["department"],
        "shift": r["shift"],
        "reported": int(r["n"]),
        "avg_fatigue": float(r["avg_fatigue"]),
        "avg_heat": float(r["avg_heat"]),
        "avg_score": float(r["avg_score"]),
        "p90_score": float(r["p90_score"]),
        "critical_share": float(r["critical_share"]),
    } for r in rows]

    if groups:
        total = sum(g["reported"] for g in groups)
        pooled = sum(g["p90_score"] * g["reported"] for g in groups) / total
    else:
        pooled = 0.0

    by_county: dict[str, dict] = {}
    for g in groups:
        c = by_county.setdefault(g["county"], {
            "county": g["county"], "reported": 0, "scores": [],
            "departments": set(),
        })
        c["reported"] += g["reported"]
        c["scores"].append((g["p90_score"], g["reported"]))
        c["departments"].add(g["department"])

    counties = []
    for c in by_county.values():
        t = sum(w for _, w in c["scores"])
        wvi = sum(s * w for s, w in c["scores"]) / t if t else 0.0
        counties.append({
            "county": c["county"],
            "wvi": round(wvi, 1),
            "level": "Critical" if wvi >= 65 else "Moderate" if wvi >= 35 else "Low",
            "reported": c["reported"],
            "departments": len(c["departments"]),
        })
    counties.sort(key=lambda x: -x["wvi"])

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pooled_wvi": round(pooled, 1),
        "pooled_level": "Critical" if pooled >= 65 else "Moderate" if pooled >= 35 else "Low",
        "group_count": len(groups),
        "county_count": len(counties),
        "groups": groups,
        "counties": counties,
        "k_anonymity": 5,
    }
