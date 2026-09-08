"""The get_db dependency. Creating a Session does not open a connection, so this is a
genuine unit test: it never touches PostgreSQL."""

import pytest
from sqlalchemy.orm import Session

from core.database import get_db


@pytest.mark.story("US-0")
def test_get_db_yields_a_session_and_closes_it_afterwards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions = get_db()
    session = next(sessions)

    assert isinstance(session, Session)

    # get_db closes in a finally, so the close has to survive the caller being done with
    # the generator. Recording the call is the only way to prove the finally ran, since
    # a Session exposes no public "am I closed" flag.
    closes: list[str] = []
    monkeypatch.setattr(session, "close", lambda: closes.append("closed"))

    with pytest.raises(StopIteration):
        next(sessions)

    assert closes == ["closed"]
