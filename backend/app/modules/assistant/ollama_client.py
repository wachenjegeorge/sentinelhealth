"""Async Ollama client. Tool calling via /api/chat. Graceful timeout."""
from __future__ import annotations

import json
from typing import Any

import httpx

OLLAMA_URL = "http://ollama:11434"
MODEL = "qwen2.5:3b"          # strong tool calling, small enough for 4GB
TIMEOUT = httpx.Timeout(connect=3.0, read=60.0, write=10.0, pool=3.0)


async def chat(messages: list[dict], tools: list[dict] | None = None) -> dict:
    payload: dict[str, Any] = {
        "model": MODEL, "messages": messages, "stream": False,
        "options": {"temperature": 0.1, "num_ctx": 4096},
    }
    if tools:
        payload["tools"] = tools
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(f"{OLLAMA_URL}/api/chat", json=payload)
        r.raise_for_status()
        return r.json()


async def is_available() -> bool:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(1.5)) as c:
            r = await c.get(f"{OLLAMA_URL}/api/tags")
            return r.status_code == 200
    except Exception:
        return False
