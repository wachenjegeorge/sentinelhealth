import hashlib, hmac
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from app.config import settings


def hash_worker_id(worker_id: str) -> str:
    return hmac.new(settings.worker_id_pepper.encode(),
                    worker_id.strip().upper().encode(), hashlib.sha256).hexdigest()


def issue_token(user_id: str, username: str, role: str,
                facility_id: str, ttl_minutes: int = 720) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({
        "sub": user_id, "username": username, "role": role,
        "facility_id": facility_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl_minutes)).timestamp()),
    }, settings.jwt_secret, algorithm="HS256")


def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError as exc:
        raise ValueError("invalid token") from exc
