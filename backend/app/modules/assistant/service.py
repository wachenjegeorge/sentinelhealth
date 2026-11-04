"""Orchestrator: tries LLM, falls back to deterministic, records messages."""
from __future__ import annotations
import uuid, json, traceback
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.assistant import agent, deterministic

_CACHE = {}
import hashlib, time

async def ask(session: AsyncSession, *, question: str, role: str,
              facility_id: str, user_id: str,
              county_hint: str | None = None) -> dict:
    
    cache_key = hashlib.md5(f"{facility_id}:{question}".encode()).hexdigest()
    if cache_key in _CACHE:
        cached_data, timestamp = _CACHE[cache_key]
        if time.time() - timestamp < 300: # 5 minutes
            return cached_data

    result = None
    verifier_rejected = None

    # Layer 2: Groq LLM
    try:
        llm = await agent.run(session, question, role, county_hint)
        if llm and "answer" in llm:
            result = llm
        elif llm and "_rejected" in llm:
            verifier_rejected = llm["_rejected"]
    except Exception as e:
        # Log the error, but don't crash - fall through to deterministic
        print("LLM FAILED:", str(e))
        traceback.print_exc()

    # Layer 1: Deterministic fallback (always works)
    if not result:
        result = await deterministic.answer(session, question, role, county_hint)
        if verifier_rejected:
            result["verifier_rejected"] = verifier_rejected

    # Persist conversation
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
        "tc": json.dumps(result.get("tool_calls", [])),
        "tr": json.dumps(result.get("tool_results", [])),
        "e": result["engine"], "v": result["verified"],
        "rr": result.get("refusal_reason"),
    })).scalar()

    result["conversation_id"] = str(conv_id)
    result["message_id"] = msg_id
    
    return result
