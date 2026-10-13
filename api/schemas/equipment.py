"""HTTP contracts for equipment catalogue entries (SCRUM-84)."""

import uuid

from pydantic import BaseModel, ConfigDict


class EquipmentCreate(BaseModel):
    """Everything Technical Support Staff may supply when adding equipment."""

    equipment_type: str | None = None
    description: str | None = None
    # Keep invalid scalar JSON values intact so the domain validator can return the
    # catalogue's consistent {field, reason} error response.
    total_quantity: int | float | str | bool | None = None
    location: str | None = None
    operational_status: str | None = None


class EquipmentUpdate(BaseModel):
    """Everything Technical Support Staff may change on a catalogue entry."""

    equipment_type: str | None = None
    description: str | None = None
    # Keep invalid scalar JSON values intact so the domain validator can return the
    # catalogue's consistent {field, reason} error response.
    total_quantity: int | float | str | bool | None = None
    location: str | None = None
    operational_status: str | None = None


class EquipmentRead(BaseModel):
    """An equipment entry as shown in the catalogue."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    equipment_type: str
    description: str | None
    total_quantity: int
    location: str
    operational_status: str


class EquipmentProblemRead(BaseModel):
    """One field that must be corrected before an entry can be saved."""

    field: str
    reason: str
