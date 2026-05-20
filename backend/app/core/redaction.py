from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

REDACTED = "[REDACTED]"
TRACEBACK_REDACTED = "[TRACEBACK REDACTED]"
RAW_BROKER_PAYLOAD_REDACTED = "[RAW_BROKER_PAYLOAD REDACTED]"

_SECRET_KEY_PARTS = (
    "authorization",
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "session",
    "credential",
)
_ACCOUNT_KEY_PARTS = (
    "account_id",
    "accountid",
    "current_account_id",
    "currentaccountid",
)
_DEAL_KEY_PARTS = (
    "deal_reference",
    "dealreference",
    "deal_id",
    "dealid",
    "broker_reference",
    "close_broker_reference",
)
_RAW_BROKER_KEY_PARTS = (
    "payload",
    "market_payload",
    "raw_response",
    "response_body",
    "response_text",
    "response_headers",
    "request_headers",
)
_TRACEBACK_MARKERS = (
    "Traceback (most recent call last):",
    'File "',
)
_TEXT_SUBSTITUTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+\b"),
        "Bearer [REDACTED]",
    ),
    (
        re.compile(r"(?i)\b(CST|X-SECURITY-TOKEN|XST)\s*[:=]\s*[^,\s|]+"),
        r"\1=[REDACTED]",
    ),
    (
        re.compile(r"(?i)\b(CST|XST)-[^|\s]+"),
        r"\1-[REDACTED]",
    ),
    (
        re.compile(
            r'(?i)("?(?:authorization|password|secret|token|api[_-]?key|cst|x-security-token)"?\s*[:=]\s*")([^"]+)(")'
        ),
        r"\1[REDACTED]\3",
    ),
    (
        re.compile(
            r"(?i)\b(accountId|currentAccountId|account_id)\s*[:=]\s*([A-Za-z0-9._:-]+)"
        ),
        r"\1=[REDACTED]",
    ),
    (
        re.compile(
            r'(?i)("?(?:accountId|currentAccountId|account_id)"?\s*:\s*")([^"]+)(")'
        ),
        r"\1[REDACTED]\3",
    ),
    (
        re.compile(
            r"(?i)\b(dealReference|dealId|deal_reference|deal_id|broker_reference)\s*[:=]\s*([A-Za-z0-9._:-]+)"
        ),
        r"\1=[REDACTED]",
    ),
    (
        re.compile(
            r'(?i)("?(?:dealReference|dealId|deal_reference|deal_id|broker_reference)"?\s*:\s*")([^"]+)(")'
        ),
        r"\1[REDACTED]\3",
    ),
)


def sanitize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    if any(marker in text for marker in _TRACEBACK_MARKERS):
        return TRACEBACK_REDACTED
    sanitized = text
    for pattern, replacement in _TEXT_SUBSTITUTIONS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def sanitize_error_detail(
    error: BaseException | str,
    *,
    default_detail: str,
) -> str:
    sanitized = sanitize_text(error)
    if sanitized is None:
        return default_detail
    cleaned = sanitized.strip()
    if not cleaned or cleaned == TRACEBACK_REDACTED:
        return default_detail
    return cleaned


def sanitize_payload(value: Any) -> Any:
    return _sanitize_value(value, parent_key=None)


def _sanitize_value(value: Any, *, parent_key: str | None) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if parent_key is not None:
            normalized_key = _normalize_key(parent_key)
            if _matches_any(normalized_key, _SECRET_KEY_PARTS):
                return REDACTED
            if _matches_any(normalized_key, _ACCOUNT_KEY_PARTS):
                return _mask_identifier(value, label="ACCOUNT_ID")
            if _matches_any(normalized_key, _DEAL_KEY_PARTS):
                return _mask_identifier(value, label="BROKER_REF")
            if _matches_any(normalized_key, _RAW_BROKER_KEY_PARTS):
                return RAW_BROKER_PAYLOAD_REDACTED
        return sanitize_text(value)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            normalized_key = _normalize_key(key_text)
            if _matches_any(normalized_key, _RAW_BROKER_KEY_PARTS):
                result[key_text] = RAW_BROKER_PAYLOAD_REDACTED
                continue
            if _matches_any(normalized_key, _SECRET_KEY_PARTS):
                result[key_text] = REDACTED
                continue
            if _matches_any(normalized_key, _ACCOUNT_KEY_PARTS):
                result[key_text] = _mask_identifier(item, label="ACCOUNT_ID")
                continue
            if _matches_any(normalized_key, _DEAL_KEY_PARTS):
                result[key_text] = _mask_identifier(item, label="BROKER_REF")
                continue
            result[key_text] = _sanitize_value(item, parent_key=key_text)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [_sanitize_value(item, parent_key=parent_key) for item in value]
    return sanitize_text(value)


def _normalize_key(value: str) -> str:
    return value.lower().replace("-", "_").replace(" ", "_")


def _matches_any(value: str, patterns: Sequence[str]) -> bool:
    return any(pattern in value for pattern in patterns)


def _mask_identifier(value: Any, *, label: str) -> str:
    text = sanitize_text(value)
    if not text:
        return f"[REDACTED_{label}]"
    suffix = text[-4:] if len(text) > 4 else text
    return f"[REDACTED_{label}:{suffix}]"
