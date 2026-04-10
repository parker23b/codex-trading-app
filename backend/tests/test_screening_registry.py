from __future__ import annotations

from datetime import UTC, datetime

from app.core.broker import BrokerMarketDetails
from app.strategies.base import ScreeningSnapshot
from app.strategies.registry import strategy_registry


def test_registry_lists_activity_surveillance_scanner():
    metadata = strategy_registry.list_screening_metadata()

    assert any(item.name == "activity_surveillance_scanner" for item in metadata)


def test_activity_surveillance_scanner_emits_promotion_intent_for_tradable_active_market():
    scanner = strategy_registry.create_scanner("activity_surveillance_scanner")
    snapshot = ScreeningSnapshot(
        instrument="CS.D.GBPJPY.CFD.IP",
        market_details=BrokerMarketDetails(
            instrument="CS.D.GBPJPY.CFD.IP",
            name="GBP/JPY",
            bid=193.7,
            offer=193.8,
            high=194.2,
            low=193.0,
            percentage_change=1.1,
            net_change=1.5,
            market_status="TRADEABLE",
            update_time=datetime(2026, 4, 9, 12, 0, tzinfo=UTC).isoformat(),
            tradable=True,
        ),
        refreshed_at=datetime(2026, 4, 9, 12, 0, tzinfo=UTC),
        streamed=False,
    )

    intent = scanner.evaluate(snapshot)

    assert intent is not None
    assert intent.scanner_name == "activity_surveillance_scanner"
    assert intent.instrument == "CS.D.GBPJPY.CFD.IP"
    assert intent.score >= 0.75
