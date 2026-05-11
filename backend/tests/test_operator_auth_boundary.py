from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from starlette.requests import Request

from app.api.auth import require_operator_identity, requires_operator_auth
from app.api.router import build_api_router
from app.core.config import Settings, get_settings
from app.main import app


def _request(
    *,
    method: str = "POST",
    path: str = "/strategy/start",
    headers: dict[str, str] | None = None,
    query_string: bytes = b"",
) -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [
                (name.lower().encode("latin-1"), value.encode("latin-1"))
                for name, value in (headers or {}).items()
            ],
            "query_string": query_string,
        }
    )


def test_audit_sec_001_all_state_changing_routes_require_operator_auth_policy():
    router = build_api_router(Settings(testing_routes_enabled=True))
    state_changing_routes = sorted(
        (method, route.path)
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in (route.methods or set())
        if method in {"POST", "PUT", "PATCH", "DELETE"}
    )

    assert state_changing_routes
    assert [
        (method, path)
        for method, path in state_changing_routes
        if not requires_operator_auth(method=method, path=path)
    ] == []


def test_audit_sec_001_write_on_read_refresh_routes_require_operator_auth_policy():
    assert not requires_operator_auth(method="GET", path="/reviews/operator-summary")
    assert not requires_operator_auth(method="GET", path="/reviews/daily")
    assert not requires_operator_auth(method="GET", path="/reviews/runtime-health")
    assert not requires_operator_auth(
        method="GET", path="/reviews/strategies/{strategy_name}"
    )
    assert not requires_operator_auth(
        method="GET", path="/reviews/trades/{trade_id}/postmortem"
    )
    assert requires_operator_auth(
        method="GET",
        path="/reviews/operator-summary",
        query_params={"persist": "true"},
    )
    assert requires_operator_auth(
        method="GET", path="/reviews/daily", query_params={"persist": "true"}
    )
    assert requires_operator_auth(
        method="GET", path="/reviews/runtime-health", query_params={"persist": "true"}
    )
    assert requires_operator_auth(
        method="GET",
        path="/reviews/strategies/{strategy_name}",
        query_params={"persist": "true"},
    )
    assert requires_operator_auth(
        method="GET",
        path="/reviews/trades/{trade_id}/postmortem",
        query_params={"persist": "true"},
    )
    assert not requires_operator_auth(
        method="GET",
        path="/reviews/operator-summary",
        query_params={"persist": "false"},
    )
    assert requires_operator_auth(
        method="GET", path="/allocation/alerts", query_params={"refresh": "true"}
    )
    assert not requires_operator_auth(
        method="GET", path="/allocation/alerts", query_params={}
    )
    assert not requires_operator_auth(
        method="GET", path="/allocation/alerts/unresolved-critical"
    )
    assert not requires_operator_auth(
        method="GET", path="/allocation/alerts", query_params={"refresh": "false"}
    )
    assert not requires_operator_auth(method="GET", path="/dashboard")


def test_audit_sec_001_production_like_operator_mutation_rejects_missing_token():
    settings = Settings(app_env="production", operator_api_token="expected-token")

    with pytest.raises(HTTPException) as exc_info:
        require_operator_identity(_request(), settings=settings)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Operator authentication is required."


def test_audit_sec_001_production_like_operator_mutation_rejects_invalid_token():
    settings = Settings(app_env="production", operator_api_token="expected-token")

    with pytest.raises(HTTPException) as exc_info:
        require_operator_identity(
            _request(headers={"Authorization": "Bearer wrong-token"}),
            settings=settings,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Operator authentication failed."


def test_audit_sec_001_production_like_operator_mutation_requires_configured_token():
    settings = Settings(app_env="production", operator_api_token=None)

    with pytest.raises(HTTPException) as exc_info:
        require_operator_identity(_request(), settings=settings)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Operator authentication is not configured."


def test_audit_sec_001_operator_mutation_accepts_configured_bearer_token():
    settings = Settings(app_env="production", operator_api_token="expected-token")

    actor_id = require_operator_identity(
        _request(headers={"Authorization": "Bearer expected-token"}),
        settings=settings,
    )

    assert actor_id == "operator"


def test_audit_sec_001_cors_does_not_allow_credentialed_localhost_regex():
    cors_middleware = next(
        middleware
        for middleware in app.user_middleware
        if middleware.cls.__name__ == "CORSMiddleware"
    )

    assert cors_middleware.kwargs["allow_origins"] == get_settings().cors_origins
    assert cors_middleware.kwargs.get("allow_origin_regex") is None
    assert cors_middleware.kwargs["allow_credentials"] is True
