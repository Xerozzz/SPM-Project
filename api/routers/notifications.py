"""Notification inbox endpoints for SCRUM-99.

Thin by rule: parse, authorise, delegate, serialise. The recipient is the signed
token's subject — never a path or query parameter — so isolation holds even if the
browser sends someone else's id.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import get_current_user
from schemas.notifications import NotificationRead
from services import notifications as service

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

SignedIn = Annotated[dict[str, object], Depends(get_current_user)]
Db = Annotated[Session, Depends(get_db)]

_REFUSALS: dict[type[service.NotificationError], tuple[int, str]] = {
    service.NotificationNotFoundError: (status.HTTP_404_NOT_FOUND, "Notification not found"),
}


def _recipient_id(user: dict[str, object]) -> uuid.UUID:
    """The JWT subject is the user's id (see core/security.py)."""
    return uuid.UUID(str(user["sub"]))


@router.get("", response_model=list[NotificationRead])
def list_inbox(db: Db, user: SignedIn) -> list[NotificationRead]:
    """The caller's own notifications, newest first."""
    rows = service.list_inbox(db, _recipient_id(user))
    return [NotificationRead.model_validate(row) for row in rows]


@router.post("/{notification_id}/viewed", response_model=NotificationRead)
def mark_viewed(notification_id: uuid.UUID, db: Db, user: SignedIn) -> NotificationRead:
    """Mark one owned notification viewed; a repeated mark keeps the first time."""
    try:
        row = service.mark_viewed(db, notification_id, _recipient_id(user), datetime.now(UTC))
    except service.NotificationError as error:
        code, message = _REFUSALS[type(error)]
        raise HTTPException(status_code=code, detail=message) from error
    return NotificationRead.model_validate(row)
