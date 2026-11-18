"""AI intervention generator. Takes patterns → one creative, specific action.

Cached per worker for 10 minutes. Falls back to a deterministic bank if
LLM fails. Never diagnoses. Never prescribes. Always ONE action.
"""
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from hashlib import md5
from app.modules.assistant import llm_client

_CACHE: dict[str, tuple[dict, datetime]] = {}
CACHE_TTL = timedelta(minutes=10)

_SYSTEM = (
    "You are an occupational health AI coach for Kenyan healthcare workers. "
    "Look at the patterns in their cognitive wellness data and propose ONE "
    "specific, creative, doable intervention.\n\n"
    "ABSOLUTE RULES:\n"
    "1. Never diagnose any medical condition.\n"
    "2. Never use clinical terms (burnout, depression, anxiety disorder).\n"
    "3. Be SPECIFIC — not 'take a break'. Instead: 'Before your 6am shift, "
    "stand outside in the cool morning air for 3 minutes without your phone. "
    "Notice 3 sounds.'\n"
    "4. Fit their context: Kenyan healthcare worker, shift work, on your feet, "
    "limited time, phone-based.\n"
    "5. Prefer behavioral + environmental over supplements or apps.\n"
    "6. Keep it warm but not infantilizing.\n\n"
    "Respond ONLY with JSON (no prose, no code fences):\n"
    '{"title":"<max 8 words>","why":"<1 sentence tying to their pattern>",'
    '"how":"<3 short steps, concrete>","duration":"<e.g. 3 min before shift>",'
    '"evidence_hint":"<one line, no citations needed>"}'
)

_BANK = {
    "sleep_debt_streak": {
        "title": "The 10-minute wind-down",
        "why": "Your sleep has been consistently short — small routines extend it.",
        "how": "1) 1 hour before bed, dim your phone. 2) For 3 minutes, name 5 textures you touched today. 3) Keep a paper and pen beside the bed.",
        "duration": "10 min before sleep",
        "evidence_hint": "Sleep hygiene, cognitive wind-down",
    },
    "stress_escalation": {
        "title": "The 90-second reset",
        "why": "Your stress readings climbed steadily this period.",
        "how": "1) Find a window or doorway. 2) Inhale 4 counts through nose, exhale 6 through mouth, 5 times. 3) Name 3 things you can see clearly.",
        "duration": "90 seconds",
        "evidence_hint": "Vagal breathing",
    },
    "clarity_crash": {
        "title": "The 4-minute walk",
        "why": "Your mental clarity dropped vs. your own baseline — movement restores it.",
        "how": "1) Step outside or into a corridor. 2) Walk at easy pace. 3) Count 5 things that are blue or green.",
        "duration": "4 min",
        "evidence_hint": "Attention restoration",
    },
    "correlated_crash": {
        "title": "One small anchor",
        "why": "Low sleep + high mental fatigue are showing up together.",
        "how": "1) Tonight, pick ONE routine to protect: shower, tea, or a call. 2) Do only that one. 3) Skip the rest without guilt.",
        "duration": "Tonight",
        "evidence_hint": "Routine-preserving behaviors",
    },
    "night_shift_penalty": {
        "title": "The dawn light rule",
        "why": "Your mental fatigue is higher on night shifts.",
        "how": "1) After your last night shift, get 15 min of daylight before sleeping. 2) Use sunglasses on the commute home. 3) Dim your room fully before bed.",
        "duration": "Post-shift ritual",
        "evidence_hint": "Circadian light exposure",
    },
    "worsening_trend": {
        "title": "The named conversation",
        "why": "Your signals trended upward — naming this with a supervisor prevents isolation.",
        "how": "1) Before your next shift, tell your supervisor: 'My energy has been dropping.' 2) Ask for one small accommodation. 3) Write down their reply.",
        "duration": "2 min before shift",
        "evidence_hint": "Social buffering of stress",
    },
    "default": {
        "title": "The 60-second curiosity break",
        "why": "Small scheduled breaks maintain cognitive performance across a shift.",
        "how": "1) Set a 60-second timer. 2) Sit or stand still. 3) Count breaths without changing them.",
        "duration": "60 sec",
        "evidence_hint": "Micro-break research",
    },
}


def _key(worker_hash: str) -> str:
    return md5(worker_hash.encode()).hexdigest()


def invalidate_cache(worker_hash: str) -> None:
    _CACHE.pop(_key(worker_hash), None)


async def generate_intervention(*, worker_hash: str, patterns: dict,
                                latest_cwi: float | None = None) -> dict:
    k = _key(worker_hash)
    now = datetime.now(timezone.utc)
    if k in _CACHE:
        cached, ts = _CACHE[k]
        if now - ts < CACHE_TTL:
            return cached

    plist = patterns.get("patterns", [])
    if not plist:
        out = {"source": "deterministic", "pattern_type": None, **_BANK["default"]}
        _CACHE[k] = (out, now)
        return out

    top = plist[0]
    ptxt = "\n".join(f"- [{p['severity']}] {p['type']}: {p['label']}" for p in plist[:5])
    prompt = (_SYSTEM + "\n\nPatterns (" + str(patterns.get("days_analyzed", 0)) + " days):\n"
              + ptxt + "\n\nLatest CWI: " + str(latest_cwi) + "\n\nReturn JSON only.")

    try:
        res = await llm_client.chat([{"role": "user", "content": prompt}])
        c = res["message"]["content"].strip()
        if c.startswith("```"):
            c = c.split("```")[1]
            if c.startswith("json"):
                c = c[4:]
            c = c.strip()
        data = json.loads(c)
        out = {"source": "ai", "pattern_type": top["type"], **data}
        _CACHE[k] = (out, now)
        return out
    except Exception:
        out = {"source": "fallback", "pattern_type": top["type"],
               **_BANK.get(top["type"], _BANK["default"])}
        _CACHE[k] = (out, now)
        return out
