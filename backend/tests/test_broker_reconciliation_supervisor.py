from __future__ import annotations

from app.services.broker_reconciliation_supervisor import (
    BrokerReconciliationSupervisor,
)


def test_audit_arch_001_reconciliation_runs_without_watchlist_coverage(
    session,
    monkeypatch,
):
    calls = []

    class SessionContext:
        def __init__(self, _engine):
            pass

        def __enter__(self):
            return session

        def __exit__(self, *_args):
            return None

    def reconcile(_service, active_session):
        calls.append(active_session)
        return []

    monkeypatch.setattr(
        "app.services.broker_reconciliation_supervisor.Session",
        SessionContext,
    )
    monkeypatch.setattr(
        "app.services.broker_reconciliation_supervisor.BrokerService.reconcile_positions",
        reconcile,
    )

    BrokerReconciliationSupervisor().reconcile_once()

    assert calls == [session]
