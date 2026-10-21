"""The seed can always put the sample events back in Draft (SCRUM-79).

This exists because the same defect has now shipped three times. The seed deletes the
sample event requests so a re-run starts clean, nothing else in the application ever
deletes one, and none of the foreign keys pointing at `event_requests` cascade. So every
story that adds a table referencing an event has to add it to the seed's clean-up list,
and three stories in a row did not:

* SCRUM-43's equipment requirements,
* SCRUM-53's reservations,
* SCRUM-79's safety reviews.

Each time the symptom was the same and nowhere near the cause: `docker compose up`
against an existing volume kills the API on startup with a ForeignKeyViolation, for
everyone except CI, which always starts from an empty volume and so never sees it.

The check is mechanical, which is the point. It fails the moment a new model gains an
`event_request_id`, in the story that adds it, rather than on a teammate's machine a week
later.
"""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import inspect

import models  # noqa: F401  (imported for its side effect: every model is registered)
from core.database import Base

#: `scripts/` sits beside `api/`, not inside it, so it is not on the import path the
#: suite runs with. Loading it by path keeps that true rather than widening the path
#: for one test.
_SEED = Path(__file__).resolve().parents[3] / "scripts" / "seed.py"


def _seed_dependents() -> tuple[type[Base], ...]:
    """The models `scripts/seed.py` clears before deleting an event request."""
    spec = importlib.util.spec_from_file_location("_seed_for_test", _SEED)
    assert spec is not None and spec.loader is not None, f"cannot load {_SEED}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dependents: tuple[type[Base], ...] = module._DEPENDENTS
    return dependents


def _models_pointing_at_an_event() -> set[str]:
    """Every mapped class with an `event_request_id`, by class name."""
    return {
        mapper.class_.__name__
        for mapper in Base.registry.mappers
        if "event_request_id" in {column.name for column in mapper.local_table.columns}
    }


@pytest.mark.story("SCRUM-79")
def test_every_table_pointing_at_an_event_is_cleared_by_the_seed() -> None:
    missing = _models_pointing_at_an_event() - {model.__name__ for model in _seed_dependents()}

    assert not missing, (
        f"{sorted(missing)} reference an event request but are not in the seed's "
        "_DEPENDENTS, so a second `docker compose up` against an existing volume will "
        "fail to reset the samples and the API will not start. Add them to _DEPENDENTS "
        "in scripts/seed.py, children before parents."
    )


@pytest.mark.story("SCRUM-79")
def test_the_seed_only_clears_rows_it_can_find_by_their_event() -> None:
    """`_delete_dependents` filters on `event_request_id`, so each entry must have one.

    A model without that column would raise at seed time rather than quietly skip, but
    only on a run that reaches the delete. This says so at test time instead.
    """
    without = [
        model.__name__
        for model in _seed_dependents()
        if "event_request_id" not in {column.name for column in inspect(model).local_table.columns}
    ]

    assert without == [], (
        f"{without} are in _DEPENDENTS but have no event_request_id for the seed to "
        "filter on. A row that hangs off one of these needs its own step in "
        "_delete_dependents, as the change items do."
    )
