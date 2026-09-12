"""The event request repository: the only code that queries the event_requests table."""

import uuid

import pytest
from sqlalchemy.orm import Session

from models.user import User
from repositories import event_requests as repo
from tests.integration.test_submit_event_request import MakeUser, make_draft


@pytest.mark.story("SCRUM-46")
def test_get_returns_the_row_or_none(db: Session, make_user: MakeUser) -> None:
    draft = make_draft(db, make_user("organiser"))

    assert repo.get(db, draft.id) is draft
    assert repo.get(db, uuid.uuid4()) is None


@pytest.mark.story("SCRUM-46")
def test_delete_removes_the_row(db: Session, make_user: MakeUser) -> None:
    organiser: User = make_user("organiser")
    draft = make_draft(db, organiser)

    repo.delete(db, draft)
    db.flush()

    assert repo.get(db, draft.id) is None
    assert repo.list_for_organiser(db, organiser.id) == []
