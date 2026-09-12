"""Password hashing and JWT handling for F1 sign-in.

Supplied users only; no registration. Generic errors live in the service layer so
this module never discloses whether an account exists.
"""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from core.config import get_settings

_ALGORITHM = "HS256"


def hash_password(plain: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Check a plain password against its hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(subject: str, roles: list[str]) -> str:
    """Issue a JWT with subject and role claims, expiring per settings."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "roles": roles,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expiry_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict[str, object]:
    """Decode a JWT, raising jwt.PyJWTError on expiry or tampering."""
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
