from datetime import date as date_cls
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from app.db import with_tenant
from app.modules.assistant import service as assistant
from app.modules.aggregator import service as agg

router = APIRouter(prefix="/api/bff/assistant", tags=["assistant"])


class AskPayload(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class FeedbackPayload(BaseModel):
    message_id: int
    rating: int = Field(ge=1, le=5)
    correction: str | None = Field(default=None, max_length=1000)


class OutcomePayload(BaseModel):
    county: str
    department: str
    shift: str
    day: str
    outcome: str
    notes: str | None = None


@router.post("/ask")
async def ask(payload: AskPayload, request: Request):
    claims = request.state.claims
    async with with_tenant(claims["facility_id"], role=claims["role"]) as session:
        county = (await session.execute(text(
            "SELECT county FROM facilities WHERE id = :id"),
            {"id": claims["facility_id"]})).scalar()
        return await assistant.ask(
            session, question=payload.question, role=claims["role"],
            facility_id=claims["facility_id"], user_id=claims["sub"],
            county_hint=county)


@router.post("/feedback")
async def feedback(payload: FeedbackPayload, request: Request):
    claims = request.state.claims
    async with with_tenant(claims["facility_id"], role=claims["role"]) as session:
        await session.execute(text("""
            INSERT INTO assistant_feedback
                (message_id, facility_id, user_id, rating, correction)
            VALUES (:m, :f, :u, :r, :c)
        """), {"m": payload.message_id, "f": claims["facility_id"],
               "u": claims["sub"], "r": payload.rating, "c": payload.correction})
    return {"ok": True}


@router.post("/outcome")
async def outcome(payload: OutcomePayload, request: Request):
    claims = request.state.claims
    if claims["role"] != "health_officer":
        raise HTTPException(403, "health_officer role required")

    # asyncpg requires a real date object for Date columns; a plain string
    # raises "'str' object has no attribute 'toordinal'".
    try:
        day_obj = date_cls.fromisoformat(payload.day)
    except ValueError:
        raise HTTPException(422, "day must be YYYY-MM-DD")

    if payload.outcome not in {"intervention", "adverse_event", "no_event", "unknown"}:
        raise HTTPException(422, "invalid outcome value")

    async with with_tenant(claims["facility_id"], role=claims["role"]) as session:
        county = (await session.execute(text(
            "SELECT county FROM facilities WHERE id = :id"),
            {"id": claims["facility_id"]})).scalar()

        overview = await agg.overview(session)
        cell = next((g for g in overview["groups"]
                     if g["county"] == county
                     and g["department"] == payload.department
                     and g["shift"] == payload.shift), None)
        predicted_wvi = cell["p90_score"] if cell else 0.0
        predicted_level = (
            "Critical" if predicted_wvi >= 65
            else "Moderate" if predicted_wvi >= 35
            else "Low" if predicted_wvi > 0 else "Unknown")

        await session.execute(text("""
            INSERT INTO risk_outcomes
                (facility_id, county, department, shift, day,
                 predicted_wvi, predicted_level, outcome, recorded_by, notes)
            VALUES (:f, :c, :d, :s, :day, :wvi, :lvl, :o, :u, :n)
        """), {"f": claims["facility_id"], "c": county,
               "d": payload.department, "s": payload.shift, "day": day_obj,
               "wvi": predicted_wvi, "lvl": predicted_level,
               "o": payload.outcome, "u": claims["sub"], "n": payload.notes})
    return {"ok": True, "predicted_wvi": predicted_wvi,
            "predicted_level": predicted_level}
