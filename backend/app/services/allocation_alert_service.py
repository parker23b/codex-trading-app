from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from sqlmodel import Session

from app.models.allocation_alert import AllocationAlert, utc_now
from app.services.allocation_read_service import AllocationReadService
from app.services.trade_service import TradeService


@dataclass(slots=True)
class AlertCandidate:
    alert_key: str
    alert_type: str
    severity: str
    escalation_level: str
    title: str
    message: str
    count: int
    intent_ids: list[int]
    cycle_ids: list[str]
    execution_ids: list[int]
    first_seen_at: object | None
    last_seen_at: object | None
    details: dict[str, object]


class AllocationAlertService:
    def __init__(self, session: Session):
        self.session = session
        self.trade_service = TradeService(session)
        self.read_service = AllocationReadService(session)

    def refresh_alerts(
        self, *, window_minutes: int | None = None
    ) -> list[AllocationAlert]:
        candidates = [
            self._candidate_from_read_model(item)
            for item in self.read_service.list_alerts(
                window_minutes=window_minutes, limit=200
            )
        ]
        active_keys = {candidate.alert_key for candidate in candidates}
        alerts: list[AllocationAlert] = []
        existing_by_key = {
            alert.alert_key: alert
            for alert in self.trade_service.list_allocation_alerts(limit=500)
        }
        for candidate in candidates:
            alert = existing_by_key.get(candidate.alert_key)
            now = utc_now()
            if alert is None:
                alert = AllocationAlert(
                    alert_key=candidate.alert_key,
                    alert_type=candidate.alert_type,
                    severity=candidate.severity,
                    escalation_level=candidate.escalation_level,
                    title=candidate.title,
                    message=candidate.message,
                    count=candidate.count,
                    first_seen_at=candidate.first_seen_at or now,
                    last_seen_at=candidate.last_seen_at or now,
                    last_evaluated_at=now,
                    escalated_at=now
                    if candidate.escalation_level in {"warning", "critical"}
                    else None,
                    related_intent_ids=candidate.intent_ids,
                    related_cycle_ids=candidate.cycle_ids,
                    related_execution_ids=candidate.execution_ids,
                    details=candidate.details,
                )
            else:
                if alert.state == "RESOLVED":
                    alert.state = "OPEN"
                    alert.recurrence_count += 1
                    alert.resolved_at = None
                    alert.resolved_by = None
                    alert.acknowledged_at = None
                    alert.acknowledged_by = None
                alert.severity = candidate.severity
                alert.escalation_level = candidate.escalation_level
                alert.title = candidate.title
                alert.message = candidate.message
                alert.count = candidate.count
                alert.last_seen_at = candidate.last_seen_at or now
                alert.last_evaluated_at = now
                alert.related_intent_ids = candidate.intent_ids
                alert.related_cycle_ids = candidate.cycle_ids
                alert.related_execution_ids = candidate.execution_ids
                alert.details = candidate.details
                if candidate.escalation_level in {"warning", "critical"}:
                    alert.escalated_at = alert.escalated_at or now
            alert.updated_at = now
            alerts.append(self.trade_service.upsert_allocation_alert(alert))

        for alert in self.trade_service.list_allocation_alerts(
            limit=500, states={"OPEN", "ACKNOWLEDGED"}
        ):
            if alert.alert_key in active_keys:
                continue
            alert.state = "RESOLVED"
            alert.resolved_at = utc_now()
            alert.updated_at = utc_now()
            alerts.append(self.trade_service.upsert_allocation_alert(alert))
        return alerts

    def list_alerts(
        self,
        *,
        limit: int = 100,
        include_resolved: bool = False,
        refresh: bool = False,
        window_minutes: int | None = None,
    ) -> list[AllocationAlert]:
        if refresh:
            self.refresh_alerts(window_minutes=window_minutes)
        states = None if include_resolved else {"OPEN", "ACKNOWLEDGED"}
        return self.trade_service.list_allocation_alerts(limit=limit, states=states)

    def acknowledge_alert(
        self, alert_id: int, *, actor_id: str = "operator"
    ) -> AllocationAlert | None:
        alert = self.trade_service.get_allocation_alert(alert_id)
        if alert is None:
            return None
        alert.state = "ACKNOWLEDGED"
        alert.acknowledged_at = utc_now()
        alert.acknowledged_by = actor_id
        alert.updated_at = utc_now()
        return self.trade_service.upsert_allocation_alert(alert)

    def resolve_alert(
        self, alert_id: int, *, actor_id: str = "operator"
    ) -> AllocationAlert | None:
        alert = self.trade_service.get_allocation_alert(alert_id)
        if alert is None:
            return None
        alert.state = "RESOLVED"
        alert.resolved_at = utc_now()
        alert.resolved_by = actor_id
        alert.updated_at = utc_now()
        return self.trade_service.upsert_allocation_alert(alert)

    @staticmethod
    def _candidate_from_read_model(item: dict[str, object]) -> AlertCandidate:
        details = dict(item.get("details") or {})
        intent_ids = [int(value) for value in item.get("intent_ids") or []]
        cycle_ids = [str(value) for value in item.get("cycle_ids") or []]
        execution_ids = [int(value) for value in item.get("execution_ids") or []]
        key_material = {
            "alert_type": item["alert_type"],
            "cycle_ids": cycle_ids,
            "intent_ids": intent_ids,
            "execution_ids": execution_ids,
            "detail_name": details.get("name"),
            "bucket_type": details.get("bucket_type"),
        }
        alert_key = f"{item['alert_type']}:{sha256(str(key_material).encode('utf-8')).hexdigest()[:16]}"
        severity = str(item["severity"])
        escalation_level = (
            "critical"
            if severity == "error"
            else "warning"
            if severity == "warning"
            else "none"
        )
        return AlertCandidate(
            alert_key=alert_key,
            alert_type=str(item["alert_type"]),
            severity=severity,
            escalation_level=escalation_level,
            title=str(item["title"]),
            message=str(item["message"]),
            count=int(item["count"]),
            intent_ids=intent_ids,
            cycle_ids=cycle_ids,
            execution_ids=execution_ids,
            first_seen_at=item.get("first_seen_at"),
            last_seen_at=item.get("last_seen_at"),
            details=AllocationAlertService._json_safe(details),
        )

    @staticmethod
    def _json_safe(value):
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {
                str(key): AllocationAlertService._json_safe(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [AllocationAlertService._json_safe(item) for item in value]
        return value
