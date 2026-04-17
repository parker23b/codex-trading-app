from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.core.broker import (
    AccountType,
    Broker,
    BrokerAccountSummary,
    BrokerMarketDetails,
    BrokerOrderResult,
    BrokerRiskSizingQuote,
    BrokerSizeNormalization,
    BrokerSizingMode,
    BrokerSizingPrecision,
    BrokerPosition,
    OrderDirection,
    OrderRequest,
)


@dataclass
class FakeBroker(Broker):
    _account_type: AccountType = AccountType.DEMO
    account_summary: BrokerAccountSummary | None = None
    remote_positions: list[BrokerPosition] = field(default_factory=list)
    market_details_by_instrument: dict[str, BrokerMarketDetails] = field(default_factory=dict)
    place_order_outcomes: list[BrokerOrderResult | Exception] = field(default_factory=list)
    close_position_outcomes: list[BrokerOrderResult | Exception] = field(default_factory=list)
    placed_orders: list[OrderRequest] = field(default_factory=list)
    close_requests: list[dict[str, str | None]] = field(default_factory=list)
    latest_prices: dict[str, float] = field(default_factory=dict)

    @property
    def account_type(self) -> AccountType:
        return self._account_type

    def place_order(self, order: OrderRequest) -> BrokerOrderResult:
        self.placed_orders.append(order)
        if not self.place_order_outcomes:
            raise AssertionError("No fake place_order outcome was queued.")
        outcome = self.place_order_outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def close_position(
        self,
        instrument: str,
        *,
        broker_reference: str | None = None,
        client_request_id: str | None = None,
    ) -> BrokerOrderResult:
        self.close_requests.append(
            {
                "instrument": instrument,
                "broker_reference": broker_reference,
                "client_request_id": client_request_id,
            }
        )
        if not self.close_position_outcomes:
            raise AssertionError("No fake close_position outcome was queued.")
        outcome = self.close_position_outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def get_positions(self) -> list[BrokerPosition]:
        return list(self.remote_positions)

    def get_latest_price(self, instrument: str) -> float:
        return self.latest_prices.get(instrument, 100.0)

    def get_account_summary(self) -> BrokerAccountSummary:
        if self.account_summary is not None:
            return self.account_summary
        return BrokerAccountSummary(
            account_id="fake-account",
            balance=100_000.0,
            available=100_000.0,
            profit_loss=0.0,
            equity=100_000.0,
            account_type=self.account_type,
        )

    def get_market_details(self, instrument: str) -> BrokerMarketDetails:
        if instrument in self.market_details_by_instrument:
            return self.market_details_by_instrument[instrument]
        price = self.get_latest_price(instrument)
        return BrokerMarketDetails(
            instrument=instrument,
            name=instrument,
            bid=price - 0.1,
            offer=price + 0.1,
            high=price + 1.0,
            low=price - 1.0,
            percentage_change=0.0,
            net_change=0.0,
            market_status="TRADEABLE",
            update_time=datetime.now(UTC).isoformat(),
            tradable=True,
            metadata={
                "sizing_profile": {
                    "mode": BrokerSizingMode.APPROXIMATE_PRICE_DELTA.value,
                    "contract_multiplier": 1.0,
                }
            },
        )

    def quote_risk_sized_order(
        self,
        instrument: str,
        *,
        entry_price: float,
        risk_amount: float,
        stop_loss_price: float | None = None,
        fallback_stop_distance: float | None = None,
    ) -> BrokerRiskSizingQuote:
        details = self.get_market_details(instrument)
        sizing_profile = details.metadata.get("sizing_profile") if isinstance(details.metadata, dict) else None
        if not isinstance(sizing_profile, dict):
            sizing_profile = {
                "mode": BrokerSizingMode.APPROXIMATE_PRICE_DELTA.value,
                "contract_multiplier": 1.0,
            }
        stop_distance, sizing_method = self._effective_stop_distance(
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            fallback_stop_distance=fallback_stop_distance,
            min_stop_distance=details.min_normal_stop_or_limit_distance,
        )
        raw_mode = str(sizing_profile.get("mode", BrokerSizingMode.UNSUPPORTED.value))
        try:
            mode = BrokerSizingMode(raw_mode)
        except ValueError:
            mode = BrokerSizingMode.UNSUPPORTED
        if mode is BrokerSizingMode.EXACT_POINT_VALUE:
            price_increment = float(sizing_profile.get("price_increment") or 0.0)
            value_per_increment = float(sizing_profile.get("value_per_increment") or 0.0)
            if price_increment <= 0 or value_per_increment <= 0:
                return BrokerRiskSizingQuote(
                    instrument=instrument,
                    precision=BrokerSizingPrecision.UNSUPPORTED,
                    mode=BrokerSizingMode.UNSUPPORTED,
                    sizing_available=False,
                    reason_code="unsupported_sizing",
                    reason="Exact point-value sizing profile is incomplete.",
                    entry_price=entry_price,
                    risk_amount=risk_amount,
                    stop_distance_price=stop_distance,
                    sizing_method=sizing_method,
                    min_stop_distance=details.min_normal_stop_or_limit_distance,
                    details={"source": "fake_broker", "sizing_profile": sizing_profile},
                )
            risk_per_unit = (stop_distance / price_increment) * value_per_increment
            precision = BrokerSizingPrecision.EXACT
        elif mode is BrokerSizingMode.EXACT_CONTRACT_RISK:
            contract_multiplier = float(sizing_profile.get("contract_multiplier") or 0.0)
            if contract_multiplier <= 0:
                return BrokerRiskSizingQuote(
                    instrument=instrument,
                    precision=BrokerSizingPrecision.UNSUPPORTED,
                    mode=BrokerSizingMode.UNSUPPORTED,
                    sizing_available=False,
                    reason_code="unsupported_sizing",
                    reason="Exact contract-risk sizing profile is incomplete.",
                    entry_price=entry_price,
                    risk_amount=risk_amount,
                    stop_distance_price=stop_distance,
                    sizing_method=sizing_method,
                    min_stop_distance=details.min_normal_stop_or_limit_distance,
                    details={"source": "fake_broker", "sizing_profile": sizing_profile},
                )
            risk_per_unit = stop_distance * contract_multiplier
            precision = BrokerSizingPrecision.EXACT
        elif mode is BrokerSizingMode.APPROXIMATE_PRICE_DELTA:
            contract_multiplier = float(sizing_profile.get("contract_multiplier") or 1.0)
            risk_per_unit = stop_distance * contract_multiplier
            precision = BrokerSizingPrecision.APPROXIMATE
        else:
            return BrokerRiskSizingQuote(
                instrument=instrument,
                precision=BrokerSizingPrecision.UNSUPPORTED,
                mode=BrokerSizingMode.UNSUPPORTED,
                sizing_available=False,
                reason_code="unsupported_sizing",
                reason=f"Unsupported sizing mode '{raw_mode}' configured for fake broker.",
                entry_price=entry_price,
                risk_amount=risk_amount,
                stop_distance_price=stop_distance,
                sizing_method=sizing_method,
                min_stop_distance=details.min_normal_stop_or_limit_distance,
                details={"source": "fake_broker", "sizing_profile": sizing_profile},
            )
        requested_size = risk_amount / max(risk_per_unit, 1e-9)
        normalization = self.normalize_order_size(instrument, requested_size)
        return BrokerRiskSizingQuote(
            instrument=instrument,
            precision=precision,
            mode=mode,
            sizing_available=True,
            reason_code="quoted",
            reason="Fake broker generated a risk sizing quote.",
            entry_price=entry_price,
            risk_amount=risk_amount,
            requested_size=max(requested_size, 0.0),
            normalized_size=normalization.normalized_size,
            risk_per_unit=risk_per_unit,
            stop_distance_price=stop_distance,
            sizing_method=sizing_method,
            min_stop_distance=details.min_normal_stop_or_limit_distance,
            normalization=normalization,
            details={"source": "fake_broker", "sizing_profile": sizing_profile},
        )

    def normalize_order_size(self, instrument: str, requested_size: float) -> BrokerSizeNormalization:
        details = self.get_market_details(instrument)
        notes: list[str] = []
        normalized_size = max(float(requested_size), 0.0)
        if details.size_step is not None and details.size_step > 0:
            normalized_size = int(normalized_size / details.size_step) * details.size_step
            notes.append("rounded_down_to_size_step")
        normalized_size = round(normalized_size, 8)
        if normalized_size <= 0:
            return BrokerSizeNormalization(
                instrument=instrument,
                requested_size=requested_size,
                normalized_size=0.0,
                accepted=False,
                reason_code="size_rounded_to_zero",
                reason="Broker size normalization rounded the requested size to zero.",
                min_deal_size=details.min_deal_size,
                size_step=details.size_step,
                details={},
                notes=notes,
            )
        if details.min_deal_size is not None and normalized_size < details.min_deal_size:
            return BrokerSizeNormalization(
                instrument=instrument,
                requested_size=requested_size,
                normalized_size=normalized_size,
                accepted=False,
                reason_code="below_min_size",
                reason="Computed size is below broker minimum deal size.",
                min_deal_size=details.min_deal_size,
                size_step=details.size_step,
                details={},
                notes=notes,
            )
        return BrokerSizeNormalization(
            instrument=instrument,
            requested_size=requested_size,
            normalized_size=normalized_size,
            accepted=True,
            reason_code="normalized",
            reason="Size normalized to broker-valid constraints.",
            min_deal_size=details.min_deal_size,
            size_step=details.size_step,
            details={},
            notes=notes,
        )

    @staticmethod
    def _effective_stop_distance(
        *,
        entry_price: float,
        stop_loss_price: float | None,
        fallback_stop_distance: float | None,
        min_stop_distance: float | None,
    ) -> tuple[float, str]:
        if stop_loss_price is not None:
            distance = abs(entry_price - stop_loss_price)
            if min_stop_distance is not None:
                distance = max(distance, min_stop_distance)
            return max(distance, 1e-9), "stop_distance"
        fallback = max(float(fallback_stop_distance or 0.0), 1e-9)
        if min_stop_distance is not None:
            fallback = max(fallback, min_stop_distance)
        return fallback, "fallback_percent_stop"


