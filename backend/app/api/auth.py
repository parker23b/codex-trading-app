from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import secrets
from typing import Any

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
REQUEST_CORRELATION_HEADER_NAMES = ("x-request-id", "x-correlation-id")
PRIVILEGED_ADMIN_PATHS = {
    "/control-plane/operator-state",
    "/control-plane/reconcile",
}


@dataclass(frozen=True, slots=True)
class OperatorPrincipal:
    actor_id: str
    scopes: frozenset[str]
    authentication_method: str


def requires_operator_auth(
    *,
    method: str,
    path: str,
    query_params: Mapping[str, str] | None = None,
    settings: Settings | None = None,
) -> bool:
    normalized_method = method.upper()
    active_settings = settings or get_settings()

    if path.startswith("/testing/"):
        return (
            normalized_method in MUTATING_METHODS
            and active_settings.testing_routes_can_register
        )

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
    return require_operator_principal(request, settings=settings).actor_id


def require_operator_principal(
    request: Request, *, settings: Settings | None = None
) -> OperatorPrincipal:
    active_settings = settings or get_settings()
    existing = getattr(request.state, "operator_principal", None)
    if isinstance(existing, OperatorPrincipal):
        return existing

    configured_credentials = active_settings.operator_api_credentials
    configured_token = _configured_operator_token(active_settings)
    if not configured_credentials and configured_token is None:
        if _is_production_like(active_settings):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Operator authentication is not configured.",
            )
        principal = OperatorPrincipal(
            actor_id="local-operator",
            scopes=frozenset({"operate", "deal", "admin"}),
            authentication_method="local-development",
        )
        request.state.operator_principal = principal
        return principal

    supplied_token = _extract_operator_token(request)
    if supplied_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Operator authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    for actor_id, record in configured_credentials.items():
        if not bool(record.get("enabled", True)):
            continue
        candidate = str(record.get("token") or "")
        if candidate and secrets.compare_digest(supplied_token, candidate):
            principal = OperatorPrincipal(
                actor_id=actor_id,
                scopes=frozenset(str(scope) for scope in record.get("scopes", [])),
                authentication_method="named-api-credential",
            )
            request.state.operator_principal = principal
            return principal

    if configured_token is not None and not _is_production_like(active_settings):
        if secrets.compare_digest(supplied_token, configured_token):
            principal = OperatorPrincipal(
                actor_id="operator",
                scopes=frozenset({"operate", "deal", "admin"}),
                authentication_method="legacy-local-token",
            )
            request.state.operator_principal = principal
            return principal

    if configured_token is not None and _is_production_like(active_settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Named operator credentials are required in production-like environments.",
        )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Operator authentication failed.",
    )


def require_operator_scope(
    request: Request,
    *,
    required_scope: str,
    settings: Settings | None = None,
) -> OperatorPrincipal:
    principal = require_operator_principal(request, settings=settings)
    if required_scope not in principal.scopes and "admin" not in principal.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Operator authorization requires the '{required_scope}' scope.",
        )
    return principal


def required_operator_scope(*, method: str, path: str) -> str:
    if method.upper() not in MUTATING_METHODS:
        return "operate"
    if path.startswith("/testing/"):
        return "admin"
    if path in PRIVILEGED_ADMIN_PATHS or path.startswith("/control-plane/governance/"):
        return "admin"
    if path in {"/strategy/start"} or (
        path.startswith("/strategies/") and path.endswith("/start")
    ):
        return "deal"
    return "operate"


def build_operator_audit_context(
    request: Request, *, settings: Settings | None = None
) -> dict[str, Any]:
    active_settings = settings or resolve_request_settings(request) or get_settings()
    principal = require_operator_principal(request, settings=active_settings)
    return {
        "actor_type": "operator",
        "actor_id": principal.actor_id,
        "operator_scopes": sorted(principal.scopes),
        "authentication_method": principal.authentication_method,
        "correlation_id": extract_request_correlation_id(request),
        "request_path": request.url.path,
    }


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


def extract_request_correlation_id(request: Request) -> str | None:
    for header_name in REQUEST_CORRELATION_HEADER_NAMES:
        value = request.headers.get(header_name)
        if value and value.strip():
            return value.strip()
    return None


def resolve_request_settings(request: Request) -> Settings | None:
    app = request.scope.get("app")
    if app is None:
        return None
    return getattr(getattr(app, "state", None), "settings", None)


def _is_review_refresh_path(path: str) -> bool:
    if path.startswith("/reviews/strategies/"):
        return True
    return path.startswith("/reviews/trades/") and path.endswith("/postmortem")


def _truthy_query_param(query_params: Mapping[str, str] | None, name: str) -> bool:
    value = (query_params or {}).get(name)
    return value is not None and value.lower() not in {"0", "false", "no", "off"}
