from __future__ import annotations

from datetime import timedelta

from app.core.identifier_policy import project_identifier
from app.models.trade import Position, Trade
from app.services.trade_service import TradeService
from tests.test_http_route_harness import _snapshot_rows


def test_api_003_trade_route_family_openapi_contracts_are_explicit(client_factory):
    with client_factory() as client:
        schema = client.app.openapi()

    for path, component_name in {
        "/trades": "TradeResponse",
        "/trades/positions": "OpenPositionResponse",
        "/positions": "OpenPositionResponse",
    }.items():
        response_schema = schema["paths"][path]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        assert response_schema["type"] == "array"
        assert response_schema["items"] == {
            "$ref": f"#/components/schemas/{component_name}"
        }

    assert set(schema["components"]["schemas"]["TradeResponse"]["properties"]) >= {
        "entry_risk_amount",
        "risk_truth_confidence",
        "close_execution_source",
        "outcome",
    }
    assert set(
        schema["components"]["schemas"]["OpenPositionResponse"]["properties"]
    ) >= {
        "broker_sync_status",
        "risk_truth_confidence",
        "close_execution_source",
        "time_in_trade_seconds",
    }


def test_api_004_trade_route_family_preserves_provenance_and_consumer_shape(
    session, client_factory, fixed_now
):
    simulated_trade = Trade(
        strategy_name="mean_reversion",
        broker_reference="trade-entry-sim-1",
        close_broker_reference="trade-close-sim-1",
        instrument="CS.D.EURUSD.CFD.IP",
        direction="BUY",
        size=0.8,
        open_price=1.08,
        close_price=1.075,
        open_time=fixed_now - timedelta(hours=5),
        close_time=fixed_now - timedelta(hours=1),
        pnl=-40.0,
        entry_risk_amount=100.0,
        risk_truth_confidence="SIMULATED_LOCAL_FILL",
        close_execution_source="SIMULATED_LOCAL_CLOSE",
        r_multiple=-0.4,
        reason="Simulated close for regression coverage.",
        account_type="DEMO",
    )
    broker_trade = Trade(
        strategy_name="breakout",
        broker_reference="trade-entry-live-1",
        close_broker_reference="trade-close-live-1",
        instrument="IX.D.DAX.IFD.IP",
        direction="SELL",
        size=1.2,
        open_price=18500.0,
        close_price=18420.0,
        open_time=fixed_now - timedelta(days=1, hours=2),
        close_time=fixed_now - timedelta(days=1),
        pnl=96.0,
        entry_risk_amount=120.0,
        risk_truth_confidence="BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED",
        close_execution_source="BROKER_CONFIRMED",
        r_multiple=0.8,
        reason="Broker-confirmed close for parity coverage.",
        outcome="win",
        account_type="LIVE",
    )
    simulated_position = Position(
        strategy_name="mean_reversion",
        broker_reference="pos-sim-1",
        instrument="CS.D.EURUSD.CFD.IP",
        direction="BUY",
        size=0.8,
        open_price=1.08,
        open_time=fixed_now - timedelta(minutes=90),
        current_price=1.0825,
        unrealized_pnl=20.0,
        risk_percent=0.6,
        entry_risk_amount=100.0,
        risk_truth_confidence="SIMULATED_LOCAL_FILL",
        manual_override=True,
        account_type="DEMO",
        broker_sync_status="SIMULATED_LOCAL_FILL",
        reason="Awaiting broker confirmation.",
    )
    unknown_position = Position(
        strategy_name="breakout",
        broker_reference=None,
        instrument="IX.D.DAX.IFD.IP",
        direction="SELL",
        size=1.2,
        open_price=18500.0,
        open_time=fixed_now - timedelta(minutes=15),
        current_price=18480.0,
        unrealized_pnl=24.0,
        risk_percent=None,
        entry_risk_amount=120.0,
        risk_truth_confidence="UNKNOWN",
        manual_override=False,
        account_type="LIVE",
        broker_sync_status="UNKNOWN",
        reason="Broker sync state unavailable.",
    )
    session.add_all(
        [simulated_trade, broker_trade, simulated_position, unknown_position]
    )
    session.commit()

    before = _snapshot_rows(session)

    with client_factory() as client:
        trades_response = client.get("/trades")
        compat_positions_response = client.get("/trades/positions")
        positions_response = client.get("/positions")

    assert trades_response.status_code == 200, trades_response.text
    assert compat_positions_response.status_code == 200, compat_positions_response.text
    assert positions_response.status_code == 200, positions_response.text
    assert _snapshot_rows(session) == before

    trades = trades_response.json()
    compat_positions = compat_positions_response.json()
    positions = positions_response.json()

    assert len(trades) == 2
    simulated_trade_payload = next(
        item
        for item in trades
        if item["close_execution_source"] == "SIMULATED_LOCAL_CLOSE"
    )
    assert set(simulated_trade_payload) == {
        "id",
        "strategy_name",
        "broker_reference",
        "close_broker_reference",
        "close_execution_source",
        "instrument",
        "direction",
        "size",
        "open_price",
        "close_price",
        "open_time",
        "close_time",
        "pnl",
        "entry_risk_amount",
        "risk_truth_confidence",
        "account_type",
        "r_multiple",
        "reason",
        "outcome",
    }
    assert simulated_trade_payload["risk_truth_confidence"] == "SIMULATED_LOCAL_FILL"
    assert simulated_trade_payload["close_execution_source"] == "SIMULATED_LOCAL_CLOSE"
    assert simulated_trade_payload["outcome"] == "loss"
    assert simulated_trade_payload["broker_reference"] == project_identifier(
        "trade-entry-sim-1",
        kind="broker_reference",
    )
    assert simulated_trade_payload["close_broker_reference"] == project_identifier(
        "trade-close-sim-1",
        kind="broker_reference",
    )

    broker_trade_payload = next(
        item for item in trades if item["close_execution_source"] == "BROKER_CONFIRMED"
    )
    assert (
        broker_trade_payload["risk_truth_confidence"]
        == "BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED"
    )
    assert broker_trade_payload["outcome"] == "win"

    assert len(compat_positions) == 2
    assert len(positions) == 2

    compat_by_id = {item["id"]: item for item in compat_positions}
    positions_by_id = {item["id"]: item for item in positions}
    assert set(compat_by_id) == set(positions_by_id)
    for position_id, compat_payload in compat_by_id.items():
        direct_payload = positions_by_id[position_id]
        assert set(compat_payload) == {
            "id",
            "strategy_name",
            "broker_reference",
            "instrument",
            "direction",
            "size",
            "open_price",
            "close_price",
            "open_time",
            "close_time",
            "pnl",
            "account_type",
            "is_open",
            "current_price",
            "unrealized_pnl",
            "risk_percent",
            "entry_risk_amount",
            "risk_truth_confidence",
            "broker_sync_status",
            "close_execution_source",
            "reason",
            "manual_override",
            "time_in_trade_seconds",
        }
        assert compat_payload.keys() == direct_payload.keys()
        for key in compat_payload:
            if key == "time_in_trade_seconds":
                assert compat_payload[key] >= 0
                assert direct_payload[key] >= 0
                continue
            assert compat_payload[key] == direct_payload[key]

    simulated_position_payload = next(
        item
        for item in compat_positions
        if item["broker_sync_status"] == "SIMULATED_LOCAL_FILL"
    )
    assert simulated_position_payload["risk_truth_confidence"] == "SIMULATED_LOCAL_FILL"
    assert simulated_position_payload["broker_reference"] == project_identifier(
        "pos-sim-1",
        kind="broker_reference",
    )
    assert simulated_position_payload["close_execution_source"] is None

    unknown_position_payload = next(
        item for item in compat_positions if item["broker_sync_status"] == "UNKNOWN"
    )
    assert unknown_position_payload["risk_truth_confidence"] == "UNKNOWN"
    assert unknown_position_payload["broker_reference"] is None
    assert unknown_position_payload["reason"] == "Broker sync state unavailable."


