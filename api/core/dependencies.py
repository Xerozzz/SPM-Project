"""Shared authorisation dependencies. Routers use these; never inline role checks."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError

from core.security import decode_access_token
from domain.roles import Role

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


def require_role(*allowed: Role) -> Callable[[dict[str, object]], dict[str, object]]:
    """Dependency factory: allow only tokens carrying one of the given roles.

    Takes `Role` members, not strings, so a misspelt role fails at import time rather than
    as a 403 nobody can explain.
    """
    allowed_values = {role.value for role in allowed}

    def check(
        user: Annotated[dict[str, object], Depends(get_current_user)],
    ) -> dict[str, object]:
        # Only string elements count as roles. The claim is ours and signed, but a malformed
        # one (say, `roles: [{}]`) must still be a 403, not a TypeError from set arithmetic.
        claimed = user.get("roles")
        granted = (
            {role for role in claimed if isinstance(role, str)}
            if isinstance(claimed, list)
            else set()
        )
        if not allowed_values & granted:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return user

    return check
