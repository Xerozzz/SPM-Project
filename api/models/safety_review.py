"""A Safety Officer's decision on an event's plan (SCRUM-79).

One row per decision, never updated. AC9 asks for chronological decisions retained for
authorised participants, and AC6 for the plan to be reviewed again after changes, so a
later decision is a new row rather than an edit of the last one. That also makes AC5's
"what does the Coordinator still have to act on" a question about the newest row rather
than a marker someone has to remember to clear.

`plan_fingerprint` is what the decision was taken against (AC4, AC8). AC7 refuses a
decision whose fingerprint no longer matches the plan, which is why it is stored rather
than recomputed: the point is to know what was in front of the Officer at the time.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from domain.safety_review import SafetyDecision


class SafetyReview(Base):
    __tablename__ = "safety_reviews"
    __table_args__ = (
        # AC4: a decision without a reason is not a review. Enforced here as well as in
        # the domain, because an empty comment is the easy mistake for any future caller.
        CheckConstraint("btrim(comment) <> ''", name="safety_reviews_comment_not_blank"),
        # AC9 and AC5 both read the newest decision for an event, so the index matches
        # the order they ask for it in.
        Index("ix_safety_reviews_event_decided_at", "event_request_id", "decided_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event_requests.id"), nullable=False, index=True
    )
    # The closed vocabulary from domain.safety_review, stored as its lowercase value in a
    # plain VARCHAR (native_enum=False elsewhere in this codebase), so adding an outcome
    # later is a code change rather than a Postgres type migration.
    decision: Mapped[SafetyDecision] = mapped_column(String(32), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    #: AC4 and AC8: the plan this decision was taken against. SHA-256 hex, so 64 chars.
    plan_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    decided_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
