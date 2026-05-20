from __future__ import annotations

from datetime import UTC, datetime
import io
import logging
import sys

from sqlmodel import select

from app.core.broker import AccountType, BrokerError
from app.core.logging import DomainEventErrorHandler, StructuredFormatter
from app.core.ig_broker import IGBroker, IGBrokerError
from app.models.domain_event import DomainEvent
from app.models.trade import Execution, ExecutionPhase, ExecutionStatus, TradeIntent
from app.services.domain_event_service import domain_event_service
from app.services.trade_service import TradeService


def test_audit_sec_002_record_error_redacts_exception_details(monkeypatch):
    captured: dict[str, object] = {}

    def _capture_event(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(domain_event_service, "record_event", _capture_event)

    try:
        raise RuntimeError(
            "Authorization: Bearer super-secret accountId=ACC-12345 dealReference=DEAL-67890"
        )
    except RuntimeError as exc:
        domain_event_service.record_error(
            error_type="RuntimeError",
            source="tests.redaction",
            title="Broker error",
            payload_json={
                "Authorization": "Bearer super-secret",
                "account_id": "ACC-12345",
                "response_body": {"dealReference": "DEAL-67890"},
            },
            exc=exc,
        )

    assert captured["message"] == (
        "Authorization: Bearer [REDACTED] accountId=[REDACTED] dealReference=[REDACTED]"
    )
    payload = captured["payload_json"]
    assert payload["Authorization"] == "[REDACTED]"
    assert payload["account_id"].startswith("[REDACTED_ACCOUNT_ID:")
    assert payload["response_body"] == "[RAW_BROKER_PAYLOAD REDACTED]"
    assert payload["exception_message"] == captured["message"]
    assert payload["traceback"] == "[TRACEBACK REDACTED]"


def test_audit_sec_002_record_event_in_session_redacts_sensitive_payload(session):
    event = domain_event_service.record_event_in_session(
        session=session,
        event_type="system.error",
        category="health",
        severity="error",
        source="tests.redaction",
        title="Authorization: Bearer abc123",
        message="accountId=ACC-12345 dealReference=DEAL-999",
        payload_json={
            "Authorization": "Bearer abc123",
            "account_id": "ACC-12345",
            "broker_reference": "DEAL-999",
            "response_text": '{"dealReference":"DEAL-999"}',
        },
    )

    assert event is not None
    persisted = session.exec(select(DomainEvent)).one()
    assert persisted.title == "Authorization: Bearer [REDACTED]"
    assert persisted.message == "accountId=[REDACTED] dealReference=[REDACTED]"
    assert persisted.payload_json["Authorization"] == "[REDACTED]"
    assert persisted.payload_json["account_id"].startswith("[REDACTED_ACCOUNT_ID:")
    assert persisted.payload_json["broker_reference"].startswith(
        "[REDACTED_BROKER_REF:"
    )
    assert persisted.payload_json["response_text"] == "[RAW_BROKER_PAYLOAD REDACTED]"


def test_audit_sec_002_execution_domain_event_redacts_nested_broker_result(session):
    trade_service = TradeService(session)
    intent = trade_service.create_trade_intent(
        TradeIntent(
            strategy_name="mean_reversion",
            instrument="CS.D.EURUSD.CFD.IP",
            direction="BUY",
            signal_time=datetime(2026, 5, 1, 9, 0, tzinfo=UTC),
            proposed_size=1.0,
            proposed_risk_percent=0.5,
            decision_reason_code="APPROVED",
            decision_reason="Approved for redaction audit.",
        )
    )
    execution = trade_service.create_execution(
        Execution(
            trade_intent_id=intent.id,
            strategy_name="mean_reversion",
            instrument="CS.D.EURUSD.CFD.IP",
            phase=ExecutionPhase.ENTRY.value,
            status=ExecutionStatus.SUBMISSION_PENDING.value,
            client_request_id="entry-redaction-1",
            signal_time=intent.signal_time,
            requested_size=1.0,
            requested_price=1.1,
            intended_risk_amount=50.0,
            details={"action_key": "entry:redaction"},
        )
    )

    trade_service.transition_execution(
        execution,
        status=ExecutionStatus.NEEDS_MANUAL_REVIEW,
        error_code="BROKER_CONFIRMATION_TIMEOUT",
        error_message=(
            "Authorization: Bearer secret-token accountId=ACC-99999 "
            "dealReference=DEAL-12345"
        ),
        requires_manual_review=True,
        details={
            "broker_result": {
                "broker_reference": "DEAL-12345",
                "account_id": "ACC-99999",
                "response_body": {"Authorization": "Bearer secret-token"},
                "error_message": (
                    "Authorization: Bearer secret-token dealReference=DEAL-12345"
                ),
            }
        },
    )

    events = list(session.exec(select(DomainEvent).order_by(DomainEvent.id)))
    event = events[-1]
    broker_result = event.payload_json["details"]["broker_result"]
    assert event.message == (
        "Authorization: Bearer [REDACTED] accountId=[REDACTED] dealReference=[REDACTED]"
    )
    assert broker_result["broker_reference"].startswith("[REDACTED_BROKER_REF:")
    assert broker_result["account_id"].startswith("[REDACTED_ACCOUNT_ID:")
    assert broker_result["response_body"] == "[RAW_BROKER_PAYLOAD REDACTED]"
    assert broker_result["error_message"] == (
        "Authorization: Bearer [REDACTED] dealReference=[REDACTED]"
    )


def test_audit_sec_002_broker_positions_route_redacts_broker_error_detail(
    client_factory, broker, monkeypatch
):
    monkeypatch.setattr("app.services.broker_service.get_broker", lambda: broker)
    broker.get_positions = lambda: (_ for _ in ()).throw(
        BrokerError(
            'IG request failed with status 403: {"accountId":"ACC-12345",'
            '"dealReference":"DEAL-11111","Authorization":"Bearer secret"}'
        )
    )

    with client_factory() as client:
        response = client.get("/broker/positions")

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "Unable to load broker positions" in detail
    assert "ACC-12345" not in detail
    assert "DEAL-11111" not in detail
    assert "secret" not in detail
    assert "[REDACTED]" in detail


def test_audit_sec_002_ig_broker_request_error_redacts_logs_and_exception(monkeypatch):
    broker = IGBroker(
        AccountType.DEMO,
        api_key="api-key-secret",
        username="user",
        password="password-secret",
        account_id="ACC-12345",
        base_url="https://example.test/gateway/deal",
        trading_enabled=True,
    )
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(StructuredFormatter("%(levelname)s [%(name)s] %(message)s"))
    logger = logging.getLogger("app.core.ig_broker")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    monkeypatch.setattr(
        broker,
        "_send_https_request",
        lambda **_: (
            403,
            '{"errorCode":"error.security.account-token-invalid","accountId":"ACC-12345","dealReference":"DEAL-1","Authorization":"Bearer secret"}',
            {},
        ),
    )
    try:
        try:
            broker._raw_request("GET", "/positions", version="2")
        except IGBrokerError as exc:
            message = str(exc)
        else:
            raise AssertionError("Expected IGBrokerError")
    finally:
        logger.removeHandler(handler)

    logs = stream.getvalue()
    assert message == (
        "IG request failed with status 403 (error.security.account-token-invalid)"
    )
    assert "ACC-12345" not in message
    assert "DEAL-1" not in message
    assert "Bearer secret" not in message
    assert "ACC-12345" not in logs
    assert "DEAL-1" not in logs
    assert "Bearer secret" not in logs
    assert "[RAW_BROKER_PAYLOAD REDACTED]" in logs


def test_audit_sec_002_log_mirroring_redacts_log_context(monkeypatch):
    captured: dict[str, object] = {}

    def _capture_error(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(domain_event_service, "record_error", _capture_error)
    handler = DomainEventErrorHandler()
    record = logging.makeLogRecord(
        {
            "name": "app.services.strategy_service",
            "levelno": logging.ERROR,
            "levelname": "ERROR",
            "msg": "Broker failure",
            "pathname": __file__,
            "lineno": 1,
            "funcName": "test_case",
            "Authorization": "Bearer super-secret",
            "account_id": "ACC-22222",
            "response_body": {"dealReference": "DEAL-22222"},
        }
    )

    handler.emit(record)

    payload = captured["payload_json"]
    assert payload["log_context"]["Authorization"] == "[REDACTED]"
    assert payload["log_context"]["account_id"].startswith("[REDACTED_ACCOUNT_ID:")
    assert payload["log_context"]["response_body"] == "[RAW_BROKER_PAYLOAD REDACTED]"


def test_audit_sec_002_structured_formatter_redacts_tracebacks():
    formatter = StructuredFormatter("%(levelname)s [%(name)s] %(message)s")
    try:
        raise RuntimeError("Authorization: Bearer trace-secret")
    except RuntimeError:
        record = logging.getLogger("app.tests.redaction").makeRecord(
            name="app.tests.redaction",
            level=logging.ERROR,
            fn=__file__,
            lno=1,
            msg="Traceback test",
            args=(),
            exc_info=sys.exc_info(),
        )

    output = formatter.format(record)
    assert "Traceback (most recent call last)" not in output
    assert "trace-secret" not in output
    assert "[TRACEBACK REDACTED]" in output
