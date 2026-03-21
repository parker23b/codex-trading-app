from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlmodel import Session

from app.core.broker import BrokerMarketDetails
from app.core.broker_factory import get_broker
from app.core.ig_broker import IGBrokerError
from app.core.instrument_catalog import InstrumentDefinition, list_market_instruments
from app.core.runtime import runtime_manager
from app.models.trade import Position, Trade
from app.services.trade_service import TradeService


@dataclass(frozen=True, slots=True)
class MarketCategoryMeta:
    key: str
    label: str
    description: str


CATEGORY_META: dict[str, MarketCategoryMeta] = {
    "forex": MarketCategoryMeta(
        key="forex",
        label="Forex",
        description="Global currency pairs with session-aware strategy routing.",
    ),
    "indices": MarketCategoryMeta(
        key="indices",
        label="Indices",
        description="Major benchmark contracts where directional and mean-reversion systems run.",
    ),
    "commodities": MarketCategoryMeta(
        key="commodities",
        label="Commodities",
        description="Metals and energy products with tighter session maintenance windows.",
    ),
    "stocks": MarketCategoryMeta(
        key="stocks",
        label="Stocks",
        description="Cash equities focused on the primary U.S. session.",
    ),
    "crypto": MarketCategoryMeta(
        key="crypto",
        label="Crypto",
        description="Always-on digital assets with hourly risk throttles.",
    ),
}


