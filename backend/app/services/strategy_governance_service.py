from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session, select

from app.models.strategy_governance import (
    GovernanceApprovalState,
    StrategyFamilyGovernance,
)
from app.strategies.registry import strategy_registry


class StrategyGovernanceService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def ensure_defaults(self) -> list[StrategyFamilyGovernance]:
        records: list[StrategyFamilyGovernance] = []
        now = datetime.now(UTC)
        for metadata in strategy_registry.list_metadata():
            record = self.get_strategy(metadata.name)
            if record is None:
                profile_names = [
                    profile.name for profile in metadata.parameter_profiles
                ] or ["default"]
                record = StrategyFamilyGovernance(
                    strategy_name=metadata.name,
                    approval_state=GovernanceApprovalState.APPROVED.value,
                    autonomous_operation_allowed=True,
                    approved_asset_classes=list(metadata.supported_asset_classes),
                    approved_profile_names=profile_names,
                    max_concurrent_deployments=1,
                    created_at=now,
                    updated_at=now,
                )
                self.session.add(record)
                self.session.commit()
                self.session.refresh(record)
            else:
                changed = False
                if self._should_promote_legacy_default_autonomy(record):
                    record.autonomous_operation_allowed = True
                    changed = True
                if (
                    not record.approved_asset_classes
                    and metadata.supported_asset_classes
                ):
                    record.approved_asset_classes = list(
                        metadata.supported_asset_classes
                    )
                    changed = True
                if not record.approved_profile_names:
                    record.approved_profile_names = [
                        profile.name for profile in metadata.parameter_profiles
                    ] or ["default"]
                    changed = True
                if changed:
                    record.updated_at = now
                    self.session.add(record)
                    self.session.commit()
                    self.session.refresh(record)
            records.append(record)
        return records

    @staticmethod
    def _should_promote_legacy_default_autonomy(
        record: StrategyFamilyGovernance,
    ) -> bool:
        if record.autonomous_operation_allowed:
            return False
        if (
            record.emergency_stop
            or record.approval_state != GovernanceApprovalState.APPROVED.value
        ):
            return False
        # Heuristic: records that still look untouched since default seeding should inherit
        # the new autonomy-allowed default, while explicitly edited records stay as-is.
        same_timestamp = (
            abs((record.updated_at - record.created_at).total_seconds()) < 1
        )
        return same_timestamp and not record.notes and not record.approved_instruments

    def list_strategies(self) -> list[StrategyFamilyGovernance]:
        self.ensure_defaults()
        statement = select(StrategyFamilyGovernance).order_by(
            StrategyFamilyGovernance.strategy_name
        )
        return list(self.session.exec(statement))

    def get_strategy(self, strategy_name: str) -> StrategyFamilyGovernance | None:
        statement = select(StrategyFamilyGovernance).where(
            StrategyFamilyGovernance.strategy_name == strategy_name
        )
        return self.session.exec(statement).first()

    def upsert_strategy(
        self,
        *,
        strategy_name: str,
        approval_state: str | None = None,
        autonomous_operation_allowed: bool | None = None,
        emergency_stop: bool | None = None,
        approved_asset_classes: list[str] | None = None,
        approved_instruments: list[str] | None = None,
        approved_profile_names: list[str] | None = None,
        max_concurrent_deployments: int | None = None,
        notes: str | None = None,
    ) -> StrategyFamilyGovernance:
        self.ensure_defaults()
        record = self.get_strategy(strategy_name)
        if record is None:
            raise ValueError(f"Strategy family '{strategy_name}' is not registered.")
        if approval_state is not None:
            record.approval_state = approval_state
        if autonomous_operation_allowed is not None:
            record.autonomous_operation_allowed = autonomous_operation_allowed
        if emergency_stop is not None:
            record.emergency_stop = emergency_stop
        if approved_asset_classes is not None:
            record.approved_asset_classes = [
                value.upper() for value in approved_asset_classes
            ]
        if approved_instruments is not None:
            record.approved_instruments = approved_instruments
        if approved_profile_names is not None:
            record.approved_profile_names = approved_profile_names
        if max_concurrent_deployments is not None:
            record.max_concurrent_deployments = max_concurrent_deployments
        if notes is not None:
            record.notes = notes
        record.updated_at = datetime.now(UTC)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record
