from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GeneratedReviewRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    review_type: str = Field(index=True)
    scope: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    generated_at: datetime = Field(default_factory=utc_now, nullable=False, index=True)
    facts_payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    derived_observations: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON)
    )
    possible_contributors: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON)
    )
    warnings: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    supporting_metrics: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON)
    )
    ai_summary: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    prompt_version: str = Field(default="ai-reviewer-v1")
    provider: str | None = None
    model: str | None = None
    raw_model_response: str | None = None
    generation_mode: str = Field(default="deterministic_only", index=True)
