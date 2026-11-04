"""Aggregation service - role-aware at three scopes: national, county, facility."""
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _trend(session: AsyncSession, where_sql: str, params: dict) -> list[dict]:
    rows = (await session.execute(text(f"""
        SELECT date_trunc('day', created_at) AS day,
               avg(risk_score)::numeric(5,1) AS avg_wvi,
               count(*) AS reports
        FROM logs WHERE {where_sql} AND created_at >= now() - interval '30 days'
        GROUP BY 1 ORDER BY 1 ASC
    """), params)).mappings().all()
    return [{"day": r["day"].strftime("%a %d"), "wvi": float(r["avg_wvi"]),
             "reports": r["reports"]} for r in rows]


async def _level(wvi: float) -> str:
    return "Critical" if wvi >= 65 else "Moderate" if wvi >= 35 else "Low"


async def overview_national(session: AsyncSession) -> dict:
    """ADMIN view: national roll-up by county."""
    rows = (await session.execute(text("""
        SELECT county, department, shift, day, n, p90_score, critical_share
        FROM agg_logs ORDER BY county
    """))).mappings().all()

    by_county: dict[str, dict] = {}
    for r in rows:
        c = by_county.setdefault(r["county"], {"county": r["county"],
                                                "reported": 0, "scores": [],
                                                "departments": set()})
        c["reported"] += r["n"]
        c["scores"].append((float(r["p90_score"]), r["n"]))
        c["departments"].add(r["department"])

    counties = []
    for c in by_county.values():
        t = sum(w for _, w in c["scores"])
        wvi = sum(s * w for s, w in c["scores"]) / t if t else 0
        counties.append({"county": c["county"], "wvi": round(wvi, 1),
                         "level": await _level(wvi),
                         "reported": c["reported"],
                         "departments": len(c["departments"])})
    counties.sort(key=lambda x: -x["wvi"])

    total = sum(x["reported"] for x in counties)
    pooled = sum(x["wvi"] * x["reported"] for x in counties) / total if total else 0

    return {
        "scope": "national",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pooled_wvi": round(pooled, 1),
        "pooled_level": await _level(pooled),
        "county_count": len(counties),
        "groups": rows,
        "counties": counties,
        "trend": await _trend(session, "1=1", {}),
        "k_anonymity": 5,
    }


async def overview_county(session: AsyncSession, county: str) -> dict:
    """OFFICER view: county roll-up by facility."""
    rows = (await session.execute(text("""
        SELECT facility_id, department, shift, day, n, p90_score, critical_share
        FROM agg_logs WHERE county = :c
    """), {"c": county})).mappings().all()

    facs = (await session.execute(text("""
        SELECT id, name, keph_level FROM facilities
        WHERE county = :c AND active = true
    """), {"c": county})).mappings().all()

    by_fac: dict[str, dict] = {}
    for r in rows:
        f = by_fac.setdefault(r["facility_id"], {"reported": 0, "scores": [], "departments": set()})
        f["reported"] += r["n"]
        f["scores"].append((float(r["p90_score"]), r["n"]))
        f["departments"].add(r["department"])

    facilities = []
    for fac in facs:
        d = by_fac.get(fac["id"], {"reported": 0, "scores": [], "departments": set()})
        if d["reported"] < 5:
            facilities.append({"facility_id": fac["id"], "name": fac["name"],
                               "keph_level": fac["keph_level"], "suppressed": True,
                               "reported": d["reported"], "wvi": None, "level": "Suppressed"})
            continue
        t = sum(w for _, w in d["scores"])
        wvi = sum(s * w for s, w in d["scores"]) / t
        facilities.append({"facility_id": fac["id"], "name": fac["name"],
                           "keph_level": fac["keph_level"], "suppressed": False,
                           "reported": d["reported"], "wvi": round(wvi, 1),
                           "level": await _level(wvi),
                           "departments": len(d["departments"])})
    facilities.sort(key=lambda x: -(x["wvi"] or 0))

    total = sum(f["reported"] for f in facilities)
    pooled = sum((f["wvi"] or 0) * f["reported"] for f in facilities) / total if total else 0

    return {
        "scope": "county", "county": county,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pooled_wvi": round(pooled, 1), "pooled_level": await _level(pooled),
        "facility_count": len(facilities),
        "groups": rows, "facilities": facilities,
        "trend": await _trend(session, "county = :c", {"c": county}),
        "k_anonymity": 5,
    }


async def overview_facility(session: AsyncSession, facility_id: str) -> dict:
    """HOSPITAL HEAD view: department roll-up within one facility."""
    rows = (await session.execute(text("""
        SELECT department, shift, day, n, p90_score, critical_share
        FROM agg_logs WHERE facility_id = :f
    """), {"f": facility_id})).mappings().all()

    by_dept: dict[str, dict] = {}
    for r in rows:
        d = by_dept.setdefault(r["department"], {"reported": 0, "scores": [], "shifts": set()})
        d["reported"] += r["n"]
        d["scores"].append((float(r["p90_score"]), r["n"]))
        d["shifts"].add(r["shift"])

    departments = []
    for name, d in by_dept.items():
        t = sum(w for _, w in d["scores"])
        wvi = sum(s * w for s, w in d["scores"]) / t
        departments.append({"department": name, "wvi": round(wvi, 1),
                            "level": await _level(wvi), "reported": d["reported"],
                            "shifts": list(d["shifts"])})
    departments.sort(key=lambda x: -x["wvi"])

    total = sum(x["reported"] for x in departments)
    pooled = sum(x["wvi"] * x["reported"] for x in departments) / total if total else 0

    return {
        "scope": "facility", "facility_id": facility_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pooled_wvi": round(pooled, 1), "pooled_level": await _level(pooled),
        "department_count": len(departments),
        "groups": rows, "departments": departments,
        "trend": await _trend(session, "facility_id = :f", {"f": facility_id}),
        "k_anonymity": 5,
    }


# Backward compatibility
async def overview(session: AsyncSession, window_hours: int = 24):
    return await overview_national(session)
