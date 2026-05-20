from __future__ import annotations

from datetime import datetime, timedelta

from sqlmodel import select

from app.api.routes.aimee import get_snapshot as get_aimee_snapshot_route
from app.models.domain_event import DomainEvent
from app.models.operator_control import OperatorControlState
from app.models.review import GeneratedReviewRecord
from app.models.runtime import StrategyRuntimeState
from app.models.strategy_deployment import StrategyDeployment
from app.models.strategy_governance import StrategyFamilyGovernance
from app.models.trade import Execution, ReconciliationEvent, TradeIntent
from app.models.watchlist import WatchlistEntry
from app.reviewer.service import AIReviewerService


def _seed_read_models(session, fixed_now: datetime) -> None:
    session.add(
        OperatorControlState(
            id=1,
            autonomous_control_override=False,
            override_reason="operator paused autonomy for maintenance",
            updated_at=fixed_now,
        )
    )
    session.add(
        StrategyFamilyGovernance(
            strategy_name="mean_reversion",
            approval_state="APPROVED",
            autonomous_operation_allowed=True,
            emergency_stop=False,
            approved_asset_classes=["INDICES"],
            approved_profile_names=["default"],
            created_at=fixed_now - timedelta(hours=2),
            updated_at=fixed_now - timedelta(hours=1),
        )
    )
    session.add(
        StrategyDeployment(
            strategy_name="mean_reversion",
            governance_id=1,
            deployment_key="dep-1",
            state="AUTO_DEPLOYED",
            selected_profile="default",
            selected_instrument="IX.D.FTSE.DAILY.IP",
            created_at=fixed_now - timedelta(hours=2),
            updated_at=fixed_now - timedelta(minutes=30),
        )
    )
    session.add(
        StrategyRuntimeState(
            runtime_id="runtime-1",
            strategy_name="mean_reversion",
            instrument="IX.D.FTSE.DAILY.IP",
            status="RUNNING",
            recovery_state="RUNNING",
            control_mode="AUTO",
            active_profile_name="default",
            started_at=fixed_now - timedelta(hours=1),
            updated_at=fixed_now - timedelta(minutes=10),
        )
    )
    session.add(
        WatchlistEntry(
            instrument="IX.D.FTSE.DAILY.IP",
            tier="TIER1",
            status="ACTIVE",
            asset_class="INDICES",
            pinned=True,
            priority_score=100.0,
            assigned_at=fixed_now - timedelta(minutes=45),
            last_streamed_at=fixed_now - timedelta(minutes=5),
            updated_at=fixed_now - timedelta(minutes=5),
        )
    )
    session.add(
        Execution(
            strategy_name="mean_reversion",
            instrument="IX.D.FTSE.DAILY.IP",
            phase="ENTRY",
            status="FAILED",
            signal_time=fixed_now - timedelta(minutes=20),
            last_transition_at=fixed_now - timedelta(minutes=15),
            updated_at=fixed_now - timedelta(minutes=15),
            error_message="broker rejected order",
        )
    )
    session.add(
        TradeIntent(
            strategy_name="carry_drift",
            instrument="IX.D.DAX.DAILY.IP",
            direction="BUY",
            state="REJECTED",
            signal_time=fixed_now - timedelta(minutes=25),
            updated_at=fixed_now - timedelta(minutes=12),
            decision_reason="allocator rejected candidate",
        )
    )
    session.add(
        DomainEvent(
            created_at=fixed_now - timedelta(minutes=9),
            event_type="reconciliation.position_corrected",
            category="reconciliation",
            severity="warning",
            source="tests",
            title="Position corrected",
            message="Reconciliation corrected a local position.",
        )
    )
    session.add(
        ReconciliationEvent(
            event_type="POSITION_SYNCED_FROM_BROKER",
            strategy_name="mean_reversion",
            instrument="IX.D.FTSE.DAILY.IP",
            created_at=fixed_now - timedelta(minutes=8),
        )
    )
    session.commit()


