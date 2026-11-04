from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import text
from app.db import with_tenant
from app.modules.assistant import llm_client

router = APIRouter(prefix="/api/bff/admin/simulate", tags=["simulator"])

class SimulatePayload(BaseModel):
    department: str
    shift: str
    extra_staff: int
    current_wvi: float

@router.post("")
async def simulate(payload: SimulatePayload, request: Request):
    claims = request.state.claims
    
    # Simple deterministic math: Every extra staff member reduces fatigue by 8%
    # WVI is heavily weighted by fatigue (30%), so we estimate the drop.
    fatigue_reduction = payload.extra_staff * 0.08
    estimated_wvi = max(0, payload.current_wvi - (payload.current_wvi * fatigue_reduction))
    
    # Ask the LLM to explain the math in clinical terms
    prompt = f"""
    The {payload.department} department on the {payload.shift} shift currently has a WVI of {payload.current_wvi}.
    We are simulating adding {payload.extra_staff} extra staff members to this shift.
    The new estimated WVI will drop to {estimated_wvi:.1f}.
    Write a 2-sentence clinical justification for this intervention. Focus on how reducing the patient-to-nurse ratio prevents burnout and fatigue errors.
    """
    
    ai_reasoning = ""
    try:
        res = await llm_client.chat([{"role": "user", "content": prompt}])
        ai_reasoning = res["message"]["content"]
    except Exception:
        ai_reasoning = f"Adding {payload.extra_staff} staff reduces the workload per provider, lowering fatigue and dropping the WVI from {payload.current_wvi} to {estimated_wvi:.1f}."

    return {
        "current_wvi": payload.current_wvi,
        "projected_wvi": round(estimated_wvi, 1),
        "ai_reasoning": ai_reasoning
    }
