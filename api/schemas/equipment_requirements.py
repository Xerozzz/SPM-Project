"""API contracts for an event's equipment requirements (SCRUM-43).

Mirrors domain/equipment_requirement.py.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from domain.equipment_requirement import RequirementReview
from models.equipment_requirement_change import RequirementAction


class RequirementCreate(BaseModel):
    """What a Coordinator supplies to add a requirement.

    Everything is optional in the sense of "present in the payload"; whether a value is
    acceptable is domain/equipment_requirement.py's decision, so a missing field and an
    invalid one are reported the same way rather than in two different shapes.
    """

    equipment_type: str | None = None
    quantity: int | None = None
    technical_requirements: str | None = None


class RequirementUpdate(BaseModel):
    """What a Coordinator may change: how many, and the free-text detail.

    Not the type. AC4 makes one type one line, so moving a line to a different type is a
    removal and an addition, which keeps the history honest about what was asked for.
    """

    quantity: int | None = None
    technical_requirements: str | None = None


class RequirementRead(BaseModel):
    """One requirement as the Coordinator and Technical Support Staff see it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_request_id: uuid.UUID
    equipment_type: str
    quantity: int
    technical_requirements: str | None
    # AC5: back to pending whenever the line changes. SCRUM-44 records the other outcomes.
    review_status: RequirementReview
    removed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RequirementChangeRead(BaseModel):
    """AC7 and AC8: one entry in the event's equipment history."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    requirement_id: uuid.UUID
    changed_by_id: uuid.UUID
    changed_at: datetime
    action: RequirementAction
    equipment_type: str
    old_quantity: int | None
    new_quantity: int | None
    old_technical_requirements: str | None
    new_technical_requirements: str | None
