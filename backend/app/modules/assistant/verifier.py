"""Layer 3: verify that every factual claim in the answer is grounded
in a tool result.

Rule: every numeric token and every county name in the answer must
appear somewhere in the concatenated tool-results JSON. If not, the
answer is rejected and the deterministic fallback is used instead.
"""
from __future__ import annotations

import json
import re

COUNTIES = [
    "Mombasa","Kwale","Kilifi","Tana River","Lamu","Taita-Taveta","Garissa",
    "Wajir","Mandera","Marsabit","Isiolo","Meru","Tharaka-Nithi","Embu","Kitui",
    "Machakos","Makueni","Nyandarua","Nyeri","Kirinyaga","Murang'a","Kiambu",
    "Turkana","West Pokot","Samburu","Trans Nzoia","Uasin Gishu",
    "Elgeyo-Marakwet","Nandi","Baringo","Laikipia","Nakuru","Narok","Kajiado",
    "Kericho","Bomet","Kakamega","Vihiga","Bungoma","Busia","Siaya","Kisumu",
    "Homa Bay","Migori","Kisii","Nyamira","Nairobi",
]

NUM_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,2})?\b")


def verify(answer: str, tool_results: list[dict]) -> tuple[bool, str | None]:
    corpus = json.dumps(tool_results)

    # 1. Numeric claims must be present in the corpus.
    claimed_numbers = set(NUM_RE.findall(answer))
    # Exclude tiny numbers that are likely ordinals ("1", "2" in "1 of 3")
    claimed_numbers = {n for n in claimed_numbers if float(n) >= 5}
    for n in claimed_numbers:
        if n not in corpus and str(float(n)) not in corpus:
            return False, f"ungrounded number: {n}"

    # 2. Any county mentioned must appear in the corpus.
    for county in COUNTIES:
        if county in answer and county not in corpus:
            return False, f"ungrounded county: {county}"

    return True, None
