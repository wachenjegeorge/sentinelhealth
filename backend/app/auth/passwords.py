"""PBKDF2-SHA256 password hashing. Stdlib only, no external dependencies.

Storage format: pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

ITERATIONS = int(os.getenv("PASSWORD_ITERATIONS", "200000"))


def hash_password(password: str, iterations: int | None = None) -> str:
    it = iterations or ITERATIONS
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, it, 32)
    return "pbkdf2_sha256${}${}${}".format(
        it,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(dk).decode("ascii"),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iter_str, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iter_str)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, 32)
        return hmac.compare_digest(expected, actual)
    except (ValueError, TypeError):
        return False
