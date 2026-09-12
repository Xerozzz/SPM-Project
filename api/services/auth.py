"""Sign-in orchestration. Verifies credentials, issues JWTs with role claims."""

from core.database import Session
from core.security import create_access_token, verify_password
from repositories import users as users_repo
from schemas.auth import LoginResponse


class InvalidCredentialsError(Exception):
    """Raised for bad email or bad password alike — never say which one failed."""


# bcrypt.hashpw(b"unknown-account", bcrypt.gensalt(rounds=12)) — the same cost as our real
# hashes. Checked when the email is unknown, so a failed sign-in takes the same time whether
# or not the account exists; otherwise the faster answer for unknown emails would let
# anyone enumerate accounts. The input is public, so this is not a secret.
_UNKNOWN_ACCOUNT_HASH = "$2b$12$mER4LzyusdZfb3IG06OluOnZGJpeSUlCBz4YYXQdtu5O2HbZ7Rf1i"


def sign_in(db: Session, email: str, password: str) -> LoginResponse:
    """Authenticate a supplied user and return a bearer token with role claims."""
    user = users_repo.get_by_email(db, email)
    if user is None:
        verify_password(password, _UNKNOWN_ACCOUNT_HASH)
        raise InvalidCredentialsError
    if not verify_password(password, user.password_hash):
        raise InvalidCredentialsError
    token = create_access_token(str(user.id), list(user.roles))
    return LoginResponse(access_token=token, roles=list(user.roles))
