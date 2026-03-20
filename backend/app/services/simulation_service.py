from __future__ import annotations

from dataclasses import dataclass
from random import Random

from sqlmodel import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.runtime import runtime_manager
from app.services.strategy_service import StrategyService
from app.services.trade_service import TradeService

logger = get_logger(__name__)


@dataclass
class MarketState:
    instrument: str
    strategy_name: str
    price: float
    drift: float
    volatility: float


class SimulationService:
    """
    Keeps realistic-ish market state outside the API layer.

    Requests can advance the simulator a small amount so the frontend sees a
    live-feeling backend while the trading engine remains the only component
    allowed to create strategy-driven trades.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.enabled = settings.simulation_mode
        self.random = Random(settings.simulation_seed)
        self.market_states: dict[str, MarketState] = {
            "IX.D.FTSE.DAILY.IP": MarketState(
                instrument="IX.D.FTSE.DAILY.IP",
                strategy_name="mean_reversion",
                price=8125.0,
                drift=0.45,
                volatility=16.0,
            ),
            "IX.D.NASDAQ.DAILY.IP": MarketState(
                instrument="IX.D.NASDAQ.DAILY.IP",
                strategy_name="breakout_guard",
                price=18910.0,
                drift=1.75,
                volatility=44.0,
            ),
            "IX.D.DAX.DAILY.IP": MarketState(
                instrument="IX.D.DAX.DAILY.IP",
                strategy_name="carry_drift",
                price=18480.0,
                drift=-0.8,
                volatility=28.0,
            ),
        }

    def bootstrap(self, session: Session) -> None:
        if not self.enabled:
            return

        trade_service = TradeService(session)
        if trade_service.list_trades() or trade_service.list_positions():
            self._ensure_default_runtimes()
            return

        self._ensure_default_runtimes()
        for _ in range(75):
            self.advance_market(session, ticks=1)
        logger.info("Simulation bootstrapped", extra={"ticks": 75})

    def advance_market(self, session: Session, ticks: int = 1) -> None:
        if not self.enabled:
            return

        self._ensure_default_runtimes()
        strategy_service = StrategyService(session)
        for _ in range(max(ticks, 1)):
            for state in self.market_states.values():
                next_price = self._next_price(state)
                state.price = next_price
                if runtime_manager.is_running(state.strategy_name):
                    strategy_service.process_price_update(state.instrument, next_price)

    def snapshot_prices(self) -> dict[str, float]:
        return {instrument: state.price for instrument, state in self.market_states.items()}

    def _ensure_default_runtimes(self) -> None:
        default_running = {"mean_reversion", "breakout_guard"}
        for state in self.market_states.values():
            if state.strategy_name in default_running and not runtime_manager.is_running(state.strategy_name):
                runtime_manager.start(strategy_name=state.strategy_name, instrument=state.instrument)

    def _next_price(self, state: MarketState) -> float:
        seasonal_push = self.random.uniform(-state.volatility, state.volatility)
        mean_reversion = (state.price * 0.0004) * (-1 if seasonal_push > 0 else 1)
        next_price = state.price + state.drift + (seasonal_push * 0.18) + mean_reversion
        return round(max(next_price, 1.0), 2)


simulation_service = SimulationService()
