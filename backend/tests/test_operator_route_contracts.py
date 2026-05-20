from __future__ import annotations

from tests.test_http_route_harness import AUTH_HEADER, _snapshot_rows


INSTRUMENT = "CS.D.EURUSD.CFD.IP"


def test_operator_summary_family_openapi_contracts_are_explicit(client_factory):
    with client_factory() as client:
        schema = client.app.openapi()

    route_expectations = {
        "/dashboard": "DashboardSnapshotResponse",
        "/control-plane/summary": "ControlPlaneSummaryResponse",
        "/control-plane/strategies/{strategy_name}": "ControlPlaneFamilyResponse",
        "/control-plane/governance/{strategy_name}": "GovernanceMutationResponse",
        "/control-plane/reconcile": "ControlPlaneReconcileResponse",
        "/strategies": "StrategySummaryResponse",
        "/strategy/start": "StrategyMutationStatusResponse",
        "/strategy/stop": "StrategyMutationStatusResponse",
    }
    for path, component_name in route_expectations.items():
        method = (
            "get"
            if path
            in {
                "/dashboard",
                "/control-plane/summary",
                "/control-plane/strategies/{strategy_name}",
                "/strategies",
            }
            else "post"
            if path == "/control-plane/reconcile" or path.startswith("/strategy/")
            else "put"
        )
        response_schema = schema["paths"][path][method]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        if path == "/strategies":
            assert response_schema["type"] == "array"
            assert response_schema["items"] == {
                "$ref": f"#/components/schemas/{component_name}"
            }
        else:
            assert response_schema == {"$ref": f"#/components/schemas/{component_name}"}

    assert set(
        schema["components"]["schemas"]["ControlPlaneFamilyResponse"]["properties"]
    ) >= {
        "strategy_name",
        "governance",
        "deployment",
        "runtime",
        "alignment",
        "recent_events",
    }
    assert set(
        schema["components"]["schemas"]["StrategySummaryResponse"]["properties"]
    ) >= {
        "governance_approval_state",
        "deployment_state",
        "active_runtimes",
        "persisted_runtimes",
        "open_positions",
        "parameters",
    }


def test_operator_summary_routes_preserve_passive_read_shape_and_uncertainty(
    session, client_factory
):
    before = _snapshot_rows(session)

    with client_factory() as client:
        summary_response = client.get("/control-plane/summary")
        family_response = client.get("/control-plane/strategies/mean_reversion")
        strategies_response = client.get("/strategies")
        dashboard_response = client.get("/dashboard")

    assert summary_response.status_code == 200, summary_response.text
    assert family_response.status_code == 200, family_response.text
    assert strategies_response.status_code == 200, strategies_response.text
    assert dashboard_response.status_code == 200, dashboard_response.text
    assert _snapshot_rows(session) == before

    summary = summary_response.json()
    family = family_response.json()
    strategies = strategies_response.json()
    dashboard = dashboard_response.json()

    assert set(summary) == {
        "autonomous_control_enabled",
        "configured_autonomous_control_enabled",
        "effective_autonomous_control_enabled",
        "autonomy_override_active",
        "autonomy_override_value",
        "autonomy_override_reason",
        "autonomy_updated_at",
        "feed_source_state",
        "feed_health_state",
        "broker_connectivity_state",
        "entry_eligible",
        "exit_eligible",
        "entry_eligibility_state",
        "exit_eligibility_state",
        "entry_block_reason",
        "exit_block_reason",
        "open_risk_management_state",
        "open_risk_management_reason",
        "families",
        "counts",
        "misaligned_count",
    }
    assert family["strategy_name"] == "mean_reversion"
    assert family["governance"]["approval_state"] == "UNKNOWN"
    assert family["deployment"] is None
    assert family["runtime"]["is_running"] is False
    assert family["runtime"]["runtime_mode"] == "STOPPED"
    assert family["alignment"]["is_aligned"] is None
    assert family["alignment"]["status"] == "NO_DEPLOYMENT"
    assert family["recent_events"] == []
    assert family["governance"]["max_concurrent_deployments"] is None

    mean_reversion = next(
        strategy for strategy in strategies if strategy["name"] == "mean_reversion"
    )
    assert mean_reversion["governance_approval_state"] == "UNKNOWN"
    assert mean_reversion["authorized"] is False
    assert mean_reversion["deployment_state"] == "UNASSIGNED"
    assert mean_reversion["active_runtimes"] == []
    assert mean_reversion["persisted_runtimes"] == []
    assert isinstance(mean_reversion["parameters"], list)

    assert set(dashboard) == {
        "accountValue",
        "accountValuePercent",
        "dailyPnl",
        "dailyPnlPercent",
        "openRisk",
        "winRate",
        "riskReward",
        "brokerInfo",
        "runningStrategies",
    }
    assert dashboard["brokerInfo"] is None
    assert isinstance(dashboard["runningStrategies"], list)


