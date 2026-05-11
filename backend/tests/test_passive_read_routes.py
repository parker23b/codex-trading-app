from __future__ import annotations

from sqlmodel import select

from app.api.routes.control_plane import (
    get_control_plane_strategy_detail,
    get_operator_control_state,
)
from app.api.routes.strategies import list_strategies
from app.models.operator_control import OperatorControlState
from app.models.strategy_governance import StrategyFamilyGovernance


def test_audit_api_001_operator_state_get_does_not_seed_default_row(session):
    response = get_operator_control_state(session)

    assert response.override_active is False
    assert response.override_value is None
    assert response.updated_at is None
    assert session.exec(select(OperatorControlState)).all() == []


def test_audit_api_001_control_plane_strategy_detail_does_not_seed_governance(
    session,
):
    detail = get_control_plane_strategy_detail("mean_reversion", session)

    assert detail["strategy_name"] == "mean_reversion"
    assert detail["governance"]["approval_state"] == "UNKNOWN"
    assert session.exec(select(StrategyFamilyGovernance)).all() == []


def test_audit_api_001_strategy_list_get_does_not_seed_governance(session):
    strategies = list_strategies(session)

    assert strategies
    mean_reversion = next(
        strategy for strategy in strategies if strategy["name"] == "mean_reversion"
    )
    assert mean_reversion["governance_approval_state"] == "UNKNOWN"
    assert mean_reversion["authorized"] is False
    assert session.exec(select(StrategyFamilyGovernance)).all() == []
