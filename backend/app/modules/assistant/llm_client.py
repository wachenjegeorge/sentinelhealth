import os
from typing import Any
import httpx

API_KEY = os.getenv("GROQ_API_KEY", "").strip()
BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")

# Fallback chain: try the newest recommended model first, then older working models
MODEL_CHAIN = [
    os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
    "openai/gpt-oss-20b",
    "qwen/qwen3.6-27b",
    "llama-3.1-8b-instant",
]
TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)

async def chat(messages: list[dict], tools: list[dict] | None = None) -> dict:
    if not API_KEY:
        raise ValueError("GROQ_API_KEY is missing")

    last_error = None
    for model in MODEL_CHAIN:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 2500,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as c:
                r = await c.post(
                    f"{BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                
                if r.status_code == 429:
                    raise RuntimeError("groq rate limited")
                if r.status_code != 200:
                    # If model not found (404), try the next model in the chain
                    if r.status_code == 404:
                        last_error = f"Model {model} not found"
                        continue
                    raise RuntimeError(f"Groq Error {r.status_code}: {r.text}")
                    
                data = r.json()

            choice = data["choices"][0]
            msg = choice.get("message") or {}

            normalized: dict[str, Any] = {
                "role": "assistant",
                "content": msg.get("content") or "",
            }
            if msg.get("tool_calls"):
                # Groq/OpenAI require id + type when assistant message is
                # sent back in a subsequent turn. Preserve them verbatim.
                normalized["tool_calls"] = [
                    {
                        "id": tc.get("id") or f"call_{i}",
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"],
                        },
                    }
                    for i, tc in enumerate(msg["tool_calls"])
                ]
            return {"message": normalized}
        except Exception as e:
            last_error = str(e)
            continue

    raise RuntimeError(f"All models failed. Last error: {last_error}")

async def is_available() -> bool:
    return bool(API_KEY)
