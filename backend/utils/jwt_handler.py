from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from config import settings


def create_access_token(user_id: str, email: str) -> str:
    expires = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": user_id,
        "email": email,
        "exp": expires,
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    expires = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "sub": user_id,
        "exp": expires,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Optional[dict]:
    """Returns payload dict or None if invalid/expired."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError:
        return None


def get_user_id_from_token(token: str) -> Optional[str]:
    payload = decode_token(token)
    if payload and payload.get("type") == "access":
        return payload.get("sub")
    return None
