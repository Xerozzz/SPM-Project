"""HTTP endpoints for the Technical Support equipment catalogue (SCRUM-84)."""

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import require_role
from domain.equipment import EquipmentFields
from domain.roles import Role
from schemas.equipment import EquipmentCreate, EquipmentProblemRead, EquipmentRead, EquipmentUpdate
from services import equipment as service

router = APIRouter(prefix="/equipment", tags=["equipment"])

TechnicalSupport = Annotated[dict[str, object], Depends(require_role(Role.TECH_SUPPORT))]
Db = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[EquipmentRead])
def list_catalogue(user: TechnicalSupport, db: Db) -> list[EquipmentRead]:
    """Show Technical Support Staff the current equipment catalogue."""
    del user
    return [EquipmentRead.model_validate(row) for row in service.list_all(db)]


@router.post("", response_model=EquipmentRead, status_code=status.HTTP_201_CREATED)
def create(body: EquipmentCreate, user: TechnicalSupport, db: Db) -> EquipmentRead:
    """Add one validated equipment entry to the catalogue."""
    del user
    return _save(lambda: service.create(db, EquipmentFields(**body.model_dump())))


@router.put("/{equipment_id}", response_model=EquipmentRead)
def update(
    equipment_id: uuid.UUID, body: EquipmentUpdate, user: TechnicalSupport, db: Db
) -> EquipmentRead:
    """Edit one existing catalogue entry while retaining its identity."""
    del user
    return _save(lambda: service.update(db, equipment_id, EquipmentFields(**body.model_dump())))


@router.post("/{equipment_id}/deactivate", response_model=EquipmentRead)
def deactivate(equipment_id: uuid.UUID, user: TechnicalSupport, db: Db) -> EquipmentRead:
    """Remove an entry from active catalogues without deleting its stored record."""
    del user
    return _save(lambda: service.deactivate(db, equipment_id))


def _save(action: Callable[[], object]) -> EquipmentRead:
    """Serialise the catalogue service's shared validation and identity errors."""
    try:
        return EquipmentRead.model_validate(action())
    except service.EquipmentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Equipment not found") from exc
    except service.DuplicateEquipmentError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Equipment with this type and location already exists",
        ) from exc
    except service.InvalidEquipmentError as exc:
        problems = [EquipmentProblemRead(field=p.field, reason=p.reason) for p in exc.problems]
        raise HTTPException(422, [problem.model_dump() for problem in problems]) from exc
