"""Equipment inventory records maintained by Technical Support Staff (SCRUM-84)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


def _now() -> datetime:
    return datetime.now(UTC)


class Equipment(Base):
    """One catalogue entry, uniquely identified by its type and physical location."""

    __tablename__ = "equipment"
    __table_args__ = (
        UniqueConstraint("equipment_type", "location", name="uq_equipment_type_location"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    equipment_type: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    total_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    operational_status: Mapped[str] = mapped_column(String(100), nullable=False)
    # SCRUM-103: catalogue entries stay available to historical records after retirement.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
