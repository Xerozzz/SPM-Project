"""Shared authorisation dependencies. Routers use these; never inline role checks."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError

from core.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict[str, object]:
    """Return the JWT claims, or 401 when missing or invalid."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        return decode_access_token(credentials.credentials)
    except PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        ) from exc


def require_role(*allowed: str) -> Callable[[dict[str, object]], dict[str, object]]:
    """Dependency factory: allow only tokens carrying one of the given roles."""

    def check(
        user: Annotated[dict[str, object], Depends(get_current_user)],
    ) -> dict[str, object]:
        roles = user.get("roles", [])
        if not isinstance(roles, list) or not any(r in roles for r in allowed):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return user

    return check
