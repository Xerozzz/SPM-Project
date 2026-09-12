"""Auth request/response models — the public contract for F1 sign-in."""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """Credentials supplied by the sign-in form."""

    email: str
    password: str


class LoginResponse(BaseModel):
    """JWT plus the role claims the UI uses for gating."""

    access_token: str
    roles: list[str]

    @property
    def token_type(self) -> str:
        """OAuth2 bearer scheme label the UI sends back in the Authorization header."""
        return "bearer"
