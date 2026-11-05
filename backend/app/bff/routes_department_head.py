"""Department Head endpoints: aggregate view, confirmation queue, AI triage."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text
from datetime import datetime

from app.db import with_tenant
from app.modules.aggregator import service as agg
from app.modules.assistant import llm_client
from app.modules.assistant.prompts import prompt_for_role

router = APIRouter(prefix="/api/bff/dept-head", tags=["department_head"])


def _require_dept_head(request: Request) -> dict:
    claims = request.state.claims
    if claims["role"] != "department_head":
        raise HTTPException(403, "department_head role required")
    return claims


# ── Department aggregate overview ──────────────────────
@router.get("/overview")
async def dept_overview(request: Request):
    claims = _require_dept_head(request)
    async with with_tenant(claims["facility_id"], role="department_head", user_id=claims["sub"]) as session:
        # Get dept from user record
        row = (await session.execute(text("""
            SELECT primary_department FROM users WHERE id = :id
        """), {"id": claims["sub"]})).mappings().first()
        if not row or not row["primary_department"]:
            raise HTTPException(400, "department head has no department assigned")
        dept = row["primary_department"]

        # Aggregate for this dept only
        groups = (await session.execute(text("""
            SELECT shift, day, n, avg_fatigue, avg_heat, avg_score, p90_score, critical_share
            FROM agg_logs
            WHERE facility_id = :f AND department = :d
            ORDER BY day DESC, shift
        """), {"f": claims["facility_id"], "d": dept})).mappings().all()

        # Confirmation queue
        queue = (await session.execute(text("""
            SELECT id, worker_username, worker_display_name, fatigue, heat_exposure,
                   shift, ai_verdict, ai_reasoning, status, created_at
            FROM fatigue_confirmations
            WHERE facility_id = :f AND department = :d
            ORDER BY status DESC, created_at DESC LIMIT 50
        """), {"f": claims["facility_id"], "d": dept})).mappings().all()

        # 30-day trend
        trend = (await session.execute(text("""
            SELECT date_trunc('day', created_at) AS day,
                   avg(risk_score)::numeric(5,1) AS avg_wvi,
                   count(*) AS reports
            FROM logs
            WHERE facility_id = :f AND department = :d
              AND created_at >= now() - interval '30 days'
            GROUP BY 1 ORDER BY 1
        """), {"f": claims["facility_id"], "d": dept})).mappings().all()

    pool = 0.0
    if groups:
        total = sum(g["n"] for g in groups)
        pool = sum(float(g["p90_score"]) * g["n"] for g in groups) / total if total else 0

    return {
        "department": dept,
        "facility_id": claims["facility_id"],
        "pooled_wvi": round(pool, 1),
        "pooled_level": "Critical" if pool >= 65 else "Moderate" if pool >= 35 else "Low",
        "groups": [dict(g) | {"day": g["day"].isoformat()} for g in groups],
        "confirmation_queue": [dict(q) | {"created_at": q["created_at"].isoformat()} for q in queue],
        "pending_count": sum(1 for q in queue if q["status"] == "pending"),
        "trend": [
            {"day": t["day"].strftime("%a %d"), "wvi": float(t["avg_wvi"]),
             "reports": t["reports"]} for t in trend
        ],
    }


# ── AI verdict on each pending confirmation ────────────
@router.post("/analyze-queue")
async def analyze_queue(request: Request):
    """Run AI triage on all pending fatigue confirmations for this department."""
    claims = _require_dept_head(request)
    async with with_tenant(claims["facility_id"], role="department_head", user_id=claims["sub"]) as session:
        dept = (await session.execute(text(
            "SELECT primary_department FROM users WHERE id = :id"), {"id": claims["sub"]})).scalar()

        pending = (await session.execute(text("""
            SELECT id, worker_username, fatigue, heat_exposure, shift, created_at
            FROM fatigue_confirmations
            WHERE facility_id = :f AND department = :d AND status = 'pending'
            ORDER BY created_at DESC LIMIT 10
        """), {"f": claims["facility_id"], "d": dept})).mappings().all()

        results = []
        for p in pending:
            # Get worker's 7-day history for context
            hist = (await session.execute(text("""
                SELECT fatigue, heat_exposure, created_at
                FROM logs WHERE facility_id = :f AND department = :d
                  AND worker_id_hash = (SELECT worker_id_hash FROM logs
                                        WHERE facility_id = :f AND department = :d
                                        ORDER BY created_at DESC LIMIT 1)
                  AND created_at >= now() - interval '7 days'
                ORDER BY created_at DESC LIMIT 7
            """), {"f": claims["facility_id"], "d": dept})).mappings().all()

            hist_summary = ", ".join(f"{h['fatigue']}" for h in hist) or "no history"

            # Ask the LLM to judge
            try:
                prompt = f"""Department Head is reviewing a fatigue report.