@dataclass
class ContractRiskBroker(FakeBroker):
    contract_multipliers: dict[str, float] = field(default_factory=dict)

    def quote_risk_sized_order(
        self,
        instrument: str,
        *,
        entry_price: float,
        risk_amount: float,
        stop_loss_price: float | None = None,
        fallback_stop_distance: float | None = None,
    ) -> BrokerRiskSizingQuote:
        details = self.get_market_details(instrument)
        contract_multiplier = self.contract_multipliers.get(instrument)
        if contract_multiplier is None or contract_multiplier <= 0:
            return BrokerRiskSizingQuote(
                instrument=instrument,
                precision=BrokerSizingPrecision.UNSUPPORTED,
                mode=BrokerSizingMode.UNSUPPORTED,
                sizing_available=False,
                reason_code="unsupported_sizing",
                reason="No contract multiplier configured for this broker/instrument.",
                entry_price=entry_price,
                risk_amount=risk_amount,
                min_stop_distance=details.min_normal_stop_or_limit_distance,
                details={"source": "contract_risk_broker"},
            )
        stop_distance, sizing_method = self._effective_stop_distance(
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            fallback_stop_distance=fallback_stop_distance,
            min_stop_distance=details.min_normal_stop_or_limit_distance,
        )
        risk_per_unit = stop_distance * contract_multiplier
        requested_size = risk_amount / max(risk_per_unit, 1e-9)
        normalization = self.normalize_order_size(instrument, requested_size)
        return BrokerRiskSizingQuote(
            instrument=instrument,
            precision=BrokerSizingPrecision.EXACT,
            mode=BrokerSizingMode.EXACT_CONTRACT_RISK,
            sizing_available=True,
            reason_code="quoted",
            reason="Contract-risk broker generated an exact risk sizing quote.",
            entry_price=entry_price,
            risk_amount=risk_amount,
            requested_size=max(requested_size, 0.0),
            normalized_size=normalization.normalized_size,
            risk_per_unit=risk_per_unit,
            stop_distance_price=stop_distance,
            sizing_method=sizing_method,
            min_stop_distance=details.min_normal_stop_or_limit_distance,
            normalization=normalization,
            details={"source": "contract_risk_broker", "contract_multiplier": contract_multiplier},
        )


def make_order_result(
    *,
    broker_reference: str,
    instrument: str,
    direction: OrderDirection,
    size: float,
    price: float,
    executed_at: datetime,
    client_request_id: str | None = None,
    average_fill_price: float | None = None,
) -> BrokerOrderResult:
    return BrokerOrderResult(
        broker_reference=broker_reference,
        instrument=instrument,
        direction=direction,
        size=size,
        price=price,
        executed_at=executed_at,
        client_request_id=client_request_id,
        filled_size=size,
        average_fill_price=average_fill_price or price,
        submitted_at=executed_at,
        acknowledged_at=executed_at,
    )


def make_broker_position(
    *,
    broker_reference: str,
    instrument: str,
    direction: OrderDirection,
    size: float,
    open_price: float,
    opened_at: datetime,
) -> BrokerPosition:
    return BrokerPosition(
        broker_reference=broker_reference,
        instrument=instrument,
        direction=direction,
        size=size,
        open_price=open_price,
        opened_at=opened_at,
    )