def test_operator_mutation_routes_expose_governance_reconcile_and_strategy_shapes(
    session, client_factory
):
    with client_factory(
        app_env="production",
        operator_api_token="expected-token",
    ) as client:
        reconcile_response = client.post(
            "/control-plane/reconcile",
            headers=AUTH_HEADER,
        )
        governance_response = client.put(
            "/control-plane/governance/mean_reversion",
            json={
                "approval_state": "APPROVED",
                "autonomous_operation_allowed": True,
                "approved_asset_classes": ["forex"],
                "approved_instruments": [INSTRUMENT],
                "approved_profile_names": ["default"],
                "max_concurrent_deployments": 2,
                "notes": "Route contract coverage",
            },
            headers=AUTH_HEADER,
        )
        start_response = client.post(
            "/strategy/start",
            json={"strategy_name": "mean_reversion", "instrument": INSTRUMENT},
            headers=AUTH_HEADER,
        )
        strategies_response = client.get("/strategies")
        stop_response = client.post(
            "/strategy/stop",
            json={"strategy_name": "mean_reversion", "instrument": INSTRUMENT},
            headers=AUTH_HEADER,
        )

    assert governance_response.status_code == 200, governance_response.text
    assert reconcile_response.status_code == 200, reconcile_response.text
    assert start_response.status_code == 200, start_response.text
    assert strategies_response.status_code == 200, strategies_response.text
    assert stop_response.status_code == 200, stop_response.text

    governance_payload = governance_response.json()
    reconcile_payload = reconcile_response.json()
    start_payload = start_response.json()
    stop_payload = stop_response.json()
    strategies_payload = strategies_response.json()

    assert set(governance_payload) == {
        "strategy_name",
        "approval_state",
        "autonomous_operation_allowed",
        "emergency_stop",
        "approved_asset_classes",
        "approved_instruments",
        "approved_profile_names",
        "max_concurrent_deployments",
        "notes",
        "updated_at",
    }
    assert governance_payload["strategy_name"] == "mean_reversion"
    assert governance_payload["autonomous_operation_allowed"] is True
    assert governance_payload["max_concurrent_deployments"] == 2
    assert governance_payload["notes"] == "Route contract coverage"

    assert set(reconcile_payload) == {
        "deployed",
        "paused",
        "blocked",
        "degraded",
        "emergency_stopped",
    }
    assert set(start_payload) == {"status", "strategy", "instrument"}
    assert start_payload == {
        "status": "started",
        "strategy": "mean_reversion",
        "instrument": INSTRUMENT,
    }
    assert stop_payload == {
        "status": "stopped",
        "strategy": "mean_reversion",
        "instrument": INSTRUMENT,
    }

    mean_reversion = next(
        strategy
        for strategy in strategies_payload
        if strategy["name"] == "mean_reversion"
    )
    assert mean_reversion["authorized"] is True
    assert mean_reversion["active_runtime_count"] == 1
    assert mean_reversion["active_runtimes"][0]["control_mode"] == "MANUAL"
    assert mean_reversion["active_runtimes"][0]["runtime_mode"] in {
        "NORMAL",
        "EXITS_ONLY",
        "STOPPED",
    }
    assert mean_reversion["persisted_runtimes"][0]["status"] == "RUNNING"
