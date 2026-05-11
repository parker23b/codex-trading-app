from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session, select

from app.core.config import get_settings
from app.models.operator_control import OperatorControlState


class OperatorControlService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()

    def get_existing_state(self) -> OperatorControlState | None:
        return self.session.exec(
            select(OperatorControlState).where(OperatorControlState.id == 1)
        ).first()

    def get_state(self) -> OperatorControlState:
        state = self.get_existing_state()
        if state is None:
            state = OperatorControlState(id=1)
            self.session.add(state)
            self.session.commit()
            self.session.refresh(state)
        return state

    def get_effective_autonomous_control_enabled(self) -> bool:
        state = self.get_existing_state()
        if state is None or state.autonomous_control_override is None:
            return self.settings.autonomous_control_enabled
        return state.autonomous_control_override

    def get_summary(self) -> dict[str, object]:
        state = self.get_existing_state()
        override_value = (
            state.autonomous_control_override if state is not None else None
        )
        return {
            "configured_autonomous_control_enabled": self.settings.autonomous_control_enabled,
            "effective_autonomous_control_enabled": self.get_effective_autonomous_control_enabled(),
            "override_active": override_value is not None,
            "override_value": override_value,
            "override_reason": state.override_reason if state is not None else None,
            "updated_at": state.updated_at if state is not None else None,
        }

    def update_autonomous_control(
        self,
        *,
        enabled: bool | None,
        reason: str | None = None,
    ) -> OperatorControlState:
        state = self.get_state()
        state.autonomous_control_override = enabled
        state.override_reason = reason
        state.updated_at = datetime.now(UTC)
        self.session.add(state)
        self.session.commit()
        self.session.refresh(state)
        return state
