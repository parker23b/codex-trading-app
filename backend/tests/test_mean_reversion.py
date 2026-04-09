from __future__ import annotations

from app.core.broker import OrderDirection
from app.strategies.base import PriceUpdate
from app.strategies.mean_reversion import MeanReversionStrategy


def test_mean_reversion_defaults_are_fx_friendly_enough_to_trigger_on_modest_deviation():
    strategy = MeanReversionStrategy()
    prices = [1.1000] * 19 + [1.0982]

    for price in prices:
        strategy.on_price_update(
            PriceUpdate(
                instrument="CS.D.EURUSD.CFD.IP",
                price=price,
            )
        )

    assert strategy.should_enter_trade() is True
    assert strategy.entry_direction() is OrderDirection.BUY
