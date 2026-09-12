"""Point every test at the `<database>_test` database — before anything reads settings.

This is the only thing the root conftest does, and it deliberately touches no database:
unit tests stay database-free. It rewrites DATABASE_URL so that `make test`, a bare
`pytest`, and CI (whose URL already ends in `_test`, and is therefore left alone) all use
a database separate from the one you are looking at in the browser, with whatever
credentials and host Compose was configured with. tests/integration/conftest.py then
creates and migrates that database and provides the session fixtures.
"""

import os

from sqlalchemy import make_url


def derive_test_database_url(url: str) -> str:
    """`.../connectsphere` -> `.../connectsphere_test`; a `_test` name is kept as-is."""
    parsed = make_url(url)
    name = parsed.database or "connectsphere"
    if not name.endswith("_test"):
        name = f"{name}_test"
    return parsed.set(database=name).render_as_string(hide_password=False)


os.environ["DATABASE_URL"] = derive_test_database_url(os.environ["DATABASE_URL"])
