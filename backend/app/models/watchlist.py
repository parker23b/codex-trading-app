from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WatchlistTier(str, Enum):
    TIER1 = "TIER1"
    TIER2 = "TIER2"
    TIER3 = "TIER3"


class WatchlistStatus(str, Enum):
    ACTIVE = "ACTIVE"
    COOLDOWN = "COOLDOWN"
    INACTIVE = "INACTIVE"


class WatchlistEntry(SQLModel, table=True):
    __tablename__ = "watchlist_entry"

    id: Optional[int] = Field(default=None, primary_key=True)
    instrument: str = Field(index=True, nullable=False)
    tier: str = Field(default=WatchlistTier.TIER1.value, index=True)
    status: str = Field(default=WatchlistStatus.ACTIVE.value, index=True)
    asset_class: str | None = Field(default=None, index=True)
    pinned: bool = Field(default=False, index=True)
    reason: str | None = None
    priority_score: float = 0.0
    requested_frequency: str | None = None
    assigned_at: datetime = Field(default_factory=utc_now, nullable=False)
    min_residency_until: datetime | None = None
    cooldown_until: datetime | None = None
    promotion_expires_at: datetime | None = None
    last_streamed_at: datetime | None = None
    last_refreshed_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
