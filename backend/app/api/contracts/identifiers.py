from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class IdentifierProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display: str
    fingerprint: str
