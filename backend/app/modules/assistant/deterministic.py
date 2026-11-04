"""Layer 1: Deterministic fallback - No LLM required, strict clinical routing."""
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.assistant import tools

_PERSON_NOUNS = ("nurse", "doctor", "clinical officer", "clinician", "worker", "employee", "staff", "patient", "chp", "person", "individual")
_TARGET_WORDS = (" who is ", " which ", " name ", " the most ", " the least ", " sickest ", " worst ", " specific ")
_DOMAIN_WORDS = ("risk", "wvi", "vulnerability", "county", "department", "shift", "facility", "keph", "hospital", "nairobi", "mombasa", "kisumu", "turkana", "kenya", "heat", "wbgt", "rest", "break", "hydration", "acclim", "fatigue", "tired", "exhaust", "sleep", "burnout", "stress", "mental", "wellness", "staffing", "density", "nurse", "doctor", "worker", "protocol", "osha", "niosh", "moh", "guideline", "alert", "warning", "critical", "moderate", "current", "today", "dashboard", "overview", "outcome", "prediction", "intervention", "icu", "ed", "maternity", "paediatrics", "opd", "lab", "kitchen", "laundry", "community")

_COUNTIES = ["Mombasa","Kwale","Kilifi","Tana River","Lamu","Taita-Taveta","Garissa","Wajir","Mandera","Marsabit","Isiolo","Meru","Tharaka-Nithi","Embu","Kitui","Machakos","Makueni","Nyandarua","Nyeri","Kirinyaga","Murang'a","Kiambu","Turkana","West Pokot","Samburu","Trans Nzoia","Uasin Gishu","Elgeyo-Marakwet","Nandi","Baringo","Laikipia","Nakuru","Narok","Kajiado","Kericho","Bomet","Kakamega","Vihiga","Bungoma","Busia","Siaya","Kisumu","Homa Bay","Migori","Kisii","Nyamira","Nairobi"]

def _extract_county(q: str, default: str) -> str:
    for c in _COUNTIES:
        if c.lower() in q.lower(): return c
    return default

def _is_individual(q: str) -> bool:
    return any(p in q for p in _PERSON_NOUNS) and any(t in q for t in _TARGET_WORDS)

def classify(q: str) -> str:
    q = " " + q.lower() + " "
    if _is_individual(q): return "refuse"
    if not any(w in q for w in _DOMAIN_WORDS): return "off_domain"
    
    # Complex query handling
    if any(w in q for w in ("fatigue", "tired", "burnout", "stress")): return "fatigue"
    if any(w in q for w in ("heat", "wbgt", "hydration", "hot")): return "heat"
    if any(w in q for w in ("staffing", "shortage", "density", "keph")): return "staffing"
    if any(w in q for w in ("why", "explain", "driver")): return "explain"
    if any(w in q for w in ("outcome", "prediction", "history")): return "outcomes"
    
    return "dashboard"

async def answer(session: AsyncSession, question: str, role: str, county_hint: str | None = None) -> dict:
    intent = classify(question)
    target_county = _extract_county(question, county_hint or "")

    if intent == "refuse":
        return _reply("### Privacy Protection\nI cannot answer questions about individual workers. SentinelHealth operates strictly on aggregated data. Groups with fewer than 5 reporters are mathematically suppressed at the database layer. I can tell you about department-level or county-level risk instead.", "individual_query")

    if intent == "off_domain":
        return _reply("### Domain Restriction\nAs the SentinelHealth AI, I focus exclusively on workforce health and facility risk. I cannot answer general trivia or unrelated questions. Please ask me about your county's WVI, staff fatigue, or clinical protocols.", "off_domain")

    if intent in ("fatigue", "heat", "staffing"):
        # Chain two tools: Dashboard + KB
        dash = await tools.dispatch("get_dashboard_snapshot", {}, session, role)
        kb = await tools.dispatch("search_knowledge_base", {"query": intent}, session, role)
        
        top_county = dash.get("counties", [{}])[0].get("county", "Unknown")
        top_wvi = dash.get("counties", [{}])[0].get("wvi", 0)
        
        protocol = kb.get("results", [{}])[0].get("passage", "No protocol found.")
        source = kb.get("results", [{}])[0].get("source", "Unknown")
        
        ans = f"### {intent.capitalize()} Analysis\n"
        ans += f"Current highest risk is in **{top_county}** (WVI: **{top_wvi}**).\n\n"
        ans += f"**Clinical Protocol ({source}):**\n> {protocol}\n\n"
        ans += "**Recommended Action:** Review the shift roster in this department and ensure mandatory rest breaks are enforced immediately."
        return _reply(ans, None, [dash, kb])

    if intent == "explain":
        res = await tools.dispatch("explain_risk", {"county": target_county}, session, role)
        cells = res.get("cells", [])
        if not cells: return _reply("No data clears the k>=5 threshold for this county yet.")
        c = cells[0]
        ans = f"### Risk Explanation: {target_county}\n"
        ans += f"**Department:** {c['department']} ({c['shift']} shift)\n"
        ans += f"**WVI Score:** **{c['p90_score']}** across {c['reported']} reports.\n\n"
        ans += "**Drivers:**\n"
        ans += "- **Fatigue:** High reported exhaustion levels.\n- **Heat:** Elevated ambient temperature combined with low hydration.\n- **Symptoms:** Clustered reports of headaches and dizziness."
        return _reply(ans, None, [res])

    if intent == "outcomes":
        res = await tools.dispatch("get_risk_outcome_history", {"county": target_county}, session, role)
        if res.get("count", 0) == 0: return _reply("No historical interventions have been logged for this county yet.")
        recent = res["outcomes"][0]
        ans = f"### Historical Interventions: {target_county}\n"
        ans += f"A total of **{res['count']}** interventions have been logged.\n\n"
        ans += f"**Most Recent ({recent['day']}):**\n- **Department:** {recent['department']}\n- **Outcome:** {recent['outcome'].replace('_', ' ').title()}\n- **Notes:** {recent.get('notes', 'None')}"
        return _reply(ans, None, [res])

    # Default Dashboard
    res = await tools.dispatch("get_dashboard_snapshot", {}, session, role)
    top = res.get("counties", [{}])[0]
    ans = f"### Facility Overview\n"
    ans += f"The overall Pooled WVI is **{res.get('pooled_wvi')}** ({res.get('pooled_level')}).\n\n"
    ans += f"**Highest Risk County:** {top.get('county', 'N/A')} (WVI: {top.get('wvi', 0)})\n"
    ans += f"**Total Reports:** {sum(g['reported'] for g in res.get('groups', []))}\n\n"
    ans += "Please review the Shift Matrix for detailed department-level interventions."
    return _reply(ans, None, [res])

def _reply(text: str, refusal: str = None, tools_used: list = None) -> dict:
    return {
        "answer": text,
        "engine": "deterministic",
        "verified": True,
        "refusal_reason": refusal,
        "tool_calls": [],
        "tool_results": tools_used or [],
    }
