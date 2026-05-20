from __future__ import annotations

from app.core.redaction import sanitize_error_detail


def operator_error_detail(
    error: BaseException | str,
    *,
    default_detail: str,
    prefix: str | None = None,
) -> str:
    detail = sanitize_error_detail(error, default_detail=default_detail)
    if prefix is None:
        return detail
    if detail == default_detail:
        return prefix
    return f"{prefix}: {detail}"
