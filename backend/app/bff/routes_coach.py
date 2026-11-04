from fastapi import APIRouter, Request
from sqlalchemy import text
from app.db import with_tenant
from app.modules.assistant import llm_client
from app.security import hash_worker_id

router = APIRouter(prefix="/api/bff/worker/coach", tags=["coach"])

@router.get("")
async def get_coaching(request: Request):
    claims = request.state.claims
    worker_hash = hash_worker_id(claims["username"])
    
    async with with_tenant(claims["facility_id"], role="worker", user_id=claims["sub"]) as session:
        log = (await session.execute(text("""
            SELECT fatigue, heat_exposure FROM logs
            WHERE worker_id_hash = :h ORDER BY created_at DESC LIMIT 1
        """), {"h": worker_hash})).mappings().first()

        wearable = (await session.execute(text("""
            SELECT steps, sleep_hours FROM wearable_metrics
            WHERE user_id = :u ORDER BY metric_date DESC LIMIT 1
        """), {"u": claims["sub"]})).mappings().first()

    # Predictive Early Warning Logic
    is_critical = False
    if log and wearable:
        if (log["fatigue"] >= 8 and float(wearable["sleep_hours"]) <= 6.0) or (log["heat_exposure"] >= 8 and log["fatigue"] >= 7):
            is_critical = True

    context = "Health data:\n"
    if log: context += f"- Fatigue: {log['fatigue']}/10\n- Heat: {log['heat_exposure']}/10\n"
    if wearable: context += f"- Sleep: {wearable['sleep_hours']} hrs\n- Steps: {wearable['steps']}\n"

    prompt = f"""
    You are an AI occupational health coach for a Kenyan healthcare worker.
    {context}
    Write a 2-sentence message. If they have high fatigue AND low sleep, warn them about physical exhaustion and injury risk.
    Give ONE actionable tip (e.g., take a 15-min nap, hydrate).
    """

    try:
        res = await llm_client.chat([{"role": "user", "content": prompt}])
        msg = res["message"]["content"]
    except Exception:
        msg = "You had low sleep and high fatigue. Prioritize a 15-minute break and drink water before your shift." if is_critical else "Keep monitoring your vitals. Ensure you take your mandatory breaks and stay hydrated."

    return {
        "message": msg,
        "severity": "critical" if is_critical else "normal",
        "is_warning": is_critical
    }
