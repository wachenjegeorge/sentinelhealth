"""Worker cognitive baseline + patterns + AI intervention + supervisor queue."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text

from app.db import with_tenant
from app.modules.cognitive.service import compute_baseline
from app.modules.cognitive import patterns as pattern_svc
from app.modules.cognitive import interventions as intervention_svc
from app.security import hash_worker_id

router = APIRouter(prefix="/api/bff/cognitive", tags=["cognitive"])


# ── WORKER: baseline ─────────────────────────────────────
@router.get("/baseline")
async def my_baseline(request: Request):
    claims = request.state.claims
    if claims["role"] != "worker":
        raise HTTPException(403, "worker role required")
    worker_hash = hash_worker_id(claims["username"])

    async with with_tenant(claims["facility_id"], role="worker",
                           user_id=claims["sub"]) as session:
        baseline = await compute_baseline(session, worker_hash=worker_hash)
        today = (await session.execute(text("""
            SELECT cwi, cwi_level, cognitive_fatigue, mental_clarity,
                   stress, sleep_quality, sleep_hours, created_at
            FROM logs WHERE worker_id_hash = :h AND cwi IS NOT NULL
            ORDER BY created_at DESC LIMIT 1
        """), {"h": worker_hash})).mappings().first()

        deltas = {}
        if baseline["ready"] and today:
            b = baseline["baseline"]
            for key in ("cognitive_fatigue","mental_clarity","stress",
                        "sleep_quality","sleep_hours","cwi"):
                if today[key] is not None and b.get(key) is not None:
                    deltas[key] = round(float(today[key]) - float(b[key]), 2)

        return {
            "ready": baseline["ready"], "sample_count": baseline["sample_count"],
            "min_samples": baseline["min_samples"], "window_days": baseline["window_days"],
            "baseline": baseline["baseline"],
            "today": dict(today) | {"created_at": today["created_at"].isoformat()} if today else None,
            "deltas": deltas,
        }


# ── WORKER: patterns ─────────────────────────────────────
@router.get("/patterns")
async def my_patterns(request: Request):
    claims = request.state.claims
    if claims["role"] != "worker":
        raise HTTPException(403, "worker role required")
    worker_hash = hash_worker_id(claims["username"])
    async with with_tenant(claims["facility_id"], role="worker",
                           user_id=claims["sub"]) as session:
        return await pattern_svc.detect_patterns(session, worker_hash=worker_hash)


# ── WORKER: AI intervention ──────────────────────────────
@router.get("/intervention")
async def my_intervention(request: Request):
    claims = request.state.claims
    if claims["role"] != "worker":
        raise HTTPException(403, "worker role required")
    worker_hash = hash_worker_id(claims["username"])
    async with with_tenant(claims["facility_id"], role="worker",
                           user_id=claims["sub"]) as session:
        report = await pattern_svc.detect_patterns(session, worker_hash=worker_hash)
    intervention = await intervention_svc.generate_intervention(
        worker_hash=worker_hash, patterns=report,
        latest_cwi=report.get("latest_cwi"))
    return {"patterns": report.get("patterns", []),
            "days_analyzed": report.get("days_analyzed", 0),
            "intervention": intervention}


class InterventionFeedback(BaseModel):
    action: str
    note: str | None = None


@router.post("/intervention/feedback")
async def intervention_feedback(payload: InterventionFeedback, request: Request):
    claims = request.state.claims
    if claims["role"] != "worker":
        raise HTTPException(403, "worker role required")
    if payload.action not in ("accept", "skip"):
        raise HTTPException(400, "action must be accept or skip")
    worker_hash = hash_worker_id(claims["username"])
    async with with_tenant(claims["facility_id"], role="worker",
                           user_id=claims["sub"]) as session:
        from app.audit import append_audit
        await append_audit(
            session, facility_id=claims["facility_id"],
            actor=worker_hash[:12], role="worker",
            action=f"intervention.{payload.action}",
            resource="cognitive_intervention",
            detail={"note": payload.note} if payload.note else {})
    intervention_svc.invalidate_cache(worker_hash)
    return {"ok": True, "action": payload.action}


# ── WORKER: cheap live status (polling) ──────────────────
@router.get("/live")
async def live_status(request: Request):
    claims = request.state.claims
    if claims["role"] != "worker":
        raise HTTPException(403, "worker role required")
    worker_hash = hash_worker_id(claims["username"])
    async with with_tenant(claims["facility_id"], role="worker",
                           user_id=claims["sub"]) as session:
        row = (await session.execute(text("""
            SELECT count(*) AS n,
                   max(created_at) AS last_at,
                   (SELECT count(*) FROM cognitive_confirmations
                    WHERE worker_id_hash = :h AND status = 'pending') AS pending
            FROM logs WHERE worker_id_hash = :h AND cwi IS NOT NULL
        """), {"h": worker_hash})).mappings().first()
    return {
        "checkin_count": int(row["n"] or 0),
        "last_checkin_at": row["last_at"].isoformat() if row["last_at"] else None,
        "pending_escalations": int(row["pending"] or 0),
    }


# ── SUPERVISOR: cognitive queue ──────────────────────────
@router.get("/queue")
async def cognitive_queue(request: Request):
    claims = request.state.claims
    role = claims["role"]
    if role not in ("department_head","hospital_head","county_officer","admin"):
        raise HTTPException(403, "supervisor role required")
    async with with_tenant(claims["facility_id"], role=role,
                           user_id=claims["sub"]) as session:
        rows = (await session.execute(text("""
            SELECT id, department, worker_username, cwi, cwi_level,
                   cognitive_fatigue, mental_clarity, stress,
                   sleep_quality, sleep_hours, status, created_at
            FROM cognitive_confirmations
            WHERE facility_id = :f AND status = 'pending'
            ORDER BY cwi DESC, created_at DESC LIMIT 50
        """), {"f": claims["facility_id"]})).mappings().all()
    return {"queue": [dict(r) | {"created_at": r["created_at"].isoformat()} for r in rows]}


class ConfirmPayload(BaseModel):
    action: str
    notes: str | None = None


@router.post("/confirm/{confirmation_id}")
async def confirm_cognitive(confirmation_id: str, payload: ConfirmPayload, request: Request):
    claims = request.state.claims
    role = claims["role"]
    if role not in ("department_head","hospital_head"):
        raise HTTPException(403, "supervisor role required")
    if payload.action not in ("confirm","deny"):
        raise HTTPException(400, "action must be confirm or deny")
    new_status = "confirmed" if payload.action == "confirm" else "denied"

    async with with_tenant(claims["facility_id"], role=role,
                           user_id=claims["sub"]) as session:
        row = (await session.execute(text("""
            SELECT log_id FROM cognitive_confirmations
            WHERE id = :id AND facility_id = :f
        """), {"id": confirmation_id, "f": claims["facility_id"]})).mappings().first()
        if not row:
            raise HTTPException(404, "confirmation not found")

        await session.execute(text("""
            UPDATE cognitive_confirmations
            SET status = :s, confirmed_by = :by, confirmed_at = now(), notes = :n
            WHERE id = :id
        """), {"s": new_status, "by": claims["sub"], "n": payload.notes,
               "id": confirmation_id})

        if row["log_id"]:
            await session.execute(text("""
                UPDATE logs SET verification_status = :v,
                                verified_by = :by, verified_at = now()
                WHERE id = :lid
            """), {"v": new_status, "by": claims["sub"], "lid": row["log_id"]})

    return {"ok": True, "status": new_status}
