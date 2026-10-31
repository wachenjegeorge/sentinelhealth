"""Layer 1: deterministic intent routing - no LLM, cannot hallucinate."""
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.assistant import tools

_PERSON_NOUNS = (
    "nurse", "doctor", "clinical officer", "clinician", "worker",
    "employee", "staff", "patient", "chp", "community health promoter",
    "person", "individual", "someone", "colleague", "member",
)
_TARGET_WORDS = (
    " who ", " which ", " name ", " the most ", " the least ",
    " sickest ", " worst ", " best ", " most exhausted ",
    " most stressed ", " most fatigued ", " most tired ",
    " specific ", " particular ", " exactly ",
)
_DOMAIN_WORDS = (
    "risk", "wvi", "vulnerability", "county", "counties", "department",
    "shift", "facility", "keph", "hospital", "nairobi", "mombasa", "kisumu",
    "turkana", "mandera", "wajir", "garissa", "kenya",
    "heat", "wbgt", "rest", "break", "hydration", "acclim",
    "fatigue", "tired", "exhaust", "sleep",
    "burnout", "stress", "mental", "wellness",
    "staffing", "density", "nurse", "doctor", "worker", "chp",
    "protocol", "osha", "niosh", "moh", "guideline", "standard",
    "alert", "warning", "critical", "moderate", "low", "high",
    "current", "today", "now", "live", "recent", "past",
    "dashboard", "overview", "situation", "summary",
    "outcome", "prediction", "accuracy", "intervention",
    "icu", "ed", "maternity", "paediatrics", "opd", "laboratory",
    "kitchen", "laundry", "community",
)


def _is_individual_query(q: str) -> bool:
    has_person = any(noun in q for noun in _PERSON_NOUNS)
    has_target = any(t in q for t in _TARGET_WORDS)
    if has_person and has_target:
        return True
    explicit = (
        "who is", "who was", "name of", "name the",
        "tell me about the worker", "tell me about the nurse",
        "tell me about the doctor", "the specific",
        "individual worker", "individual nurse", "individual doctor",
    )
    return any(x in q for x in explicit)


def _is_off_domain(q: str) -> bool:
    return not any(w in q for w in _DOMAIN_WORDS)


def classify(question: str) -> str:
    q = " " + question.lower() + " "
    if _is_individual_query(q):
        return "refuse_individual"
    if _is_off_domain(q):
        return "off_domain"
    if any(w in q for w in ("why", "explain", "driver", "cause", "component")):
        return "explain_risk"
    if any(w in q for w in ("heat", "wbgt", "rest break", "acclimat", "hydration",
                            "osha", "niosh")):
        return "search_knowledge_base"
    if any(w in q for w in ("burnout", "mental", "wellness", "kenya moh",
                            "guideline", "protocol")):
        return "search_knowledge_base"
    if any(w in q for w in ("keph", "level 4", "level 5", "referral",
                            "facility structure")):
        return "list_facilities_in_county"
    if any(w in q for w in ("accuracy", "prediction", "past alert",
                            "outcome", "did it work")):
        return "get_risk_outcome_history"
    return "get_dashboard_snapshot"


