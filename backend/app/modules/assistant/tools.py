"""Six read-only tools. None returns individual worker rows."""
from __future__ import annotations
import json
from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.aggregator import service as agg

# Knowledge base
KB = {
    "heat_illness": {
        "source": "OSHA Heat NPRM (2024) / NIOSH REL",
        "passage": (
            "At or above the high-heat trigger (90F heat index, or WBGT at the "
            "NIOSH REL), OSHA proposes a minimum 15-minute paid rest break at "
            "least every two hours, plus observation for signs of heat illness "
            "via a buddy system or heat-safety coordinator."
        ),
        "tags": ["heat", "rest", "break", "wbgt", "osha", "hydration"],
    },
    "heat_rest_schedule": {
        "source": "Oregon OSHA OAR 437-002-0156 Table 2",
        "passage": (
            "Minimum simplified rest-break durations by heat index: "
            "90F or greater - 10 min every 2 hours; 95F or greater - 20 min "
            "every hour; 100F or greater - 30 min every hour; 105F or greater - "
            "40 min every hour. Rest must be in shade, not performing work."
        ),
        "tags": ["heat", "schedule", "rest", "temperature", "threshold"],
    },
    "acclimatization": {
        "source": "CDC/NIOSH - Heat Acclimatization",
        "passage": (
            "New and returning workers should follow the 20% rule: 20% of "
            "normal heat exposure on day one, increased by roughly 20% each "
            "subsequent day. Full acclimatization takes 5-7 days."
        ),
        "tags": ["acclimatization", "new", "worker", "return", "first", "day"],
    },
    "fatigue_protocol": {
        "source": "Kenya MoH HRH Strategy / OSHA Fatigue Management",
        "passage": (
            "To respond to fatigue: 1) Enforce a hard stop at 16 hours of continuous work. "
            "2) Cap consecutive night shifts at 2. 3) Insert 15-minute protected micro-breaks "
            "every 4 hours. 4) Reassign safety-critical tasks (like dispensing meds or driving) "
            "to non-fatigued staff if fatigue levels exceed 8/10."
        ),
        "tags": ["fatigue", "respond", "manage", "protocol", "tired", "exhaustion", "handle", "burnout"],
    },
    "burnout_kenya": {
        "source": "Kenya MoH National Guidelines on Workplace Mental Wellness (Oct 2024)",
        "passage": (
            "Kenya's Ministry of Health issued National Guidelines on Workplace "
            "Mental Wellness in October 2024, aimed at preventing excessive "
            "workload and mitigating occupational burnout among health "
            "professionals and trainees. County Health Management Teams are "
            "responsible for implementation."
        ),
        "tags": ["burnout", "mental", "kenya", "moh", "wellness", "stress", "fatigue"],
    },
    "nurse_burnout": {
        "source": "HRMARS - Burnout in Nurses at a Referral Hospital in Western Kenya",
        "passage": (
            "A previous Kenyan study reported burnout prevalence among nurses "
            "as high as 95%, though the authors note the need for larger, "
            "multi-site studies to confirm the figure. Prolonged occupational "
            "stress is the strongest predictor."
        ),
        "tags": ["burnout", "nurse", "kenya", "prevalence", "stress"],
    },
    "fatigue_error": {
        "source": "Reimagining Workforce Well-Being (Cultura, 2024)",
        "passage": (
            "As fatigue accumulates, cognitive precision and decision-making "
            "capacity decline, increasing occupational injury risk and clinical "
            "error. Compromised physical vitality directly correlates with "
            "reduced care quality and increased burnout vulnerability."
        ),
        "tags": ["fatigue", "error", "decision", "cognitive", "safety"],
    },
    "keph_levels": {
        "source": "Kenya KEPH 2024",
        "passage": (
            "Level 4 (sub-county hospital) serves ~100,000 people with inpatient, "
            "outpatient, surgery, lab, radiology, and emergency care. Level 5 "
            "(county referral) serves ~1,000,000 people with advanced specialist "
            "care and is the referral centre for Level 4 facilities."
        ),
        "tags": ["keph", "level", "facility", "referral", "hospital"],
    },
    "staffing_density": {
        "source": "Kenya Quality of Care (QOC) 2024",
        "passage": (
            "National core health personnel density is 15.6 per 10,000, below "
            "the WHO threshold of 23. Only 6 of 47 counties meet the threshold. "
            "Nurses: 10.1 per 10,000. Clinical officers: 3.2. Doctors: 0.89."
        ),
        "tags": ["staffing", "density", "who", "nurse", "doctor", "shortage"],
    },
}

def _cit(result: dict, cite: str) -> dict:
    return {"cite": cite, **result}

async def get_dashboard_snapshot(session: AsyncSession, **_) -> dict:
    data = await agg.overview(session)
    return _cit({
        "pooled_wvi": data["pooled_wvi"],
        "pooled_level": data["pooled_level"],
        "county_count": data["county_count"],
        "group_count": data["group_count"],
        "counties": data["counties"][:10],
        "departments": _rank_departments(data["groups"]),
    }, "live-dashboard")

