from __future__ import annotations

from datetime import UTC, datetime

from app.models.runtime import StrategyRuntimeState
from app.models.trade import Execution, Position
from app.services.open_risk_authority_service import OpenRiskAuthorityService


INSTRUMENT = "IX.D.FTSE.DAILY.IP"
STRATEGY = "mean_reversion"


def _position() -> Position:
    return Position(
        strategy_name=STRATEGY,
        family_name=STRATEGY,
        broker_reference="broker-open-1",
        instrument=INSTRUMENT,
        direction="BUY",
        size=1.0,
        open_price=100.0,
        open_time=datetime(2026, 6, 13, 8, 0, tzinfo=UTC),
        account_type="DEMO",
        is_open=True,
        broker_sync_status="CONFIRMED",
        last_reconciled_at=datetime(2026, 6, 13, 8, 1, tzinfo=UTC),
    )


def _runtime(*, runtime_mode: str = "NORMAL") -> StrategyRuntimeState:
    return StrategyRuntimeState(
        runtime_id="runtime-open-risk-1",
        strategy_name=STRATEGY,
        instrument=INSTRUMENT,
        status="RUNNING",
        recovery_state="RUNNING",
        runtime_mode=runtime_mode,
        current_position_broker_reference="broker-open-1",
    )


def test_audit_arch_002_persists_versioned_managed_authority(session):
    session.add(_position())
    session.add(_runtime())
    session.commit()

    first = OpenRiskAuthorityService(session).refresh(source="test")
    first_version = first.version
    second = OpenRiskAuthorityService(session).refresh(source="test")

    assert first.id == second.id
    assert second.version == first_version + 1
    assert second.state == "MANAGED"
    assert second.open_position_count == 1
    assert second.snapshot_json["items"][0]["runtime_id"] == "runtime-open-risk-1"


def test_audit_arch_002_marks_open_position_without_runtime_unmanaged(session):
    session.add(_position())
    session.commit()

    authority = OpenRiskAuthorityService(session).refresh(source="test")

    assert authority.state == "UNMANAGED_OPEN_RISK"
    assert "lacks verified exit authority" in (authority.reason or "")


def test_audit_arch_002_manual_review_restricts_authority_to_exits_only(session):
    position = _position()
    session.add(position)
    session.commit()
    session.refresh(position)
    session.add(_runtime())
    session.add(
        Execution(
            strategy_name=STRATEGY,
            instrument=INSTRUMENT,
            phase="CLOSE",
            status="NEEDS_MANUAL_REVIEW",
            signal_time=datetime(2026, 6, 13, 8, 2, tzinfo=UTC),
            local_position_id=position.id,
            requires_manual_review=True,
        )
    )
    session.commit()

    authority = OpenRiskAuthorityService(session).refresh(source="test")

    assert authority.state == "EXITS_ONLY"
    assert authority.snapshot_json["items"][0]["requires_manual_review"] is True


def test_audit_arch_002_reconciliation_unavailable_fails_open_risk_closed(session):
    session.add(_position())
    session.add(_runtime())
    session.commit()

    authority = OpenRiskAuthorityService(session).refresh(
        source="test",
        reconciliation_status="UNAVAILABLE",
    )

    assert authority.state == "UNMANAGED_OPEN_RISK"
    assert authority.reconciliation_status == "UNAVAILABLE"
