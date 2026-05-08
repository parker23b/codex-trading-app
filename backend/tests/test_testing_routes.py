from __future__ import annotations

from sqlmodel import select

from app.api.router import build_api_router
from app.api.routes.testing import reset_history
from app.core.config import get_settings
from app.models.domain_event import DomainEvent


def _testing_route_paths(*, enabled: bool) -> set[str]:
    settings = get_settings()
    settings.testing_routes_enabled = enabled

    router = build_api_router()
    return {route.path for route in router.routes}


def test_audit_api_004_reset_history_route_unavailable_without_explicit_test_config(
    session, fixed_now
):
    session.add(
        DomainEvent(
            created_at=fixed_now,
            event_type="execution.position_closed",
            category="execution",
            severity="info",
            source="tests",
            title="Position closed",
        )
    )
    session.commit()

    route_paths = _testing_route_paths(enabled=False)

    assert "/testing/reset-history" not in route_paths
    assert len(session.exec(select(DomainEvent)).all()) == 1


def test_audit_api_004_reset_history_route_available_with_explicit_test_config(
    session, fixed_now
):
    session.add(
        DomainEvent(
            created_at=fixed_now,
            event_type="execution.position_closed",
            category="execution",
            severity="info",
            source="tests",
            title="Position closed",
        )
    )
    session.commit()

    route_paths = _testing_route_paths(enabled=True)
    response = reset_history(session=session)

    assert "/testing/reset-history" in route_paths
    assert response.status == "ok"
    assert response.summary["domain_events_deleted"] == 1
    assert session.exec(select(DomainEvent)).all() == []
