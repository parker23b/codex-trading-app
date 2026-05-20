from __future__ import annotations

from datetime import timedelta

from app.models.trade import Position, TradeIntent
from tests.test_http_route_harness import _snapshot_rows


def test_api_003_risk_allocation_chart_openapi_contract_is_explicit(client_factory):
    with client_factory() as client:
        schema = client.app.openapi()

    response_schema = schema["paths"]["/charts/risk-allocation"]["get"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"]
    assert response_schema == {
        "$ref": "#/components/schemas/RiskAllocationChartResponse"
    }
    assert set(
        schema["components"]["schemas"]["RiskAllocationChartResponse"]["properties"]
    ) >= {
        "generated_at",
        "data_status",
        "source",
        "chart_mode",
        "summary",
        "bars",
        "reasons",
        "notes",
    }


def test_risk_017_risk_allocation_chart_keeps_unknown_truth_unavailable_not_zero(
    session, client_factory, fixed_now
):
    session.add(
        Position(
            strategy_name="mean_reversion",
            family_name="FX",
            broker_reference="risk-unknown-1",
            instrument="CS.D.EURUSD.CFD.IP",
            direction="BUY",
            size=1.0,
            open_price=1.08,
            open_time=fixed_now - timedelta(minutes=45),
            current_price=1.081,
            unrealized_pnl=10.0,
            risk_percent=None,
            entry_risk_amount=None,
            risk_truth_confidence="UNKNOWN",
            account_type="DEMO",
            broker_sync_status="UNKNOWN",
        )
    )
    session.commit()
    before = _snapshot_rows(session)

    with client_factory() as client:
        response = client.get("/charts/risk-allocation")

    assert response.status_code == 200, response.text
    assert _snapshot_rows(session) == before
    payload = response.json()

    assert payload["data_status"] == "UNAVAILABLE"
    assert payload["source"] == "ALLOCATION_EXPOSURE_SUMMARY_PLUS_POSITION_INTENT_TRUTH"
    assert "unknown_live_position_risk_truth" in payload["reasons"]
    assert payload["summary"]["live_risk_percent"] is None
    assert payload["summary"]["total_active_risk_percent"] is None
    assert payload["summary"]["open_position_count"] == 1
    assert payload["summary"]["has_unknown_risk"] is True
    assert payload["summary"]["chartable_bucket_count"] == 0
    assert payload["summary"]["unavailable_bucket_count"] == 1

    bar = payload["bars"][0]
    assert bar["instrument"] == "CS.D.EURUSD.CFD.IP"
    assert bar["data_status"] == "UNAVAILABLE"
    assert bar["live_risk_percent"] is None
    assert bar["total_risk_percent"] is None
    assert bar["has_unknown_risk"] is True
    assert "unknown_live_position_risk_truth" in bar["reasons"]
    assert {"confidence": "UNKNOWN", "count": 1} in bar["risk_truth_confidence_mix"]


def test_risk_006_risk_allocation_chart_marks_partial_and_simulated_truth(
    session, client_factory, fixed_now
):
    session.add(
        Position(
            strategy_name="mean_reversion",
            family_name="FX",
            broker_reference="risk-partial-1",
            instrument="CS.D.EURUSD.CFD.IP",
            direction="BUY",
            size=1.0,
            open_price=1.08,
            open_time=fixed_now - timedelta(minutes=90),
            current_price=1.082,
            unrealized_pnl=20.0,
            risk_percent=1.25,
            entry_risk_amount=125.0,
            risk_truth_confidence="PARTIAL_FILL_PROVISIONAL",
            account_type="DEMO",
            broker_sync_status="SIMULATED_LOCAL_FILL",
        )
    )
    session.add(
        TradeIntent(
            strategy_name="breakout",
            family_name="FX",
            instrument="CS.D.EURUSD.CFD.IP",
            direction="BUY",
            state="APPROVED",
            signal_time=fixed_now - timedelta(minutes=10),
            allocated_risk_percent=0.75,
            estimated_risk_amount=75.0,
            risk_truth_confidence="ALLOCATION_INTENT_ONLY",
        )
    )
    session.commit()

    with client_factory() as client:
        response = client.get("/charts/risk-allocation")

    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["data_status"] == "PARTIAL"
    assert payload["summary"]["has_provisional_risk"] is True
    assert payload["summary"]["has_simulated_risk"] is True
    assert payload["summary"]["reserved_risk_percent"] == 0.75
    assert payload["summary"]["live_risk_percent"] == 1.25
    assert payload["summary"]["provisional_live_risk_percent"] == 1.25
    assert payload["summary"]["total_active_risk_percent"] == 2.0
    assert "partial_fill_provisional_live_risk" in payload["reasons"]
    assert "simulated_local_live_risk" in payload["reasons"]
    assert "reserved_intent_only_risk" in payload["reasons"]

    bar = payload["bars"][0]
    assert bar["instrument"] == "CS.D.EURUSD.CFD.IP"
    assert bar["data_status"] == "PARTIAL"
    assert bar["live_risk_percent"] == 1.25
    assert bar["reserved_risk_percent"] == 0.75
    assert bar["provisional_live_risk_percent"] == 1.25
    assert bar["total_risk_percent"] == 2.0
    assert bar["has_provisional_risk"] is True
    assert bar["has_simulated_risk"] is True
    assert {"confidence": "PARTIAL_FILL_PROVISIONAL", "count": 1} in bar[
        "risk_truth_confidence_mix"
    ]
    assert {"confidence": "ALLOCATION_INTENT_ONLY", "count": 1} in bar[
        "risk_truth_confidence_mix"
    ]