def _rank_departments(groups: list[dict]) -> list[dict]:
    agg: dict[str, dict] = {}
    for g in groups:
        d = agg.setdefault(g["department"], {"total": 0.0, "weight": 0})
        d["total"] += g["p90_score"] * g["reported"]
        d["weight"] += g["reported"]
    return sorted(
        [{"department": k, "wvi": round(v["total"] / v["weight"], 1),
          "reported": v["weight"]} for k, v in agg.items()],
        key=lambda x: -x["wvi"],
    )

async def get_county_detail(session: AsyncSession, county: str = "", **_) -> dict:
    if not county: return _cit({"error": "county parameter required"}, "live-dashboard")
    data = await agg.overview(session)
    match = next((c for c in data["counties"] if c["county"].lower() == county.lower()), None)
    if not match:
        return _cit({"error": f"no data for county '{county}'", "available": [c["county"] for c in data["counties"]]}, "live-dashboard")
    depts = [g for g in data["groups"] if g["county"].lower() == county.lower()]
    return _cit({"county": match, "departments": depts}, "live-dashboard")

async def explain_risk(session: AsyncSession, county: str = "", department: str = "", **_) -> dict:
    data = await agg.overview(session)
    cells = [g for g in data["groups"]
             if (not county or g["county"].lower() == county.lower())
             and (not department or g["department"].lower() == department.lower())]
    if not cells: return _cit({"error": "no group clears k>=5 for that filter"}, "live-dashboard")
    return _cit({"cells": cells[:5]}, "live-dashboard")

async def search_knowledge_base(session: AsyncSession, query: str = "", **_) -> dict:
    if not query: return _cit({"results": []}, "knowledge-base")
    q = query.lower()
    scored = []
    for key, entry in KB.items():
        score = sum(1 for tag in entry["tags"] if tag in q)
        if score: scored.append((score, entry))
    scored.sort(key=lambda x: -x[0])
    return _cit({"query": query, "results": [e for _, e in scored[:3]]}, "knowledge-base")

async def get_risk_outcome_history(session: AsyncSession, county: str = "", **_) -> dict:
    rows = (await session.execute(text("""
        SELECT county, department, shift, day, predicted_wvi, predicted_level, outcome
        FROM risk_outcomes WHERE (:c = '' OR county = :c)
        ORDER BY day DESC LIMIT 30
    """), {"c": county})).mappings().all()
    return _cit({"count": len(rows), "outcomes": [dict(r) | {"day": str(r["day"])} for r in rows]}, "risk-outcomes")

async def list_facilities_in_county(session: AsyncSession, county: str = "", **_) -> dict:
    rows = (await session.execute(text("""
        SELECT id, name, keph_level, facility_type FROM facilities
        WHERE county = :c AND active = true ORDER BY keph_level DESC, name
    """), {"c": county})).mappings().all()
    return _cit({"county": county, "facilities": [dict(r) for r in rows]}, "facility-registry")

TOOL_SCHEMAS: list[dict] = [
    {"type": "function", "function": {"name": "get_dashboard_snapshot", "description": "Return current pooled WVI, top counties, department ranking.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_county_detail", "description": "Return one county's WVI and per-department breakdown.", "parameters": {"type": "object", "required": ["county"], "properties": {"county": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "explain_risk", "description": "Return component scores behind a county/department cell.", "parameters": {"type": "object", "properties": {"county": {"type": "string"}, "department": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "search_knowledge_base", "description": "Search curated occupational-health passages (OSHA, NIOSH, Kenya MoH).", "parameters": {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "get_risk_outcome_history", "description": "Return historical predicted-vs-actual outcomes for a county.", "parameters": {"type": "object", "properties": {"county": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "list_facilities_in_county", "description": "List facilities in a county.", "parameters": {"type": "object", "required": ["county"], "properties": {"county": {"type": "string"}}}}},
]

REGISTRY = {
    "get_dashboard_snapshot": get_dashboard_snapshot,
    "get_county_detail": get_county_detail,
    "explain_risk": explain_risk,
    "search_knowledge_base": search_knowledge_base,
    "get_risk_outcome_history": get_risk_outcome_history,
    "list_facilities_in_county": list_facilities_in_county,
}

ROLE_ALLOWLIST = {"health_officer": set(REGISTRY), "worker": {"search_knowledge_base"}, "admin": set(REGISTRY)}

async def dispatch(name: str, args: dict, session: AsyncSession, role: str) -> dict:
    if name not in REGISTRY: return {"error": f"unknown tool: {name}", "cite": "tool-registry"}
    if name not in ROLE_ALLOWLIST.get(role, set()): return {"error": f"tool '{name}' not permitted for role '{role}'", "cite": "tool-registry"}
    try:
        return await REGISTRY[name](session, **args)
    except TypeError as e:
        return {"error": f"bad arguments: {e}", "cite": name}
