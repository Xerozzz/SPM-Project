"""The event request repository: the only code that queries the event_requests table."""

import uuid

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from models.event_request import EventRequest
from models.user import User
from repositories import event_requests as repo
from tests.integration.test_submit_event_request import MakeUser, make_draft


@pytest.mark.story("SCRUM-46")
def test_get_returns_the_row_or_none(db: Session, make_user: MakeUser) -> None:
    draft = make_draft(db, make_user("organiser"))

    assert repo.get(db, draft.id) is draft
    assert repo.get(db, uuid.uuid4()) is None


@pytest.mark.story("SCRUM-46")
def test_get_for_update_queries_when_row_is_already_in_identity_map(
    db: Session, make_user: MakeUser
) -> None:
    draft = make_draft(db, make_user("organiser"))
    assert db.get(EventRequest, draft.id) is draft
    statements: list[str] = []

    def record_statement(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del connection, cursor, parameters, context, executemany
        statements.append(statement)

    connection = db.connection()
    event.listen(connection, "before_cursor_execute", record_statement)
    try:
        assert repo.get_for_update(db, draft.id) is draft
    finally:
        event.remove(connection, "before_cursor_execute", record_statement)

    assert any("FOR UPDATE" in statement.upper() for statement in statements)


@pytest.mark.story("SCRUM-46")
def test_add_stages_a_new_row(db: Session, make_user: MakeUser) -> None:
    organiser: User = make_user("organiser")

    request = repo.add(db, EventRequest(organiser_id=organiser.id, name="Staged"))
    db.flush()

    assert repo.get(db, request.id) is request
    assert repo.list_for_organiser(db, organiser.id) == [request]


@pytest.mark.story("SCRUM-46")
def test_delete_removes_the_row(db: Session, make_user: MakeUser) -> None:
    organiser: User = make_user("organiser")
    draft = make_draft(db, organiser)

    repo.delete(db, draft)
    db.flush()

    assert repo.get(db, draft.id) is None
    assert repo.list_for_organiser(db, organiser.id) == []
