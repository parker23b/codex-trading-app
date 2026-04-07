from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings


@dataclass(slots=True)
class ReviewLLMRequest:
    system_prompt: str
    user_prompt: str


@dataclass(slots=True)
class ReviewLLMResponse:
    content: str
    provider: str
    model: str


class ReviewLLMClient:
    def generate(self, request: ReviewLLMRequest) -> ReviewLLMResponse | None:  # pragma: no cover - interface only
        raise NotImplementedError


class NullReviewLLMClient(ReviewLLMClient):
    def generate(self, request: ReviewLLMRequest) -> ReviewLLMResponse | None:
        return None


def get_review_llm_client() -> ReviewLLMClient:
    settings = get_settings()
    if not settings.ai_reviewer_llm_enabled:
        return NullReviewLLMClient()
    return NullReviewLLMClient()
