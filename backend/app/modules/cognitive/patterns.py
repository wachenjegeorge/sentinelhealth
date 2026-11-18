"""Deterministic pattern detection across a worker's cognitive wellness history.

Finds patterns AI can act on. All detection is rule-based — no LLM, no
hallucination risk. Patterns feed the intervention generator.
"""
from __future__ import annotations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def detect_patterns(session: AsyncSession, worker_hash: str,
                          lookback_days: int = 14) -> dict:
    rows = (await session.execute(text(f"""
        SELECT date_trunc('day', created_at) AS day,
               avg(cognitive_fatigue)::numeric(5,2) AS cf,
               avg(mental_clarity)::numeric(5,2) AS mc,
               avg(stress)::numeric(5,2) AS st,
               avg(sleep_quality)::numeric(5,2) AS sq,
               avg(sleep_hours)::numeric(5,2) AS sh,
               avg(cwi)::numeric(5,1) AS cwi,
               count(*) AS n
        FROM logs
        WHERE worker_id_hash = :h AND cwi IS NOT NULL
          AND created_at >= now() - interval '{lookback_days} days'
        GROUP BY 1 ORDER BY 1
    """), {"h": worker_hash})).mappings().all()

    if len(rows) < 3:
        return {"ready": False, "reason": "insufficient_history",
                "days_analyzed": len(rows), "min_days": 3, "patterns": []}

    days = [dict(r) for r in rows]
    patterns: list[dict] = []

    # 1. Sleep debt streak
    sd = [d for d in days if d["sh"] is not None and float(d["sh"]) < 6.5]
    if len(sd) >= 3:
        patterns.append({
            "type": "sleep_debt_streak",
            "severity": "high" if len(sd) >= 5 else "moderate",
            "span_days": len(sd),
            "avg_sleep_hours": round(sum(float(d["sh"]) for d in sd) / len(sd), 1),
            "label": f"{len(sd)} days with sleep under 6.5h",
        })

    # 2. Stress escalation (recent vs earlier average)
    st = [float(d["st"]) for d in days if d["st"] is not None]
    if len(st) >= 4:
        recent = sum(st[-3:]) / 3
        earlier = sum(st[:3]) / 3
        delta = recent - earlier
        if delta >= 1.5:
            patterns.append({
                "type": "stress_escalation",
                "severity": "high" if delta >= 3 else "moderate",
                "delta": round(delta, 1),
                "recent_avg": round(recent, 1),
                "label": f"Stress up {round(delta,1)} pts vs earlier",
            })

    # 3. Clarity crash
    mc = [float(d["mc"]) for d in days if d["mc"] is not None]
    if len(mc) >= 5:
        base = sum(mc) / len(mc)
        rec = sum(mc[-2:]) / 2
        drop = base - rec
        if drop >= 2:
            patterns.append({
                "type": "clarity_crash",
                "severity": "high" if drop >= 4 else "moderate",
                "drop": round(drop, 1),
                "baseline": round(base, 1),
                "label": f"Clarity down {round(drop,1)} pts vs baseline",
            })

    # 4. Correlated crash (same day: low sleep AND high mental fatigue)
    corr = [d for d in days
            if d["sh"] is not None and d["cf"] is not None
            and float(d["sh"]) < 6 and float(d["cf"]) >= 7]
    if len(corr) >= 2:
        patterns.append({
            "type": "correlated_crash",
            "severity": "high",
            "occurrences": len(corr),
            "label": f"Low sleep + high mental fatigue on {len(corr)} days",
        })

    # 5. Recovery after rest (positive signal — worth reinforcing)
    for i in range(1, len(days)):
        prev, cur = days[i-1], days[i]
        if (prev["sh"] is not None and float(prev["sh"]) >= 8
            and prev["mc"] is not None and cur["mc"] is not None
            and float(cur["mc"]) - float(prev["mc"]) >= 2):
            patterns.append({
                "type": "recovery_after_rest",
                "severity": "low",
                "gain": round(float(cur["mc"]) - float(prev["mc"]), 1),
                "label": f"Clarity +{round(float(cur['mc']) - float(prev['mc']),1)} after 8h+ sleep — your body responds to rest",
            })
            break

    # 6. CWI trend (linear slope over window)
    cwi = [float(d["cwi"]) for d in days if d["cwi"] is not None]
    if len(cwi) >= 4:
        n = len(cwi); xs = list(range(n))
        sx = sum(xs); sy = sum(cwi)
        sxy = sum(x*y for x, y in zip(xs, cwi)); sxx = sum(x*x for x in xs)
        denom = n*sxx - sx*sx
        slope = ((n*sxy - sx*sy) / denom) if denom else 0
        if slope >= 1.5:
            patterns.append({
                "type": "worsening_trend",
                "severity": "high" if slope >= 3 else "moderate",
                "slope_per_day": round(slope, 2),
                "label": f"CWI trending up {round(slope,2)}/day",
            })
        elif slope <= -1.5:
            patterns.append({
                "type": "improving_trend",
                "severity": "low",
                "slope_per_day": round(slope, 2),
                "label": f"CWI trending down {abs(round(slope,2))}/day",
            })

    # 7. Night shift penalty (avg cognitive fatigue higher on night shifts)
    night = (await session.execute(text(f"""
        SELECT avg(cognitive_fatigue)::numeric(5,2) AS night_avg, count(*) AS n
        FROM logs WHERE worker_id_hash = :h AND shift = 'night'
          AND cognitive_fatigue IS NOT NULL
          AND created_at >= now() - interval '{lookback_days} days'
    """), {"h": worker_hash})).mappings().first()
    day = (await session.execute(text(f"""
        SELECT avg(cognitive_fatigue)::numeric(5,2) AS day_avg, count(*) AS n
        FROM logs WHERE worker_id_hash = :h AND shift = 'day'
          AND cognitive_fatigue IS NOT NULL
          AND created_at >= now() - interval '{lookback_days} days'
    """), {"h": worker_hash})).mappings().first()
    if night["n"] and day["n"] and night["night_avg"] and day["day_avg"]:
        diff = float(night["night_avg"]) - float(day["day_avg"])
        if diff >= 1.5:
            patterns.append({
                "type": "night_shift_penalty",
                "severity": "moderate" if diff < 3 else "high",
                "delta": round(diff, 1),
                "label": f"Mental fatigue {round(diff,1)} pts higher on night shifts",
            })

    sev_order = {"high": 0, "moderate": 1, "low": 2}
    patterns.sort(key=lambda p: sev_order.get(p.get("severity", "low"), 9))

    return {
        "ready": True,
        "days_analyzed": len(days),
        "patterns": patterns,
        "latest_cwi": cwi[-1] if cwi else None,
        "latest_date": days[-1]["day"].isoformat() if days else None,
    }