def _fingerprint_state(session) -> dict[str, object]:
    return {
        "reviews": [
            (record.id, record.review_type, record.generated_at.isoformat())
            for record in session.exec(
                select(GeneratedReviewRecord).order_by(GeneratedReviewRecord.id)
            ).all()
        ],
        "reconciliation_events": [
            (
                event.id,
                event.event_type,
                event.strategy_name,
                event.instrument,
                event.created_at.isoformat(),
            )
            for event in session.exec(
                select(ReconciliationEvent).order_by(ReconciliationEvent.id)
            ).all()
        ],
        "domain_events": [
            (
                event.id,
                event.event_type,
                event.category,
                event.severity,
                event.created_at.isoformat(),
            )
            for event in session.exec(
                select(DomainEvent).order_by(DomainEvent.id)
            ).all()
        ],
        "operator_control": [
            (
                row.id,
                row.autonomous_control_override,
                row.override_reason,
                row.updated_at.isoformat(),
            )
            for row in session.exec(
                select(OperatorControlState).order_by(OperatorControlState.id)
            ).all()
        ],
        "governance": [
            (
                row.strategy_name,
                row.approval_state,
                row.autonomous_operation_allowed,
                row.emergency_stop,
                row.updated_at.isoformat(),
            )
            for row in session.exec(
                select(StrategyFamilyGovernance).order_by(
                    StrategyFamilyGovernance.strategy_name
                )
            ).all()
        ],
        "deployments": [
            (
                row.strategy_name,
                row.state,
                row.selected_instrument,
                row.selected_profile,
                row.updated_at.isoformat(),
            )
            for row in session.exec(
                select(StrategyDeployment).order_by(StrategyDeployment.strategy_name)
            ).all()
        ],
        "runtimes": [
            (
                row.runtime_id,
                row.strategy_name,
                row.instrument,
                row.status,
                row.recovery_state,
                row.control_mode,
                row.updated_at.isoformat(),
            )
            for row in session.exec(
                select(StrategyRuntimeState).order_by(StrategyRuntimeState.runtime_id)
            ).all()
        ],
        "watchlist": [
            (
                row.instrument,
                row.tier,
                row.status,
                row.pinned,
                row.last_streamed_at.isoformat()
                if row.last_streamed_at is not None
                else None,
                row.last_refreshed_at.isoformat()
                if row.last_refreshed_at is not None
                else None,
                row.updated_at.isoformat(),
            )
            for row in session.exec(
                select(WatchlistEntry).order_by(WatchlistEntry.instrument)
            ).all()
        ],
        "executions": [
            (
                row.id,
                row.strategy_name,
                row.instrument,
                row.status,
                row.requires_manual_review,
                row.last_transition_at.isoformat(),
                row.updated_at.isoformat(),
            )
            for row in session.exec(select(Execution).order_by(Execution.id)).all()
        ],
    }


def _fail_if_called(name: str):
    def _raiser(*_args, **_kwargs):
        raise AssertionError(f"{name} must not be called by AIMEE passive reads")

    return _raiser


def test_aimee_snapshot_route_is_side_effect_free(session, fixed_now, monkeypatch):
    _seed_read_models(session, fixed_now)
    before = _fingerprint_state(session)
    original_persist_review = AIReviewerService._persist_review
    persisted_types: list[str] = []

    def _persist_spy(self, response):
        persisted_types.append(response.metadata.review_type)
        return original_persist_review(self, response)

    monkeypatch.setattr(
        "app.services.broker_service.BrokerService.reconcile_positions",
        _fail_if_called("BrokerService.reconcile_positions"),
    )
    monkeypatch.setattr(
        "app.services.reconciliation_service.ReconciliationService.reconcile_open_positions",
        _fail_if_called("ReconciliationService.reconcile_open_positions"),
    )
    monkeypatch.setattr(
        "app.services.strategy_governance_service.StrategyGovernanceService.ensure_defaults",
        _fail_if_called("StrategyGovernanceService.ensure_defaults"),
    )
    monkeypatch.setattr(
        "app.services.watchlist_service.WatchlistService.get_streaming_plan",
        _fail_if_called("WatchlistService.get_streaming_plan"),
    )
    monkeypatch.setattr(
        "app.services.watchlist_service.WatchlistService.get_tier2_refresh_plan",
        _fail_if_called("WatchlistService.get_tier2_refresh_plan"),
    )
    monkeypatch.setattr(AIReviewerService, "_persist_review", _persist_spy)

    first = get_aimee_snapshot_route(session)
    after_first = _fingerprint_state(session)
    second = get_aimee_snapshot_route(session)
    after_second = _fingerprint_state(session)

    assert first.review is not None
    assert second.review is not None
    assert first.review.metadata.review_id is None
    assert second.review.metadata.review_id is None
    assert persisted_types == []
    assert before == after_first == after_second


