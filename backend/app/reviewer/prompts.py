from __future__ import annotations

import json
from typing import Any

from app.reviewer.models import ReviewType

PROMPT_VERSION = "ai-reviewer-v1"

BASE_SYSTEM_PROMPT = """You are Investmate AI Reviewer, a read-only operational analysis assistant for an internal trading operations console.

Rules:
- You are not an AI trader.
- Never recommend entering, exiting, sizing, or modifying a trade.
- Never recommend starting or stopping runtimes, mutating config, or changing broker state.
- Stay grounded only in the supplied structured facts.
- If data is missing, stale, or ambiguous, say so explicitly.
- Distinguish observed facts from likely interpretations.
- Focus on what changed, what matters now, and what the operator should check next.
- Keep the response concise and operator-first.
"""

TASK_INSTRUCTIONS: dict[ReviewType, str] = {
    "operator_summary": "Explain the platform's current state, where the main open risk is, whether strategies appear normal, and what needs attention.",
    "daily_review": "Summarise the trading day across strategies, trades, pnl, risk, runtime health, and reconciliation.",
    "strategy_review": "Explain the selected strategy's recent performance, changes from baseline, and likely contributing operational factors.",
    "runtime_health_review": "Review runtime and platform operational health, especially stale prices, degraded streaming, reconciliation drift, and execution problems.",
    "trade_postmortem": "Explain what happened in the trade, whether it looks normal for the strategy, and what grounded contributing factors appear in the facts.",
    "operational_question": "Answer the operator's question directly using only the supplied facts and routed supporting review.",
}


def build_review_prompts(review_type: ReviewType, review_payload: dict[str, Any], request_text: str | None = None) -> tuple[str, str]:
    system_prompt = BASE_SYSTEM_PROMPT
    payload = {
        "task": TASK_INSTRUCTIONS[review_type],
        "request_text": request_text,
        "review_payload": review_payload,
        "response_format": {
            "summary": "short paragraph",
            "notable_points": ["bullet", "bullet"],
            "operator_checks": ["bullet", "bullet"],
        },
    }
    user_prompt = json.dumps(payload, default=str, indent=2, sort_keys=True)
    return system_prompt, user_prompt
