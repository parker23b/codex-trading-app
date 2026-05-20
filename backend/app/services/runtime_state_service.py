from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, select

from app.core.runtime import runtime_manager
from app.models.runtime import StrategyRuntimeState
from app.models.trade import Position
from app.strategies.registry import strategy_registry


class RuntimeStateService:
    def __init__(self, session: Session):
        self.session = session

    def list_runtimes(self) -> list[StrategyRuntimeState]:
        statement = select(StrategyRuntimeState).order_by(
            StrategyRuntimeState.strategy_name, StrategyRuntimeState.instrument
        )
        return list(self.session.exec(statement))

    def list_active_runtimes(self) -> list[StrategyRuntimeState]:
        statement = select(StrategyRuntimeState).where(
            StrategyRuntimeState.status == "RUNNING"
        )
        return list(self.session.exec(statement))

    def get_runtime(
        self, strategy_name: str, instrument: str
    ) -> StrategyRuntimeState | None:
        statement = select(StrategyRuntimeState).where(
            StrategyRuntimeState.strategy_name == strategy_name,
            StrategyRuntimeState.instrument == instrument,
        )
        return self.session.exec(statement).first()

    def get_runtime_by_id(self, runtime_id: str) -> StrategyRuntimeState | None:
        statement = select(StrategyRuntimeState).where(
            StrategyRuntimeState.runtime_id == runtime_id
        )
        return self.session.exec(statement).first()

    def sync_engine_state(
        self,
        *,
        strategy_name: str,
        instrument: str,
        status: str,
        recovery_state: str,
        recovery_reason: str | None = None,
        control_mode: str | None = None,
        runtime_mode: str | None = None,
        deployment_id: int | None = None,
        active_profile_name: str | None = None,
        parameters: dict[str, Any] | None = None,
        auto_resume: bool = True,
        startup_context: dict[str, Any] | None = None,
        started_at: datetime | None = None,
        stopped_at: datetime | None = None,
        last_price_seen: float | None = None,
        last_price_seen_at: datetime | None = None,
        current_position: Position | None = None,
        current_position_broker_reference: str | None = None,
    ) -> StrategyRuntimeState:
        engine = runtime_manager.get_engine(strategy_name, instrument)
        if engine is None:
            raise ValueError(
                f"No active engine for strategy '{strategy_name}' on '{instrument}'."
            )

        runtime = self.get_runtime(strategy_name, instrument)
        metadata = strategy_registry.get_metadata(strategy_name)
        now = datetime.now(UTC)
        if runtime is None:
            runtime = StrategyRuntimeState(
                runtime_id=engine.runtime_id,
                strategy_name=strategy_name,
                strategy_version="1",
                instrument=instrument,
                parameters=parameters
                or {
                    parameter.key: parameter.value for parameter in metadata.parameters
                },
                started_at=started_at or now,
                control_mode=control_mode or "MANUAL",
                runtime_mode=runtime_mode or "NORMAL",
                deployment_id=deployment_id,
                active_profile_name=active_profile_name,
                startup_context=startup_context
                or getattr(engine, "startup_context", {}),
            )

        runtime.runtime_id = engine.runtime_id
        runtime.strategy_name = strategy_name
        runtime.strategy_version = "1"
        runtime.instrument = instrument
        runtime.parameters = (
            parameters
            or engine.strategy_parameters
            or {parameter.key: parameter.value for parameter in metadata.parameters}
        )
        runtime.status = status
        runtime.recovery_state = recovery_state
        runtime.recovery_reason = recovery_reason
        runtime.control_mode = control_mode or runtime.control_mode or "MANUAL"
        runtime.runtime_mode = runtime_mode or runtime.runtime_mode or "NORMAL"
        runtime.deployment_id = (
            deployment_id if deployment_id is not None else runtime.deployment_id
        )
        runtime.active_profile_name = (
            active_profile_name
            or engine.active_profile_name
            or runtime.active_profile_name
        )
        runtime.auto_resume = auto_resume
        runtime.startup_context = (
            startup_context
            or getattr(engine, "startup_context", None)
            or runtime.startup_context
            or {}
        )
        runtime.started_at = started_at or runtime.started_at
        runtime.stopped_at = stopped_at
        runtime.last_heartbeat_at = engine.last_heartbeat_at or now
        runtime.last_price_seen = last_price_seen
        runtime.last_price_seen_at = last_price_seen_at
        runtime.current_position_broker_reference = (
            current_position_broker_reference
            if current_position_broker_reference is not None
            else (
                current_position.broker_reference
                if current_position is not None
                else (
                    engine.current_position.broker_reference
                    if engine.current_position is not None
                    else None
                )
            )
        )
        runtime.strategy_state_snapshot = engine.strategy.export_state_snapshot()
        runtime.updated_at = now
        self.session.add(runtime)
        self.session.commit()
        self.session.refresh(runtime)
        return runtime

    def mark_stopped(
        self, engine_runtime_id: str, *, stopped_at: datetime | None = None
    ) -> StrategyRuntimeState | None:
        runtime = self.get_runtime_by_id(engine_runtime_id)
        if runtime is None:
            return None
        now = datetime.now(UTC)
        runtime.status = "STOPPED"
        runtime.recovery_state = "PAUSED"
        runtime.recovery_reason = None
        runtime.runtime_mode = "STOPPED"
        runtime.stopped_at = stopped_at or now
        runtime.last_heartbeat_at = runtime.stopped_at
        runtime.updated_at = now
        self.session.add(runtime)
        self.session.commit()
        self.session.refresh(runtime)
        return runtime

    def mark_recovery_state(
        self,
        *,
        strategy_name: str,
        instrument: str,
        recovery_state: str,
        recovery_reason: str | None,
        status: str | None = None,
        runtime_mode: str | None = None,
        current_position_broker_reference: str | None = None,
    ) -> StrategyRuntimeState | None:
        runtime = self.get_runtime(strategy_name, instrument)
        if runtime is None:
            return None
        runtime.recovery_state = recovery_state
        runtime.recovery_reason = recovery_reason
        if status is not None:
            runtime.status = status
        if runtime_mode is not None:
            runtime.runtime_mode = runtime_mode
        runtime.current_position_broker_reference = current_position_broker_reference
        runtime.updated_at = datetime.now(UTC)
        self.session.add(runtime)
        self.session.commit()
        self.session.refresh(runtime)
        return runtime
