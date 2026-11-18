"""Personal AI Health Coach — structured cognitive + physical signals.
Backward-compatible: keeps `message`, `severity`, `is_warning`.
"""
from fastapi import APIRouter, Request
from sqlalchemy import text

from app.db import with_tenant
from app.modules.assistant import llm_client
from app.modules.cognitive.service import compute_baseline
from app.security import hash_worker_id

router = APIRouter(prefix="/api/bff/worker/coach", tags=["coach"])

COACH_SYSTEM = (
    "You are a supportive, non-clinical AI health coach for a Kenyan healthcare worker. "
    "ABSOLUTE RULES:\n"
    "1. Never diagnose any condition. Never use clinical terminology like 'depression', "
    "'burnout syndrome', 'PTSD'.\n"
    "2. Frame observations as patterns in their data, not as medical findings.\n"
    "3. Always end with ONE small, concrete, achievable action.\n"
    "4. If data shows sustained worsening (>=3 consecutive days of cognitive signals up), "
    "mention talking to their supervisor or occupational health focal person.\n"
    "5. Be warm, brief. 3 sentences max.\n"
)


@router.get("")
async def get_coaching(request: Request):
    claims = request.state.claims
    worker_hash = hash_worker_id(claims["username"])

    async with with_tenant(claims["facility_id"], role="worker",
                           user_id=claims["sub"]) as session:
        log = (await session.execute(text("""
            SELECT fatigue, heat_exposure, cwi, cwi_level,
                   cognitive_fatigue, mental_clarity, stress,
                   sleep_quality, sleep_hours
            FROM logs WHERE worker_id_hash = :h
            ORDER BY created_at DESC LIMIT 1
        """), {"h": worker_hash})).mappings().first()

        wearable = (await session.execute(text("""
            SELECT steps, sleep_hours FROM wearable_metrics
            WHERE user_id = :u ORDER BY metric_date DESC LIMIT 1
        """), {"u": claims["sub"]})).mappings().first()

        baseline = await compute_baseline(session, worker_hash=worker_hash)

    signals = []
    if log and baseline["ready"]:
        b = baseline["baseline"]
        checks = [
            ("Mental fatigue", "cognitive_fatigue", "pts", 1.0, 3.0),
            ("Stress", "stress", "pts", 1.0, 3.0),
            ("Sleep", "sleep_hours", "h", 0.5, 2.0),
        ]
        for label, key, unit, min_delta, high_thresh in checks:
            if log[key] is not None and b.get(key) is not None:
                d = float(log[key]) - float(b[key])
                if abs(d) >= min_delta:
                    signals.append({
                        "label": label,
                        "delta": f"{d:+.1f} {unit}".strip(),
                        "direction": "up" if d > 0 else "down",
                        "severity": "high" if abs(d) >= high_thresh else "moderate",
                    })

    is_critical = False
    cwi = cwi_level = None
    if log:
        if log["cwi"] is not None:
            cwi = float(log["cwi"]); cwi_level = log["cwi_level"]
            if cwi >= 65: is_critical = True
        if wearable and (log["fatigue"] >= 8 and float(wearable["sleep_hours"]) <= 6.0):
            is_critical = True
        if log["heat_exposure"] >= 8 and log["fatigue"] >= 7:
            is_critical = True

    context = ""
    if log:
        context += f"- Physical fatigue: {log['fatigue']}/10\n- Heat: {log['heat_exposure']}/10\n"
        if log["cognitive_fatigue"] is not None:
            context += (f"- Mental fatigue: {log['cognitive_fatigue']}/10\n"
                        f"- Mental clarity: {log['mental_clarity']}/10\n"
                        f"- Stress: {log['stress']}/10\n")
        if log["sleep_hours"] is not None:
            context += f"- Sleep: {log['sleep_hours']}h, quality {log['sleep_quality']}/5\n"
    if cwi is not None:
        context += f"- CWI: {cwi}/100 ({cwi_level})\n"

    narrative = None
    action = "Consider a 15-minute break and a glass of water before your next task."
    try:
        res = await llm_client.chat([{"role": "user",
            "content": COACH_SYSTEM + "\nWorker's recent data:\n" + context +
                "\nWrite 2-3 sentences of warm, non-clinical guidance ending with one action."}])
        narrative = res["message"]["content"]
    except Exception:
        narrative = ("Your recent signals suggest accumulating load. This is a pattern "
                     "worth resting against, not pushing through." if is_critical else
                     "Your signals look manageable today. Small, steady habits keep them that way.")
        if is_critical:
            action = "Take a 15-minute break before your shift and hydrate."

    escalate_to = None
    if cwi is not None and cwi >= 65:
        escalate_to = {
            "role": "department_head",
            "trigger": "Persistent elevated cognitive load (CWI >= 65)",
            "message": ("If this continues for 3+ more days, talk to your department head "
                        "or the facility occupational health focal person."),
        }

    return {
        "message": narrative, "severity": "critical" if is_critical else "normal",
        "is_warning": is_critical,
        "narrative": narrative, "signals": signals, "action": action,
        "escalate_to": escalate_to, "cwi": cwi, "cwi_level": cwi_level,
        "baseline_ready": baseline["ready"],
        "baseline_sample_count": baseline["sample_count"],
    }
