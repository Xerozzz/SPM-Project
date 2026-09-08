"""The get_db dependency. Creating a Session does not open a connection, so this is a
genuine unit test: it never touches PostgreSQL."""

import pytest
from sqlalchemy.orm import Session

from core.database import get_db


@pytest.mark.story("US-0")
def test_get_db_yields_a_session_and_closes_it_afterwards() -> None:
    sessions = get_db()
    session = next(sessions)

    assert isinstance(session, Session)

    with pytest.raises(StopIteration):
        next(sessions)

    assert not session.in_transaction()
