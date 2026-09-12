"""Sign-in orchestration. Verifies credentials, issues JWTs with role claims."""

from sqlalchemy.orm import Session

from core.security import create_access_token, verify_password
from repositories import users as users_repo
from schemas.auth import LoginResponse


class InvalidCredentialsError(Exception):
    """Raised for bad email or bad password alike — never say which one failed."""


def sign_in(db: Session, email: str, password: str) -> LoginResponse:
    """Authenticate a supplied user and return a bearer token with role claims."""
    user = users_repo.get_by_email(db, email)
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError
    token = create_access_token(str(user.id), list(user.roles))
    return LoginResponse(access_token=token, roles=list(user.roles))
