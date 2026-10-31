"""Orchestrator: tries LLM, falls back to deterministic, records messages."""
from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assistant import agent, deterministic


async def ask(session: AsyncSession, *, question: str, role: str,
              facility_id: str, user_id: str,
              county_hint: str | None = None) -> dict:
    # Layer 2 first (if Ollama is reachable). The agent returns None on
    # any failure, which triggers Layer 1.
    llm = await agent.run(session, question, role, county_hint)
    if llm and "answer" in llm:
        result = llm
    else:
        result = await deterministic.answer(session, question, role, county_hint)
        if llm and "_rejected" in llm:
            result["verifier_rejected"] = llm["_rejected"]

    # Persist conversation + message
    conv_id = uuid.uuid4()
    await session.execute(text("""
        INSERT INTO assistant_conversations (id, facility_id, user_id, role)
        VALUES (:id, :f, :u, :r)
    """), {"id": str(conv_id), "f": facility_id, "u": user_id, "r": role})
    msg_id = (await session.execute(text("""
        INSERT INTO assistant_messages
            (conversation_id, role, content, tool_calls, tool_results,
             engine, verified, refusal_reason)
        VALUES (:c, 'assistant', :content, :tc, :tr, :e, :v, :rr)
        RETURNING id
    """), {
        "c": str(conv_id), "content": result["answer"],
        "tc": __import__("json").dumps(result.get("tool_calls", [])),
        "tr": __import__("json").dumps(result.get("tool_results", [])),
        "e": result["engine"], "v": result["verified"],
        "rr": result.get("refusal_reason"),
    })).scalar()

    result["conversation_id"] = str(conv_id)
    result["message_id"] = msg_id
    return result