def test_audit_api_007_aimee_passive_snapshot_does_not_call_broker_account(
    session, fixed_now, monkeypatch
):
    _seed_read_models(session, fixed_now)

    broker_account_reads = 0

    def _fail_broker_read():
        nonlocal broker_account_reads
        broker_account_reads += 1
        raise AssertionError("AIMEE passive snapshot must not call broker account")

    monkeypatch.setattr(
        "app.services.dashboard_service.get_broker",
        _fail_broker_read,
        raising=False,
    )
    monkeypatch.setattr(
        "app.core.broker_factory.get_broker",
        _fail_broker_read,
    )

    snapshot = get_aimee_snapshot_route(session)

    assert snapshot.review is not None
    assert snapshot.review.metadata.review_id is None
    assert broker_account_reads == 0


def test_get_operator_summary_persist_false_does_not_create_review_rows(session):
    reviewer = AIReviewerService(session)
    response = reviewer.get_operator_summary(persist=False)

    assert response.metadata.review_id is None
    assert session.exec(select(GeneratedReviewRecord)).all() == []


def test_operational_question_persists_only_the_explicit_question_review(
    session, fixed_now, monkeypatch
):
    _seed_read_models(session, fixed_now)
    reviewer = AIReviewerService(session)
    before = _fingerprint_state(session)
    original_persist_review = AIReviewerService._persist_review
    persisted_types: list[str] = []

    def _persist_spy(self, response):
        persisted_types.append(response.metadata.review_type)
        return original_persist_review(self, response)

    monkeypatch.setattr(
        "app.services.broker_service.BrokerService.reconcile_positions",
        _fail_if_called("BrokerService.reconcile_positions"),
    )
    monkeypatch.setattr(
        "app.services.reconciliation_service.ReconciliationService.reconcile_open_positions",
        _fail_if_called("ReconciliationService.reconcile_open_positions"),
    )
    monkeypatch.setattr(
        "app.services.strategy_governance_service.StrategyGovernanceService.ensure_defaults",
        _fail_if_called("StrategyGovernanceService.ensure_defaults"),
    )
    monkeypatch.setattr(
        "app.services.watchlist_service.WatchlistService.get_streaming_plan",
        _fail_if_called("WatchlistService.get_streaming_plan"),
    )
    monkeypatch.setattr(
        "app.services.watchlist_service.WatchlistService.get_tier2_refresh_plan",
        _fail_if_called("WatchlistService.get_tier2_refresh_plan"),
    )
    monkeypatch.setattr(AIReviewerService, "_persist_review", _persist_spy)

    response = reviewer.answer_operational_question(
        "What needs my attention right now?"
    )
    after = _fingerprint_state(session)

    records = session.exec(select(GeneratedReviewRecord)).all()
    assert response.metadata.review_id is not None
    assert persisted_types == ["operational_question"]
    assert len(records) == 1
    assert records[0].review_type == "operational_question"
    assert records[0].id == response.metadata.review_id
    assert before["reconciliation_events"] == after["reconciliation_events"]
    assert before["domain_events"] == after["domain_events"]
    assert before["operator_control"] == after["operator_control"]
    assert before["governance"] == after["governance"]
    assert before["deployments"] == after["deployments"]
    assert before["runtimes"] == after["runtimes"]
    assert before["watchlist"] == after["watchlist"]
    assert before["executions"] == after["executions"]
