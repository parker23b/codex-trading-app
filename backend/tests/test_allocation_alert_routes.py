from __future__ import annotations

import inspect

from sqlmodel import select

from app.api.auth import requires_operator_auth
from app.api.routes.allocation import (
    list_allocation_alerts,
    list_unresolved_critical_allocation_alerts,
)
from app.models.allocation_alert import AllocationAlert
from app.services.allocation_alert_service import AllocationAlertService


def _seed_alert(session, *, severity: str = "warning") -> AllocationAlert:
    alert = AllocationAlert(
        alert_key=f"seeded-{severity}",
        alert_type="material_execution_drift",
        severity=severity,
        escalation_level="critical" if severity == "error" else "warning",
        title="Seeded allocation alert",
        message="Existing persisted alert",
        count=1,
    )
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return alert


def test_audit_003_allocation_alert_service_default_read_does_not_refresh(
    session, monkeypatch
):
    _seed_alert(session)

    def forbidden_refresh(*_, **__):
        raise AssertionError("passive allocation alert reads must not refresh alerts")

    monkeypatch.setattr(AllocationAlertService, "refresh_alerts", forbidden_refresh)

    alerts = AllocationAlertService(session).list_alerts()

    assert [alert.alert_key for alert in alerts] == ["seeded-warning"]


def test_audit_003_allocation_alert_route_default_is_passive_read():
    refresh_default = (
        inspect.signature(list_allocation_alerts).parameters["refresh"].default
    )

    assert refresh_default.default is False
    assert not requires_operator_auth(
        method="GET", path="/allocation/alerts", query_params={}
    )
    assert requires_operator_auth(
        method="GET", path="/allocation/alerts", query_params={"refresh": "true"}
    )


def test_audit_003_allocation_alert_route_refresh_true_is_active_read(
    session, monkeypatch
):
    calls: list[int | None] = []

    def record_refresh(self, *, window_minutes=None):
        calls.append(window_minutes)
        return []

    monkeypatch.setattr(AllocationAlertService, "refresh_alerts", record_refresh)

    list_allocation_alerts(
        limit=50,
        window_minutes=240,
        include_resolved=False,
        refresh=True,
        session=session,
    )

    assert calls == [240]


def test_audit_003_unresolved_critical_route_reads_persisted_alerts_without_refresh(
    session, monkeypatch
):
    _seed_alert(session, severity="error")

    def forbidden_refresh(*_, **__):
        raise AssertionError("unresolved critical read must not refresh alerts")

    monkeypatch.setattr(AllocationAlertService, "refresh_alerts", forbidden_refresh)

    alerts = list_unresolved_critical_allocation_alerts(
        limit=50, window_minutes=None, session=session
    )

    assert len(alerts) == 1
    assert alerts[0].alert_key == "seeded-error"
    assert not requires_operator_auth(
        method="GET", path="/allocation/alerts/unresolved-critical"
    )
    persisted = session.exec(select(AllocationAlert)).all()
    assert [alert.alert_key for alert in persisted] == ["seeded-error"]
