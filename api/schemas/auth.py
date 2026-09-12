"""Auth request/response models — the public contract for F1 sign-in."""

from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Credentials supplied by the sign-in form."""

    # Plain str, not pydantic's EmailStr: that would add the email-validator dependency
    # (an ADR), and the lookup is an exact match against supplied accounts anyway.
    email: str
    password: str


class LoginResponse(BaseModel):
    """JWT plus the role claims the UI uses for gating."""

    access_token: str
    roles: list[str]
    # A real field, not a @property: a property is invisible to serialisation, so the UI's
    # LoginResponse type promised a token_type the API never actually sent. It is the OAuth2
    # scheme label, not a secret — Field(default=...) rather than a bare literal only so the
    # bandit rule for hard-coded tokens (S105) does not mistake it for one.
    token_type: Literal["bearer"] = Field(default="bearer")
