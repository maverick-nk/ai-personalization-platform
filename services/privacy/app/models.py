from datetime import datetime

from sqlalchemy import Boolean, DateTime, Identity, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Consent(Base):
    __tablename__ = "consent"

    user_pseudo_id: Mapped[str] = mapped_column(String, primary_key=True)
    consent_granted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    # Composite PK required by PostgreSQL range-partitioned tables — the partition key
    # (timestamp) must appear in every unique/PK constraint.
    # Identity(always=True) maps to GENERATED ALWAYS AS IDENTITY, which works correctly
    # on partitioned tables unlike SERIAL (whose sequence doesn't propagate to children).
    id: Mapped[int] = mapped_column(Integer, Identity(always=True), primary_key=True)
    user_pseudo_id: Mapped[str] = mapped_column(String, nullable=False)
    # 'GRANT' or 'REVOKE' — kept short so the column is self-documenting in psql output
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    # Optional human-readable context for why consent changed — e.g. "GDPR erasure
    # request", "onboarding flow", "support ticket #1234". Omitted for automated
    # flows; most useful when a human (user or admin) initiates the change and there
    # is business context worth preserving alongside the timestamp.
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
