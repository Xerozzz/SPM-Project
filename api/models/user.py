"""User account for F1 sign-in. Supplied data only; no self-registration."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class User(Base):
    """Supplied user with one or more role claims."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Postgres-dialect ARRAY, not the generic one: only this one implements `.contains()`,
    # which repositories/users.py needs for the active-coordinator lookup (SCRUM-34).
    roles: Mapped[list[str]] = mapped_column(ARRAY(String(50)), nullable=False, default=list)
    # SCRUM-34: only an active Event Coordinator is eligible for round-robin assignment.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
