"""Password hashing and JWT handling for F1 sign-in.

Supplied users only; no registration. Generic errors live in the service layer so
this module never discloses whether an account exists.
"""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from core.config import get_settings

_ALGORITHM = "HS256"

# bcrypt hashes only the first 72 bytes of its input. What it does with the rest depends
# on the version: 4.x silently truncates, 5.x raises ValueError. requirements.txt allows
# both, so the limit is enforced here rather than left to whichever version pip resolved —
# on 4.x, an 80-byte password that shares its first 72 bytes with the real one would
# otherwise verify.
_BCRYPT_MAX_PASSWORD_BYTES = 72


def hash_password(plain: str) -> str:
    """Hash a password with bcrypt. Refuses input bcrypt would silently truncate."""
    encoded = plain.encode("utf-8")
    if len(encoded) > _BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError(f"password exceeds bcrypt's {_BCRYPT_MAX_PASSWORD_BYTES}-byte limit")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Check a plain password against its hash.

    A password over the bcrypt limit is simply a wrong password. Answering that way here,
    before bcrypt sees it, keeps the generic-401 promise of ADR-0005 on every supported
    bcrypt version instead of relying on 5.x's ValueError.
    """
    encoded = plain.encode("utf-8")
    if len(encoded) > _BCRYPT_MAX_PASSWORD_BYTES:
        return False
    return bcrypt.checkpw(encoded, hashed.encode("utf-8"))


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
