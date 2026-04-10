from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PromotionRequestStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class PromotionRequest(SQLModel, table=True):
    __tablename__ = "promotion_request"

    id: Optional[int] = Field(default=None, primary_key=True)
    instrument: str = Field(index=True, nullable=False)
    source: str = Field(index=True)
    reason: str
    score: float = Field(default=0.0)
    status: str = Field(default=PromotionRequestStatus.PENDING.value, index=True)
    requested_at: datetime = Field(default_factory=utc_now, nullable=False, index=True)
    expires_at: datetime | None = None
    market_status: str | None = None
    tradable: bool | None = None
    requested_frequency: str | None = None
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