def test_audit_sec_002_trade_route_family_serializes_redacted_persisted_reason_fields(
    session, client_factory, fixed_now
):
    trade_service = TradeService(session)
    trade_service.record_trade(
        Trade(
            strategy_name="mean_reversion",
            broker_reference="trade-redaction-entry-1",
            close_broker_reference="trade-redaction-close-1",
            instrument="CS.D.EURUSD.CFD.IP",
            direction="BUY",
            size=0.8,
            open_price=1.08,
            close_price=1.075,
            open_time=fixed_now - timedelta(hours=5),
            close_time=fixed_now - timedelta(hours=1),
            pnl=-40.0,
            entry_risk_amount=100.0,
            risk_truth_confidence="SIMULATED_LOCAL_FILL",
            close_execution_source="SIMULATED_LOCAL_CLOSE",
            reason=(
                "Authorization: Bearer trade-route-secret accountId=ACC-43210 "
                "dealReference=DEAL-43210"
            ),
            account_type="DEMO",
        )
    )
    trade_service.record_broker_position(
        Position(
            strategy_name="mean_reversion",
            broker_reference="pos-redaction-1",
            instrument="CS.D.EURUSD.CFD.IP",
            direction="BUY",
            size=0.8,
            open_price=1.08,
            open_time=fixed_now - timedelta(minutes=30),
            current_price=1.0825,
            unrealized_pnl=20.0,
            risk_percent=0.6,
            entry_risk_amount=100.0,
            risk_truth_confidence="SIMULATED_LOCAL_FILL",
            manual_override=False,
            account_type="DEMO",
            broker_sync_status="SIMULATED_LOCAL_FILL",
            reason=(
                "Authorization: Bearer position-route-secret accountId=ACC-54321 "
                "dealReference=DEAL-54321"
            ),
        )
    )

    with client_factory() as client:
        trades_response = client.get("/trades")
        positions_response = client.get("/positions")

    assert trades_response.status_code == 200, trades_response.text
    assert positions_response.status_code == 200, positions_response.text

    trade_payload = trades_response.json()[0]
    position_payload = positions_response.json()[0]

    assert trade_payload["reason"] == (
        "Authorization: Bearer [REDACTED] accountId=[REDACTED] dealReference=[REDACTED]"
    )
    assert position_payload["reason"] == (
        "Authorization: Bearer [REDACTED] accountId=[REDACTED] dealReference=[REDACTED]"
    )
