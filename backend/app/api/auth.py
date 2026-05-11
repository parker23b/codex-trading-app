from __future__ import annotations

from collections.abc import Mapping
import secrets

from fastapi import HTTPException, Request, status

from app.core.config import Settings, get_settings


MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
PRODUCTION_LIKE_ENVS = {"production", "prod", "staging", "demo", "live"}
LOCAL_AUTH_OPTIONAL_ENVS = {"development", "dev", "local", "test", "testing"}

ACTIVE_READ_REFRESH_GET_PATHS = {
    "/reviews/operator-summary",
    "/reviews/daily",
    "/reviews/runtime-health",
}


def requires_operator_auth(
    *,
    method: str,
    path: str,
    query_params: Mapping[str, str] | None = None,
) -> bool:
    normalized_method = method.upper()
    if normalized_method in MUTATING_METHODS:
        return True
    if normalized_method != "GET":
        return False

    if path in ACTIVE_READ_REFRESH_GET_PATHS or _is_review_refresh_path(path):
        return _truthy_query_param(query_params, "persist")
    if path == "/allocation/alerts":
        return _truthy_query_param(query_params, "refresh")
    return False


def require_operator_identity(
    request: Request, *, settings: Settings | None = None
) -> str:
    active_settings = settings or get_settings()
    configured_token = _configured_operator_token(active_settings)

    if configured_token is None:
        if _is_production_like(active_settings):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Operator authentication is not configured.",
            )
        return "local-operator"

    supplied_token = _extract_operator_token(request)
    if supplied_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Operator authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not secrets.compare_digest(supplied_token, configured_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator authentication failed.",
        )
    return "operator"


def _configured_operator_token(settings: Settings) -> str | None:
    token = settings.operator_api_token
    if token is None:
        return None
    stripped = token.strip()
    return stripped or None


def _is_production_like(settings: Settings) -> bool:
    app_env = settings.app_env.strip().lower()
    if app_env in PRODUCTION_LIKE_ENVS:
        return True
    return app_env not in LOCAL_AUTH_OPTIONAL_ENVS


def _extract_operator_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization")
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token.strip():
            return token.strip()
    header_token = request.headers.get("x-operator-token")
    if header_token and header_token.strip():
        return header_token.strip()
    return None


def _is_review_refresh_path(path: str) -> bool:
    if path.startswith("/reviews/strategies/"):
        return True
    return path.startswith("/reviews/trades/") and path.endswith("/postmortem")


def _truthy_query_param(query_params: Mapping[str, str] | None, name: str) -> bool:
    value = (query_params or {}).get(name)
    return value is not None and value.lower() not in {"0", "false", "no", "off"}
