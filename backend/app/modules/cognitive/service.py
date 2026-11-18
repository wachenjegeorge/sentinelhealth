"""Cognitive Wellness Index (CWI), baseline, escalation."""
from __future__ import annotations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.security import hash_worker_id

CRIT = 65
MOD = 35
BASELINE_DAYS = 14
BASELINE_MIN_SAMPLES = 5


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def level_for(score):
    return "Critical" if score >= CRIT else "Moderate" if score >= MOD else "Low"


def compute_cwi(*, cognitive_fatigue, mental_clarity, stress, sleep_quality, sleep_hours):
    cf = (cognitive_fatigue - 1) / 9 * 100
    mc = (mental_clarity - 1) / 9 * 100
    clarity_inverse = 100 - mc
    st = (stress - 1) / 9 * 100
    hours_debt = max(0.0, 7.0 - sleep_hours) / 7.0 * 100
    quality_debt = (5 - sleep_quality) / 4 * 100
    sleep_score = hours_debt * 0.6 + quality_debt * 0.4

    components = {
        "cognitive_fatigue": round(cf, 1),
        "stress": round(st, 1),
        "clarity_inverse": round(clarity_inverse, 1),
        "sleep": round(sleep_score, 1),
    }
    weights = {
        "cognitive_fatigue": 0.35, "stress": 0.20,
        "clarity_inverse": 0.20, "sleep": 0.25,
    }
    total = _clamp(sum(weights[k] * components[k] for k in weights))
    return {"cwi": round(total, 1), "level": level_for(total), "components": components}


async def compute_baseline(session, *, worker_hash, lookback_days=BASELINE_DAYS):
    row = (await session.execute(text(f"""
        SELECT count(*) AS n,
            avg(cognitive_fatigue)::numeric(5,2) AS cognitive_fatigue,
            avg(mental_clarity)::numeric(5,2) AS mental_clarity,
            avg(stress)::numeric(5,2) AS stress,
            avg(sleep_quality)::numeric(5,2) AS sleep_quality,
            avg(sleep_hours)::numeric(5,2) AS sleep_hours,
            avg(cwi)::numeric(5,1) AS cwi
        FROM logs
        WHERE worker_id_hash = :h AND cwi IS NOT NULL
          AND created_at >= now() - interval '{lookback_days} days'
    """), {"h": worker_hash})).mappings().first()

    n = int(row["n"]) if row and row["n"] is not None else 0
    if n < BASELINE_MIN_SAMPLES:
        return {"ready": False, "sample_count": n, "min_samples": BASELINE_MIN_SAMPLES,
                "window_days": lookback_days, "baseline": None}
    def _f(v): return float(v) if v is not None else None
    return {"ready": True, "sample_count": n, "min_samples": BASELINE_MIN_SAMPLES,
            "window_days": lookback_days,
            "baseline": {k: _f(row[k]) for k in
                ("cognitive_fatigue","mental_clarity","stress","sleep_quality","sleep_hours","cwi")}}


async def maybe_escalate(session, *, log_id, facility_id, department, worker_username,
                         cwi, cwi_level, cognitive_fields, components):
    if cwi < CRIT:
        return False
    await session.execute(text("""
        INSERT INTO cognitive_confirmations
            (log_id, facility_id, department, worker_id_hash, worker_username,
             cwi, cwi_level, cognitive_fatigue, mental_clarity, stress,
             sleep_quality, sleep_hours, components, status)
        VALUES
            (:lid,:f,:d,:wh,:wu,:cwi,:lvl,:cf,:mc,:st,:sq,:sh,:comp,'pending')
    """), {
        "lid": log_id, "f": facility_id, "d": department,
        "wh": hash_worker_id(worker_username), "wu": worker_username,
        "cwi": cwi, "lvl": cwi_level,
        "cf": cognitive_fields.get("cognitive_fatigue"),
        "mc": cognitive_fields.get("mental_clarity"),
        "st": cognitive_fields.get("stress"),
        "sq": cognitive_fields.get("sleep_quality"),
        "sh": cognitive_fields.get("sleep_hours"),
        "comp": components,
    })
    return True
