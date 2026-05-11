from __future__ import annotations

from datetime import UTC, date, datetime

from sqlmodel import select

from app.api.routes.ai_reviewer import (
    get_daily_review,
    get_operator_summary,
    get_runtime_health_review,
    get_strategy_review,
    get_trade_postmortem,
)
from app.api.routes.coverage import get_coverage_summary
from app.api.routes.control_plane import (
    get_control_plane_strategy_detail,
    get_operator_control_state,
)
from app.api.routes.markets import (
    get_feed_state,
    get_instrument_feed_state,
    get_strategy_watchlist,
)
from app.api.routes.strategies import list_strategies
from app.models.operator_control import OperatorControlState
from app.models.review import GeneratedReviewRecord
from app.models.strategy_governance import StrategyFamilyGovernance
from app.models.trade import Trade
from app.models.watchlist import WatchlistEntry, WatchlistStatus, WatchlistTier


def _seed_watchlist_entry(session) -> WatchlistEntry:
    entry = WatchlistEntry(
        instrument="CS.D.EURUSD.CFD.IP",
        tier=WatchlistTier.TIER1.value,
        status=WatchlistStatus.ACTIVE.value,
        asset_class="forex",
        pinned=False,
        reason="operator_strategy_watchlist",
        priority_score=60.0,
        assigned_at=datetime(2026, 4, 9, 10, 0, tzinfo=UTC),
        last_streamed_at=datetime(2026, 4, 9, 10, 5, tzinfo=UTC),
        updated_at=datetime(2026, 4, 9, 10, 10, tzinfo=UTC),
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def _watchlist_state(session) -> tuple[int, datetime | None, datetime | None]:
    entries = session.exec(
        select(WatchlistEntry).order_by(WatchlistEntry.instrument)
    ).all()
    assert len(entries) == 1
    entry = entries[0]
    return len(entries), entry.last_streamed_at, entry.updated_at


def test_audit_api_001_operator_state_get_does_not_seed_default_row(session):
    response = get_operator_control_state(session)

    assert response.override_active is False
    assert response.override_value is None
    assert response.updated_at is None
    assert session.exec(select(OperatorControlState)).all() == []


def test_audit_api_001_control_plane_strategy_detail_does_not_seed_governance(
    session,
):
    detail = get_control_plane_strategy_detail("mean_reversion", session)

    assert detail["strategy_name"] == "mean_reversion"
    assert detail["governance"]["approval_state"] == "UNKNOWN"
    assert session.exec(select(StrategyFamilyGovernance)).all() == []


def test_audit_api_001_strategy_list_get_does_not_seed_governance(session):
    strategies = list_strategies(session)

    assert strategies
    mean_reversion = next(
        strategy for strategy in strategies if strategy["name"] == "mean_reversion"
    )
    assert mean_reversion["governance_approval_state"] == "UNKNOWN"
    assert mean_reversion["authorized"] is False
    assert session.exec(select(StrategyFamilyGovernance)).all() == []


def test_audit_api_002_strategy_watchlist_get_does_not_sync_watchlist_state(session):
    _seed_watchlist_entry(session)
    before = _watchlist_state(session)

    response = get_strategy_watchlist(session)

    assert response["active_count"] == 1
    assert _watchlist_state(session) == before


def test_audit_api_002_feed_state_get_does_not_sync_watchlist_state(session):
    entry = _seed_watchlist_entry(session)
    before = _watchlist_state(session)

    response = get_feed_state(session)
    instrument_response = get_instrument_feed_state(entry.instrument, session)

    assert response["instruments"][0]["instrument"] == entry.instrument
    assert instrument_response["instrument"] == entry.instrument
    assert _watchlist_state(session) == before


def test_audit_api_002_coverage_summary_get_does_not_sync_watchlist_state(session):
    entry = _seed_watchlist_entry(session)
    before = _watchlist_state(session)

    response = get_coverage_summary(session)

    assert response.streaming["active_instruments"][0]["instrument"] == entry.instrument
    assert _watchlist_state(session) == before


def test_audit_api_003_review_gets_are_passive_without_explicit_persist(session):
    trade = Trade(
        strategy_name="mean_reversion",
        instrument="CS.D.EURUSD.CFD.IP",
        direction="BUY",
        size=1.0,
        open_price=1.1,
        close_price=1.2,
        open_time=datetime(2026, 4, 9, 9, 0, tzinfo=UTC),
        close_time=datetime(2026, 4, 9, 10, 0, tzinfo=UTC),
        pnl=100.0,
        account_type="DEMO",
    )
    session.add(trade)
    session.commit()
    session.refresh(trade)

    get_operator_summary(session=session, persist=False)
    get_daily_review(review_date=date(2026, 4, 9), session=session, persist=False)
    get_strategy_review("mean_reversion", days=7, session=session, persist=False)
    get_runtime_health_review(hours=24, session=session, persist=False)
    get_trade_postmortem(trade.id or 0, session=session, persist=False)

    assert session.exec(select(GeneratedReviewRecord)).all() == []


def test_audit_api_003_review_get_persist_true_is_explicit_active_read(session):
    response = get_operator_summary(session=session, persist=True)

    records = session.exec(select(GeneratedReviewRecord)).all()
    assert len(records) == 1
    assert records[0].review_type == "operator_summary"
    assert response.metadata.review_id == records[0].id
