from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, desc, select

from app.models.open_risk_authority import OpenRiskAuthority
from app.models.runtime import StrategyRuntimeState
from app.models.strategy_deployment import StrategyDeployment
from app.models.trade import Execution, Position


OPEN_RISK_SCOPE_KEY = "primary"
OPEN_RISK_STATE_PRECEDENCE = {
    "NO_OPEN_RISK": 0,
    "MANAGED": 1,
    "EXITS_ONLY": 2,
    "UNMANAGED_OPEN_RISK": 3,
}


class OpenRiskAuthorityService:
    """Owns the persisted open-risk management snapshot for the active risk book."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self) -> OpenRiskAuthority | None:
        return self.session.exec(
            select(OpenRiskAuthority).where(
                OpenRiskAuthority.scope_key == OPEN_RISK_SCOPE_KEY
            )
        ).first()

    def get_or_derive(self) -> OpenRiskAuthority:
        authority = self.get()
        if authority is not None:
            return authority
        return self._build_authority(
            authority=None,
            source="legacy_uninitialized_read",
            reconciliation_status="UNKNOWN",
            reconciled_at=None,
        )

    def refresh(
        self,
        *,
        source: str,
        reconciliation_status: str | None = None,
        reconciled_at: datetime | None = None,
    ) -> OpenRiskAuthority:
        authority = self.session.exec(
            select(OpenRiskAuthority)
            .where(OpenRiskAuthority.scope_key == OPEN_RISK_SCOPE_KEY)
            .with_for_update()
        ).first()
        updated = self._build_authority(
            authority=authority,
            source=source,
            reconciliation_status=reconciliation_status,
            reconciled_at=reconciled_at,
        )
        self.session.add(updated)
        self.session.commit()
        self.session.refresh(updated)
        return updated

    def _build_authority(
        self,
        *,
        authority: OpenRiskAuthority | None,
        source: str,
        reconciliation_status: str | None,
        reconciled_at: datetime | None,
    ) -> OpenRiskAuthority:
        now = datetime.now(UTC)
        positions = list(
            self.session.exec(
                select(Position)
                .where(Position.is_open.is_(True))
                .order_by(Position.instrument, Position.id)
            )
        )
        runtimes = list(
            self.session.exec(
                select(StrategyRuntimeState).order_by(
                    desc(StrategyRuntimeState.updated_at)
                )
            )
        )
        deployments = {
            deployment.strategy_name: deployment
            for deployment in self.session.exec(select(StrategyDeployment))
        }
        manual_review_position_ids = {
            position_id
            for position_id in self.session.exec(
                select(Execution.local_position_id).where(
                    Execution.requires_manual_review.is_(True),
                    Execution.local_position_id.is_not(None),
                )
            )
            if position_id is not None
        }

        items = [
            self._build_item(
                position=position,
                runtimes=runtimes,
                deployment=deployments.get(position.strategy_name),
                requires_manual_review=position.id in manual_review_position_ids,
            )
            for position in positions
        ]
        state = max(
            (str(item["state"]) for item in items),
            key=lambda value: OPEN_RISK_STATE_PRECEDENCE[value],
            default="NO_OPEN_RISK",
        )
        effective_reconciliation_status = reconciliation_status or (
            authority.reconciliation_status if authority is not None else "UNKNOWN"
        )
        effective_reconciled_at = (
            reconciled_at
            if reconciled_at is not None
            else authority.last_reconciled_at
            if authority is not None
            else None
        )
        if positions and effective_reconciliation_status == "UNAVAILABLE":
            state = "UNMANAGED_OPEN_RISK"

        reason = self._aggregate_reason(
            state=state,
            items=items,
            reconciliation_status=effective_reconciliation_status,
        )
        snapshot_json = {
            "scope_key": OPEN_RISK_SCOPE_KEY,
            "source": source,
            "state": state,
            "reason": reason,
            "reconciliation_status": effective_reconciliation_status,
            "last_reconciled_at": (
                effective_reconciled_at.isoformat()
                if effective_reconciled_at is not None
                else None
            ),
            "items": items,
        }
        if authority is None:
            return OpenRiskAuthority(
                scope_key=OPEN_RISK_SCOPE_KEY,
                version=1,
                state=state,
                reason=reason,
                open_position_count=len(positions),
                reconciliation_status=effective_reconciliation_status,
                last_reconciled_at=effective_reconciled_at,
                snapshot_json=snapshot_json,
                updated_at=now,
            )

        authority.version += 1
        authority.state = state
        authority.reason = reason
        authority.open_position_count = len(positions)
        authority.reconciliation_status = effective_reconciliation_status
        authority.last_reconciled_at = effective_reconciled_at
        authority.snapshot_json = snapshot_json
        authority.updated_at = now
        return authority

    @staticmethod
    def _build_item(
        *,
        position: Position,
        runtimes: list[StrategyRuntimeState],
        deployment: StrategyDeployment | None,
        requires_manual_review: bool,
    ) -> dict[str, Any]:
        runtime = next(
            (
                candidate
                for candidate in runtimes
                if candidate.strategy_name == position.strategy_name
                and candidate.instrument == position.instrument
                and candidate.status == "RUNNING"
            ),
            None,
        )
        state = "UNMANAGED_OPEN_RISK"
        reason = "Open position has no running persisted runtime with exit authority."
        if runtime is not None and runtime.recovery_state == "RUNNING":
            if runtime.runtime_mode == "EXITS_ONLY" or requires_manual_review:
                state = "EXITS_ONLY"
                reason = (
                    "Open position is restricted to exits while manual review is required."
                    if requires_manual_review
                    else "Open position is owned by an EXITS_ONLY runtime."
                )
            elif runtime.runtime_mode == "NORMAL":
                state = "MANAGED"
                reason = "Open position is owned by a running normal-mode runtime."
            else:
                reason = (
                    f"Running runtime mode {runtime.runtime_mode} is not exit-capable."
                )

        if deployment is not None:
            if deployment.open_risk_management_state == "UNMANAGED_OPEN_RISK":
                state = "UNMANAGED_OPEN_RISK"
                reason = (
                    deployment.open_risk_management_reason
                    or "Deployment explicitly marks this exposure as unmanaged."
                )
            elif (
                deployment.open_risk_management_state == "EXITS_ONLY"
                and state != "UNMANAGED_OPEN_RISK"
            ):
                state = "EXITS_ONLY"
                reason = (
                    deployment.open_risk_management_reason
                    or "Deployment restricts this exposure to exits only."
                )

        return {
            "position_id": position.id,
            "trade_intent_id": position.trade_intent_id,
            "strategy_name": position.strategy_name,
            "instrument": position.instrument,
            "state": state,
            "reason": reason,
            "runtime_id": runtime.runtime_id if runtime is not None else None,
            "runtime_mode": runtime.runtime_mode if runtime is not None else None,
            "runtime_recovery_state": (
                runtime.recovery_state if runtime is not None else None
            ),
            "deployment_id": deployment.id if deployment is not None else None,
            "broker_sync_status": position.broker_sync_status,
            "last_reconciled_at": (
                position.last_reconciled_at.isoformat()
                if position.last_reconciled_at is not None
                else None
            ),
            "requires_manual_review": requires_manual_review,
        }

    @staticmethod
    def _aggregate_reason(
        *,
        state: str,
        items: list[dict[str, Any]],
        reconciliation_status: str,
    ) -> str | None:
        if not items:
            return None
        if reconciliation_status == "UNAVAILABLE":
            return "Broker reconciliation is unavailable while open positions exist."
        affected = [item for item in items if item["state"] == state]
        if not affected:
            return None
        instruments = ", ".join(str(item["instrument"]) for item in affected)
        if state == "UNMANAGED_OPEN_RISK":
            return f"Open risk on {instruments} lacks verified exit authority."
        if state == "EXITS_ONLY":
            return f"Open risk on {instruments} is restricted to exits only."
        return f"{len(items)} open position(s) have persisted runtime ownership."
