"""Layer 2: Groq agent loop."""
from __future__ import annotations
import json
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.assistant import llm_client, tools, verifier
from app.modules.assistant.prompts import prompt_for_role


MAX_STEPS = 4

async def run(session: AsyncSession, question: str, role: str,
              county_hint: str | None = None) -> dict | None:
    if not await llm_client.is_available():
        return None

    messages: list[dict] = [
        {"role": "system", "content": prompt_for_role(role)},
        {"role": "user", "content": question
            + (f"\n(Context: the user's role is '{role}', facility is '{county_hint or 'unknown'}')")},
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