Worker: {p['worker_username']}
Current report: Fatigue {p['fatigue']}/10, Heat {p['heat_exposure']}/10, shift={p['shift']}
Their last 7 reports' fatigue values: {hist_summary}

Return ONLY a JSON object with these keys:
{{"verdict": "likely_real"|"outlier"|"uncertain", "reasoning": "<1 sentence>"}}

Rules:
- likely_real: current matches or is close to their history
- outlier: current is >3 points above their average (possible data error or off-duty submit)
- uncertain: less than 2 history entries to compare"""

                res = await llm_client.chat([{"role": "user", "content": prompt}])
                import json
                content = res["message"]["content"].strip()
                if content.startswith("```"):
                    content = content.split("```")[1].replace("json", "").strip()
                verdict_data = json.loads(content)
            except Exception:
                # Deterministic fallback based on history
                try:
                    fatigue_values = [int(h["fatigue"]) for h in hist]
                except Exception:
                    fatigue_values = []
                if len(fatigue_values) < 2:
                    verdict_data = {"verdict": "uncertain",
                                    "reasoning": "Not enough history to judge"}
                elif p["fatigue"] > (sum(fatigue_values) / len(fatigue_values)) + 3:
                    verdict_data = {"verdict": "outlier",
                                    "reasoning": "Fatigue is 3+ points above their recent average"}
                else:
                    verdict_data = {"verdict": "likely_real",
                                    "reasoning": "Fatigue matches their recent history"}

            # Save verdict
            await session.execute(text("""
                UPDATE fatigue_confirmations
                SET ai_verdict = :v, ai_reasoning = :r
                WHERE id = :id
            """), {"v": verdict_data["verdict"], "r": verdict_data["reasoning"], "id": p["id"]})

            results.append({
                "id": str(p["id"]), "worker": p["worker_username"],
                "verdict": verdict_data["verdict"], "reasoning": verdict_data["reasoning"],
            })

    return {"analyzed": len(results), "results": results}


# ── Confirm/deny a specific report ────────────────────
class ConfirmPayload(BaseModel):
    action: str  # confirm / deny
    notes: str | None = None


@router.post("/confirm/{confirmation_id}")
async def confirm_report(confirmation_id: str, payload: ConfirmPayload, request: Request):
    claims = _require_dept_head(request)
    if payload.action not in ("confirm", "deny"):
        raise HTTPException(400, "action must be 'confirm' or 'deny'")

    new_status = "confirmed" if payload.action == "confirm" else "denied"
    async with with_tenant(claims["facility_id"], role="department_head", user_id=claims["sub"]) as session:
        await session.execute(text("""
            UPDATE fatigue_confirmations
            SET status = :s, confirmed_by = :by, confirmed_at = now(), notes = :n
            WHERE id = :id AND facility_id = :f
        """), {"s": new_status, "by": claims["sub"], "n": payload.notes,
               "id": confirmation_id, "f": claims["facility_id"]})
    return {"ok": True, "status": new_status}


# ── 1-on-1 check-in action ─────────────────────────────
@router.post("/checkin/{confirmation_id}")
async def schedule_checkin(confirmation_id: str, request: Request):
    claims = _require_dept_head(request)
    async with with_tenant(claims["facility_id"], role="department_head", user_id=claims["sub"]) as session:
        await session.execute(text("""
            UPDATE fatigue_confirmations SET notes = COALESCE(notes,'') || ' [1-on-1 scheduled] '
            WHERE id = :id
        """), {"id": confirmation_id})
    return {"ok": True}
