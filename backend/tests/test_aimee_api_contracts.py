from __future__ import annotations

from app.services.domain_event_service import domain_event_service
from tests.test_http_route_harness import (
    AUTH_HEADER,
    _seed_http_read_state,
    _snapshot_rows,
)


def test_aimee_snapshot_openapi_contract_is_explicit(client_factory):
    with client_factory() as client:
        schema = client.app.openapi()

    response_schema = schema["paths"]["/aimee/snapshot"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    component = schema["components"]["schemas"]["AimeeSnapshotResponse"]

    assert response_schema == {"$ref": "#/components/schemas/AimeeSnapshotResponse"}
    assert set(component["properties"]) == {
        "review",
        "history",
        "controlPlane",
        "coverage",
        "telemetry",
        "events",
        "strategies",
        "updatedAt",
    }
    assert set(component["required"]) == {
        "review",
        "controlPlane",
        "coverage",
        "telemetry",
        "updatedAt",
    }


def test_aimee_snapshot_route_contract_preserves_shape_and_passive_no_write(
    session, client_factory
):
    _seed_http_read_state(session)
    before = _snapshot_rows(session)

    with client_factory(testing_routes_enabled=True) as client:
        response = client.get("/aimee/snapshot")

    assert response.status_code == 200, response.text
    payload = response.json()

    assert set(payload) == {
        "review",
        "history",
        "controlPlane",
        "coverage",
        "telemetry",
        "events",
        "strategies",
        "updatedAt",
    }
    assert payload["review"]["metadata"]["review_type"] == "operator_summary"
    assert (
        payload["review"]["metadata"]["source_coverage"]["broker_summary_available"]
        is False
    )
    assert isinstance(payload["controlPlane"]["entry_eligible"], bool)
    assert isinstance(payload["controlPlane"]["exit_eligible"], bool)
    assert isinstance(payload["controlPlane"]["open_risk_management_state"], str)
    assert payload["controlPlane"]["families"]
    assert payload["controlPlane"]["families"][0]["deployment"][
        "open_risk_management_state"
    ] in {"MANAGED", "NO_OPEN_RISK", "EXITS_ONLY", "UNMANAGED_OPEN_RISK", None}
    assert payload["telemetry"]["feed_source_state"] in {
        "LIVE",
        "POLLING_FALLBACK",
        "STALE",
        "DISCONNECTED",
    }
    assert payload["events"][0]["category"] == "runtime"
    assert isinstance(payload["updatedAt"], str)
    assert _snapshot_rows(session) == before


def test_operator_summary_and_review_history_routes_match_frontend_contract(
    session, client_factory
):
    _seed_http_read_state(session)

    with client_factory() as client:
        review_response = client.get("/reviews/operator-summary")
        history_response = client.get(
            "/reviews/history", params={"review_type": "operator_summary", "limit": 2}
        )

    assert review_response.status_code == 200, review_response.text
    assert history_response.status_code == 200, history_response.text

    review = review_response.json()
    history = history_response.json()

    assert set(review) == {
        "metadata",
        "facts",
        "derived_observations",
        "possible_contributors",
        "warnings",
        "supporting_metrics",
        "ai_summary",
        "provenance",
    }
    assert review["metadata"]["review_id"] is None
    assert review["metadata"]["review_type"] == "operator_summary"
    assert review["metadata"]["source_coverage"]["broker_summary_available"] is False
    assert isinstance(review["derived_observations"], list)

    assert history
    assert set(history[0]) == {
        "review_id",
        "review_type",
        "generated_at",
        "scope",
        "generation_mode",
        "provider",
        "model",
    }
    assert history[0]["review_type"] == "operator_summary"


def test_review_question_route_persists_only_advisory_artifact_and_audit_event(
    session, client_factory
):
    _seed_http_read_state(session)
    before = _snapshot_rows(session)

    with client_factory(
        app_env="production",
        operator_api_token="expected-token",
    ) as client:
        response = client.post(
            "/reviews/questions",
            json={"question": "What needs attention right now?"},
            headers=AUTH_HEADER,
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    after = _snapshot_rows(session)
    changed_models = {
        model_name for model_name in after if after[model_name] != before[model_name]
    }

    assert set(payload) == {
        "metadata",
        "facts",
        "derived_observations",
        "possible_contributors",
        "warnings",
        "supporting_metrics",
        "ai_summary",
        "provenance",
    }
    assert payload["metadata"]["review_type"] == "operational_question"
    assert payload["metadata"]["review_id"] is not None
    assert payload["facts"]["question"] == "What needs attention right now?"
    assert changed_models == {"DomainEvent", "GeneratedReviewRecord"}


def test_review_persistence_routes_preserve_shape_and_backend_error_detail(
    session, client_factory, monkeypatch
):
    _seed_http_read_state(session)

    with client_factory(
        app_env="production",
        operator_api_token="expected-token",
    ) as client:
        persist_response = client.get(
            "/reviews/operator-summary",
            params={"persist": "true"},
            headers=AUTH_HEADER,
        )

    assert persist_response.status_code == 200, persist_response.text
    persisted_payload = persist_response.json()
    assert persisted_payload["metadata"]["review_type"] == "operator_summary"
    assert persisted_payload["metadata"]["review_id"] is not None

    monkeypatch.setattr(
        domain_event_service,
        "record_event_in_session",
        lambda **_: None,
        raising=False,
    )

    with client_factory(
        app_env="production",
        operator_api_token="expected-token",
    ) as client:
        failed_response = client.post(
            "/reviews/questions",
            json={"question": "Summarize current control-plane issues."},
            headers=AUTH_HEADER,
        )

    assert failed_response.status_code == 503
    assert failed_response.json() == {
        "detail": "Advisory review was persisted, but durable audit persistence failed."
    }
