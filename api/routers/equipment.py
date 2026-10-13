"""HTTP endpoints for the Technical Support equipment catalogue (SCRUM-84)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import require_role
from domain.equipment import EquipmentFields
from domain.roles import Role
from schemas.equipment import EquipmentCreate, EquipmentProblemRead, EquipmentRead
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
    try:
        return EquipmentRead.model_validate(
            service.create(db, EquipmentFields(**body.model_dump()))
        )
    except service.DuplicateEquipmentError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Equipment with this type and location already exists",
        ) from exc
    except service.InvalidEquipmentError as exc:
        problems = [EquipmentProblemRead(field=p.field, reason=p.reason) for p in exc.problems]
        raise HTTPException(422, [problem.model_dump() for problem in problems]) from exc
