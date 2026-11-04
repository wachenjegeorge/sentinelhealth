"""Layer 2: Groq agent loop."""
from __future__ import annotations
import json
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.assistant import llm_client, tools, verifier

SYSTEM_PROMPT = """You are the SentinelHealth AI Co-Pilot, an expert in workforce health, 
occupational safety, and public health surveillance for Kenyan healthcare providers.

YOUR GOAL:
Provide comprehensive, actionable, and highly professional answers to the Health Officer.
You have access to real-time facility data via tools. You MUST use these tools to ground every answer.

RULES OF ENGAGEMENT:
1. TOOL CALLING: You must call at least one tool before answering. For complex questions, 
   chain multiple tools (e.g., check dashboard -> explain risk -> search protocol).
2. STRICT DOMAIN FILTER: You ONLY answer questions related to workforce health, facility risk, 
   medical protocols, or Kenyan health data. If the user asks an off-topic question (e.g., 
   coding, politics, general trivia), you must politely decline and say: 
   "As the SentinelHealth AI, I focus exclusively on workforce health and facility risk. 
   Please ask me about your county's WVI, staff fatigue, or clinical protocols."
3. PRIVACY: Never mention individual workers. You operate on aggregated k-anonymity (k>=5).
4. NO HALLUCINATION: Every number (WVI, fatigue score, count) MUST come from a tool result.

FORMATTING:
- Use Markdown. 
- Use **bold** for key metrics (e.g., **WVI 45.2**).
- Use bullet points for lists (e.g., recommended interventions).
- Use headers (###) to structure long answers.
- Be authoritative, concise, and clinical in tone.
"""

MAX_STEPS = 4

async def run(session: AsyncSession, question: str, role: str,
              county_hint: str | None = None) -> dict | None:
    if not await llm_client.is_available():
        return None

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question
            + (f"\n(Context: The user is the Health Officer for {county_hint} County)" if county_hint else "")},
    ]
    tool_results: list[dict] = []

    for _ in range(MAX_STEPS):
        try:
            resp = await llm_client.chat(messages, tools=tools.TOOL_SCHEMAS)
        except Exception as e:
            import traceback
            print(f"LLM CHAT FAILED: {type(e).__name__} - {e}")
            traceback.print_exc()
            return None

        msg = resp.get("message", {})
        calls = msg.get("tool_calls") or []

        if not calls:
            draft = msg.get("content", "").strip()
            if not draft:
                return None
            if not tool_results:
                return None # Must call tools
            ok, reason = verifier.verify(draft, tool_results)
            if not ok:
                return {"_rejected": reason, "_draft": draft}
            return {
                "answer": draft, "engine": "groq", "verified": True,
                "refusal_reason": None,
                "tool_calls": [{"name": m["function"]["name"], "args": m["function"]["arguments"]} for m in messages if "tool_calls" in m for m in m["tool_calls"]],
                "tool_results": tool_results,
            }

        messages.append(msg)
        for call in calls:
            fn = call["function"]
            name = fn["name"]
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            result = await tools.dispatch(name, args, session, role)
            tool_results.append(result)
            messages.append({
                "role": "tool", "tool_name": name,
                "content": json.dumps(result)[:6000],
            })

    return None
