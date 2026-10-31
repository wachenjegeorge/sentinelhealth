"""Layer 2: Ollama agent loop, gated by availability and by the verifier.

Rules enforced here, not in the prompt alone:
  - The model MUST call at least one tool before producing a final answer.
  - The verifier checks every number and county before the answer is returned.
  - Any failure -> return None so the caller falls back to Layer 1.
"""
from __future__ import annotations

import json
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assistant import ollama_client, tools, verifier

SYSTEM_PROMPT = """You are SentinelHealth's analytical assistant for Kenyan
county health officers. You answer questions about workforce vulnerability
using ONLY the results of the tools you call.

ABSOLUTE RULES:
1. You MUST call at least one tool before answering. If you have not called
   a tool, you have nothing to say.
2. Never state a number, a county name, or a department name that did not
   appear in a tool result. No exceptions.
3. Never mention an individual worker. If asked, refuse and explain that
   the system operates on k-anonymized aggregates (k>=5).
4. If the tools return no relevant data, say so politely. A gap in the
   data is not a reason to guess.
5. Be concise: 2-3 sentences plus one concrete recommended action.
"""

MAX_STEPS = 4


async def run(session: AsyncSession, question: str, role: str,
              county_hint: str | None = None) -> dict | None:
    """Return a verified answer dict, or None to signal fallback."""
    if not await ollama_client.is_available():
        return None

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question
            + (f"\n(County context: {county_hint})" if county_hint else "")},
    ]
    tool_results: list[dict] = []

    for _ in range(MAX_STEPS):
        try:
            resp = await ollama_client.chat(messages, tools=tools.TOOL_SCHEMAS)
        except Exception:
            return None

        msg = resp.get("message", {})
        calls = msg.get("tool_calls") or []

        if not calls:
            draft = msg.get("content", "").strip()
            if not draft:
                return None
            if not tool_results:
                # Model tried to answer without calling a tool. Reject.
                return None
            ok, reason = verifier.verify(draft, tool_results)
            if not ok:
                return {"_rejected": reason, "_draft": draft}
            return {
                "answer": draft, "engine": "ollama", "verified": True,
                "refusal_reason": None,
                "tool_calls": [], "tool_results": tool_results,
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
