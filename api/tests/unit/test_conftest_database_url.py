"""The test-database rewrite every test run relies on (tests/conftest.py)."""

import pytest

from tests.conftest import derive_test_database_url


@pytest.mark.story("SCRUM-46")
def test_development_database_gets_a_test_suffix() -> None:
    url = "postgresql+psycopg://user:secret@db:5432/connectsphere"

    assert (
        derive_test_database_url(url)
        == "postgresql+psycopg://user:secret@db:5432/connectsphere_test"
    )


@pytest.mark.story("SCRUM-46")
def test_an_existing_test_database_is_left_alone() -> None:
    url = "postgresql+psycopg://ci:ci@localhost:5432/connectsphere_test"

    assert derive_test_database_url(url) == url


@pytest.mark.story("SCRUM-46")
def test_credentials_and_host_are_preserved() -> None:
    url = "postgresql+psycopg://custom_user:p%40ss@otherhost:5433/mydb"

    assert (
        derive_test_database_url(url)
        == "postgresql+psycopg://custom_user:p%40ss@otherhost:5433/mydb_test"
    )