async def answer(session: AsyncSession, question: str, role: str,
                 county_hint: str | None = None) -> dict:
    intent = classify(question)

    if intent == "refuse_individual":
        return {
            "answer": (
                "I cannot answer questions about individual workers. SentinelHealth "
                "operates on aggregated data only - groups with fewer than 5 reporters "
                "are suppressed at the database layer, so no individual record is ever "
                "available to me. I can tell you about department-level or county-level "
                "risk instead."
            ),
            "engine": "deterministic", "verified": True,
            "refusal_reason": "individual_query",
            "tool_calls": [], "tool_results": [],
        }

    if intent == "off_domain":
        return {
            "answer": (
                "I'm the SentinelHealth assistant. I only answer questions about "
                "workforce risk, occupational health protocols, KEPH facility structure, "
                "and Kenya health-workforce data. Your question doesn't touch any of "
                "those topics, so I have nothing grounded to say. Try asking about "
                "current risk in your county, heat-rest protocols, or health worker "
                "burnout guidance."
            ),
            "engine": "deterministic", "verified": True,
            "refusal_reason": "off_domain",
            "tool_calls": [], "tool_results": [],
        }

    if intent == "search_knowledge_base":
        result = await tools.dispatch(
            "search_knowledge_base", {"query": question}, session, role)
        if not result.get("results"):
            return _polite_gap(
                "I don't have a curated knowledge-base passage on that specific topic.")
        top = result["results"][0]
        return _ok(
            answer=f"From {top['source']}: {top['passage']}",
            tool_name="search_knowledge_base", result=result)

    if intent == "explain_risk":
        result = await tools.dispatch(
            "explain_risk", {"county": county_hint or ""}, session, role)
        cells = result.get("cells", [])
        if not cells:
            return _polite_gap(
                "Not enough aggregated data (k>=5) to explain risk for that filter yet.")
        c = cells[0]
        return _ok(
            answer=(
                f"{c['county']} / {c['department']} ({c['shift']}) has a WVI of "
                f"{c['p90_score']} across {c['reported']} reporters. The score is the "
                f"p90 of individual check-in scores in that group, driven by fatigue, "
                f"heat exposure, symptoms, staffing strain, and biometric drift."
            ),
            tool_name="explain_risk", result=result)

    if intent == "list_facilities_in_county":
        if not county_hint:
            return _polite_gap("Which county would you like the facility list for?")
        result = await tools.dispatch(
            "list_facilities_in_county", {"county": county_hint}, session, role)
        names = [f"{f['name']} (L{f['keph_level']})" for f in result["facilities"]]
        return _ok(
            answer=f"Facilities in {county_hint}: " + "; ".join(names),
            tool_name="list_facilities_in_county", result=result)

    if intent == "get_risk_outcome_history":
        result = await tools.dispatch(
            "get_risk_outcome_history", {"county": county_hint or ""}, session, role)
        if result["count"] == 0:
            return _polite_gap(
                "No outcome records recorded yet. Officers record outcomes from the "
                "alert panel; the calibration report improves as data accumulates.")
        recent = result["outcomes"][0]
        return _ok(
            answer=(
                f"{result['count']} outcome records. Most recent: {recent['county']} / "
                f"{recent['department']} on {recent['day']} - predicted WVI "
                f"{recent['predicted_wvi']} ({recent['predicted_level']}), outcome "
                f"recorded as '{recent['outcome']}'."
            ),
            tool_name="get_risk_outcome_history", result=result)

    result = await tools.dispatch("get_dashboard_snapshot", {}, session, role)
    top = result["counties"][0] if result["counties"] else None
    top_dept = result["departments"][0] if result["departments"] else None
    if not top:
        return _polite_gap(
            "No county has at least 5 check-ins yet, so no aggregate can be shown.")
    return _ok(
        answer=(
            f"Pooled WVI is {result['pooled_wvi']} ({result['pooled_level']}). "
            f"Highest-risk county: {top['county']} at {top['wvi']} with "
            f"{top['reported']} reporters across {top['departments']} departments."
            + (f" Highest-risk department: {top_dept['department']} "
               f"({top_dept['wvi']})." if top_dept else "")
        ),
        tool_name="get_dashboard_snapshot", result=result)


def _ok(answer: str, tool_name: str, result: dict) -> dict:
    return {"answer": answer, "engine": "deterministic", "verified": True,
            "refusal_reason": None,
            "tool_calls": [{"name": tool_name, "args": {}}],
            "tool_results": [result]}


def _polite_gap(reason: str) -> dict:
    return {"answer": (
            f"{reason} This is a data gap, not a refusal. If the data should exist, "
            f"check that enough workers submitted check-ins for that group."
        ),
        "engine": "deterministic", "verified": True,
        "refusal_reason": "insufficient_data",
        "tool_calls": [], "tool_results": []}