class MarketOverviewService:
    def __init__(self, session: Session):
        self.trade_service = TradeService(session)
        self.broker = get_broker()

    def get_category_overview(self, category: str) -> dict[str, object]:
        if category not in CATEGORY_META:
            raise ValueError(f"Unsupported market category '{category}'.")

        now = datetime.now(UTC)
        positions = {position.instrument: position for position in self.trade_service.list_positions()}
        trades = self.trade_service.list_trades()
        rows: list[dict[str, object]] = []

        for definition in list_market_instruments():
            definition_category = definition.category.lower()
            if definition_category != category:
                continue
            details = self.broker.get_market_details(definition.epic)
            rows.append(
                self._build_instrument_row(
                definition=definition,
                details=details,
                now=now,
                position=positions.get(definition.epic),
                trades=trades,
            )
            )

        return {
            "generatedAt": now.isoformat(),
            "summary": self._build_summary(category=category, rows=rows, now=now),
            "instruments": rows,
        }

    def _build_instrument_row(
        self,
        *,
        definition: InstrumentDefinition,
        details: BrokerMarketDetails,
        now: datetime,
        position: Position | None,
        trades: list[Trade],
    ) -> dict[str, object]:
        price = self._select_price(details, position, definition)
        active = self._is_active(definition=definition, details=details, now=now, position=position, trades=trades)
        status = self._map_status(details.market_status, tradable=details.tradable, has_open_position=bool(position and position.is_open))
        session_note = self._session_note(details=details, status=status, has_open_position=bool(position and position.is_open))

        return {
            "id": definition.epic,
            "category": definition.category.lower(),
            "name": details.name or definition.label,
            "symbol": definition.symbol,
            "status": status,
            "tradable": details.tradable,
            "active": active,
            "activityLevel": self._activity_level(details=details, active=active),
            "strategyCompatibility": list(definition.compatible_strategies),
            "price": round(price, 4) if price < 100 else round(price, 2),
            "changePercent": round(details.percentage_change or 0.0, 2),
            "sessionNote": session_note,
        }

    def _build_summary(self, *, category: str, rows: list[dict[str, object]], now: datetime) -> dict[str, object]:
        meta = CATEGORY_META[category]
        tradable_rows = [row for row in rows if row["tradable"]]
        active_rows = [row for row in rows if row["active"]]
        primary_row = self._primary_row(rows)
        next_transition_label = self._next_transition_label(primary_row)
        next_transition_at = self._next_transition_at(now=now, primary_row=primary_row)

        return {
            "category": category,
            "label": meta.label,
            "description": meta.description,
            "status": self._summary_status(rows),
            "headline": f"{next_transition_label} in {self._format_countdown(next_transition_at, now)}",
            "detail": primary_row.get("sessionNote")
            or f"{len(tradable_rows)} of {len(rows)} instruments are ready for strategy deployment.",
            "nextTransitionAt": next_transition_at.isoformat(),
            "nextTransitionLabel": next_transition_label,
            "tradableCount": len(tradable_rows),
            "activeCount": len(active_rows),
            "totalCount": len(rows),
        }

    @staticmethod
    def _select_price(details: BrokerMarketDetails, position: Position | None, definition: InstrumentDefinition) -> float:
        if details.bid is not None and details.offer is not None:
            return (details.bid + details.offer) / 2
        if details.bid is not None:
            return details.bid
        if details.offer is not None:
            return details.offer
        if details.high is not None and details.low is not None:
            return (details.high + details.low) / 2
        if position and position.current_price is not None:
            return position.current_price
        return definition.reference_price

    @staticmethod
    def _map_status(market_status: str | None, *, tradable: bool, has_open_position: bool) -> str:
        normalized = (market_status or "").upper()
        if tradable:
            return "OPEN"
        if has_open_position or normalized in {"EDITS_ONLY", "ON_AUCTION", "ON_AUCTION_NO_EDITS", "SUSPENDED"}:
            return "LIMITED"
        return "CLOSED"

    @staticmethod
    def _session_note(*, details: BrokerMarketDetails, status: str, has_open_position: bool) -> str | None:
        normalized = (details.market_status or "").upper()
        if has_open_position and status == "LIMITED":
            return "Market is not open for fresh entries, but open positions can still require management."
        if normalized == "TRADEABLE":
            return None
        if normalized == "CLOSED":
            return "Market is currently closed at the venue."
        if normalized in {"EDITS_ONLY", "ON_AUCTION", "ON_AUCTION_NO_EDITS"}:
            return "Venue is in a restricted session. Existing orders may be managed, but new entries are limited."
        if normalized == "SUSPENDED":
            return "Instrument is suspended by the venue."
        return f"IG market status: {normalized}." if normalized else None

    def _is_active(
        self,
        *,
        definition: InstrumentDefinition,
        details: BrokerMarketDetails,
        now: datetime,
        position: Position | None,
        trades: list[Trade],
    ) -> bool:
        active_runtime = any(
            engine.instrument == definition.epic and engine.active
            for engine in runtime_manager.engines.values()
        )
        has_open_position = bool(position and position.is_open)
        has_recent_trade = any(
            trade.instrument == definition.epic and (now - trade.close_time.astimezone(UTC)) <= timedelta(days=2)
            for trade in trades[:30]
        )
        has_live_market = (details.market_status or "").upper() in {"TRADEABLE", "TRADEABLE_ONLINE", "EDITS_ONLY"}
        return active_runtime or has_open_position or has_recent_trade or has_live_market

    @staticmethod
    def _activity_level(*, details: BrokerMarketDetails, active: bool) -> str:
        change = abs(details.percentage_change or 0.0)
        if not active:
            return "LOW"
        if change >= 0.75:
            return "HIGH"
        if change >= 0.2:
            return "MEDIUM"
        if details.bid is not None and details.offer is not None:
            spread = abs(details.offer - details.bid)
            if spread > 0:
                return "MEDIUM"
        return "LOW"

    @staticmethod
    def _summary_status(rows: list[dict[str, object]]) -> str:
        if any(row["status"] == "OPEN" for row in rows):
            return "OPEN"
        if any(row["status"] == "LIMITED" for row in rows):
            return "LIMITED"
        return "CLOSED"

    @staticmethod
    def _primary_row(rows: list[dict[str, object]]) -> dict[str, object]:
        return sorted(
            rows,
            key=lambda row: (
                0 if row["status"] == "OPEN" else 1 if row["status"] == "LIMITED" else 2,
                -float(row["changePercent"]),
            ),
        )[0]

    @staticmethod
    def _next_transition_label(primary_row: dict[str, object]) -> str:
        return "Closes" if primary_row["status"] == "OPEN" else "Opens"

    @staticmethod
    def _next_transition_at(*, now: datetime, primary_row: dict[str, object]) -> datetime:
        if primary_row["status"] == "OPEN":
            return now + timedelta(hours=6)
        if primary_row["status"] == "LIMITED":
            return now + timedelta(hours=1)
        return now + timedelta(hours=12)

    @staticmethod
    def _format_countdown(target: datetime, now: datetime) -> str:
        total_minutes = max(0, round((target - now).total_seconds() / 60))
        hours, minutes = divmod(total_minutes, 60)
        return f"{hours}h {minutes}m" if hours else f"{minutes}m"

    def validate_connectivity(self) -> None:
        try:
            first_instrument = list_market_instruments()[0]
            self.broker.get_market_details(first_instrument.epic)
        except IGBrokerError:
            raise
