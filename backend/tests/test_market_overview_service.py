from __future__ import annotations

from app.core.broker import BrokerMarketDetails
from app.core.instrument_catalog import list_market_instruments
from app.services import market_overview_service
from app.services.market_overview_service import MarketOverviewService


class _BatchMarketBroker:
    def __init__(self) -> None:
        self.batch_requests: list[list[str]] = []
        self.single_requests: list[str] = []

    def get_market_details(self, instrument: str) -> BrokerMarketDetails:
        self.single_requests.append(instrument)
        return self._details(instrument)

    def get_market_details_many(
        self, instruments: list[str]
    ) -> dict[str, BrokerMarketDetails]:
        self.batch_requests.append(list(instruments))
        return {instrument: self._details(instrument) for instrument in instruments}

    @staticmethod
    def _details(instrument: str) -> BrokerMarketDetails:
        return BrokerMarketDetails(
            instrument=instrument,
            name=instrument,
            bid=1.0,
            offer=1.1,
            high=1.2,
            low=0.9,
            percentage_change=0.1,
            net_change=0.0,
            market_status="TRADEABLE",
            update_time="12:00:00",
            tradable=True,
        )


def test_market_overview_batches_broker_market_detail_reads(session, monkeypatch):
    broker = _BatchMarketBroker()
    monkeypatch.setattr(market_overview_service, "get_broker", lambda: broker)

    overview = MarketOverviewService(session).get_category_overview("forex")

    expected_epics = [
        definition.epic
        for definition in list_market_instruments()
        if definition.category == "FOREX"
    ]
    assert broker.batch_requests == [expected_epics]
    assert broker.single_requests == []
    assert len(overview["instruments"]) == len(expected_epics)
