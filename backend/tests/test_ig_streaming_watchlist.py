from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.services.ig_streaming_service import IGStreamingService
from app.services.watchlist_service import StreamingPlan


def test_reconcile_subscription_uses_watchlist_plan(monkeypatch):
    service = IGStreamingService()
    service.settings.ig_streaming_max_subscription_churn_per_minute = 20
    service._broker = type(
        "Broker",
        (),
        {
            "get_streaming_credentials": lambda self: type(
                "Creds",
                (),
                {"account_id": "acct", "lightstreamer_endpoint": "http://example.test"},
            )()
        },
    )()

    observed: dict[str, tuple[str, ...]] = {}
    monkeypatch.setattr(
        "app.services.ig_streaming_service.get_watchlist_service",
        lambda: type(
            "Watchlist",
            (),
            {
                "get_streaming_plan": lambda self: StreamingPlan(
                    instruments=("CS.D.EURUSD.CFD.IP",),
                    pinned_instruments=("CS.D.EURUSD.CFD.IP",),
                    capped_instruments=(),
                    asset_class_usage={"FOREX": 1},
                )
            },
        )(),
    )
    monkeypatch.setattr(service, "_reset_client", lambda credentials: setattr(service, "_credentials", credentials))
    monkeypatch.setattr(service, "_resubscribe", lambda instruments: observed.setdefault("instruments", instruments))

    asyncio.run(service._reconcile_subscription())

    assert observed["instruments"] == ("CS.D.EURUSD.CFD.IP",)


def test_reconcile_subscription_respects_churn_budget(monkeypatch):
    service = IGStreamingService()
    service.settings.ig_streaming_max_subscription_churn_per_minute = 1
    service._subscribed_instruments = ("CS.D.EURUSD.CFD.IP",)
    service._broker = type(
        "Broker",
        (),
        {
            "get_streaming_credentials": lambda self: type(
                "Creds",
                (),
                {"account_id": "acct", "lightstreamer_endpoint": "http://example.test"},
            )()
        },
    )()
    monkeypatch.setattr(
        "app.services.ig_streaming_service.get_watchlist_service",
        lambda: type(
            "Watchlist",
            (),
            {
                "get_streaming_plan": lambda self: StreamingPlan(
                    instruments=("CS.D.GBPUSD.CFD.IP",),
                    pinned_instruments=(),
                    capped_instruments=(),
                    asset_class_usage={"FOREX": 1},
                )
            },
        )(),
    )
    monkeypatch.setattr(service, "_reset_client", lambda credentials: setattr(service, "_credentials", credentials))
    called = {"count": 0}
    monkeypatch.setattr(service, "_resubscribe", lambda instruments: called.__setitem__("count", called["count"] + 1))

    asyncio.run(service._reconcile_subscription())

    assert called["count"] == 0
    assert service.get_health().last_error == "Subscription churn limit reached; keeping current streamed watchlist."
