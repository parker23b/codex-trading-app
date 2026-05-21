from __future__ import annotations

import ast
from pathlib import Path

import pytest


pytestmark = pytest.mark.usefixtures("audit_critical_domain_events")

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
IGNORED_HELPER_FILES = {
    "app/api/audit.py",
    "app/services/audit_event_recorder.py",
    "app/services/domain_event_service.py",
}
WRITE_CALLS = {
    "persist_required_domain_event",
    "record_required_domain_event",
    "domain_event_service.record_event_in_session",
    "domain_event_service.record_event",
    "self.event_service.record_event",
}
EXPECTED_AUDIT_WRITE_PATHS = {
    (
        "REQUIRED_DURABLE",
        "app/api/routes/ai_reviewer.py",
        "_persist_review_audit_event",
        "persist_required_domain_event",
    ),
    (
        "REQUIRED_DURABLE",
        "app/api/routes/allocation.py",
        "_persist_alert_mutation_event",
        "persist_required_domain_event",
    ),
    (
        "REQUIRED_DURABLE",
        "app/api/routes/control_plane.py",
        "reconcile_control_plane",
        "persist_required_domain_event",
    ),
    (
        "REQUIRED_DURABLE",
        "app/api/routes/control_plane.py",
        "update_operator_control_state",
        "persist_required_domain_event",
    ),
    (
        "REQUIRED_DURABLE",
        "app/api/routes/control_plane.py",
        "update_strategy_governance",
        "persist_required_domain_event",
    ),
    (
        "REQUIRED_DURABLE",
        "app/api/routes/markets.py",
        "add_shortlist_item",
        "persist_required_domain_event",
    ),
    (
        "REQUIRED_DURABLE",
        "app/api/routes/markets.py",
        "add_strategy_watchlist_items",
        "persist_required_domain_event",
    ),
    (
        "REQUIRED_DURABLE",
        "app/api/routes/markets.py",
        "remove_shortlist_item",
        "persist_required_domain_event",
    ),
    (
        "REQUIRED_DURABLE",
        "app/api/routes/markets.py",
        "remove_strategy_watchlist_item",
        "persist_required_domain_event",
    ),
    (
        "REQUIRED_DURABLE",
        "app/api/routes/strategies.py",
        "start_strategy",
        "persist_required_domain_event",
    ),
    (
        "REQUIRED_DURABLE",
        "app/api/routes/strategies.py",
        "start_strategy_by_name",
        "persist_required_domain_event",
    ),
    (
        "REQUIRED_DURABLE",
        "app/api/routes/strategies.py",
        "stop_strategy",
        "persist_required_domain_event",
    ),
    (
        "REQUIRED_DURABLE",
        "app/api/routes/strategies.py",
        "stop_strategy_by_name",
        "persist_required_domain_event",
    ),
    (
        "REQUIRED_DURABLE",
        "app/services/coverage_allocator_service.py",
        "CoverageAllocatorService._reject_request",
        "record_required_domain_event",
    ),
    (
        "REQUIRED_DURABLE",
        "app/services/coverage_allocator_service.py",
        "CoverageAllocatorService.allocate_pending_promotions",
        "record_required_domain_event",
    ),
    (
        "REQUIRED_DURABLE",
        "app/services/market_data_service.py",
        "MarketDataService._record_polling_health_event",
        "record_required_domain_event",
    ),
    (
        "REQUIRED_DURABLE",
        "app/services/market_data_service.py",
        "MarketDataService._refresh_tier2_once",
        "record_required_domain_event",
    ),
    (
        "REQUIRED_DURABLE",
        "app/services/reconciliation_service.py",
        "ReconciliationService._record_required_reconciliation_event",
        "record_required_domain_event",
    ),
    (
        "REQUIRED_DURABLE",
        "app/services/runtime_recovery_service.py",
        "RuntimeRecoveryService._record_required_runtime_event",
        "record_required_domain_event",
    ),
    (
        "REQUIRED_DURABLE",
        "app/services/strategy_deployment_manager_service.py",
        "StrategyDeploymentManagerService._handle_non_auto_runtime_transition",
        "record_required_domain_event",
    ),
    (
        "REQUIRED_DURABLE",
        "app/services/strategy_deployment_manager_service.py",
        "StrategyDeploymentManagerService.reconcile",
        "record_required_domain_event",
    ),
    (
        "REQUIRED_DURABLE",
        "app/services/strategy_service.py",
        "StrategyService._execute_entry_signal",
        "record_required_domain_event",
    ),
    (
        "REQUIRED_DURABLE",
        "app/services/strategy_service.py",
        "StrategyService._prepare_execution",
        "record_required_domain_event",
    ),
    (
        "REQUIRED_DURABLE",
        "app/services/strategy_service.py",
        "StrategyService._record_close_broker_action_event",
        "record_required_domain_event",
    ),
    (
        "REQUIRED_DURABLE",
        "app/services/strategy_service.py",
        "StrategyService._record_domain_event",
        "record_required_domain_event",
    ),
    (
        "SESSION_BOUND_DURABLE",
        "app/services/capital_allocator_service.py",
        "CapitalAllocatorService._persist_cycle_summary",
        "domain_event_service.record_event_in_session",
    ),
    (
        "SESSION_BOUND_DURABLE",
        "app/services/trade_service.py",
        "TradeService._record_execution_created_domain_event",
        "domain_event_service.record_event_in_session",
    ),
    (
        "SESSION_BOUND_DURABLE",
        "app/services/trade_service.py",
        "TradeService._record_execution_domain_event",
        "domain_event_service.record_event_in_session",
    ),
    (
        "SESSION_BOUND_DURABLE",
        "app/services/trade_service.py",
        "TradeService._record_trade_intent_created_domain_event",
        "domain_event_service.record_event_in_session",
    ),
    (
        "SESSION_BOUND_DURABLE",
        "app/services/trade_service.py",
        "TradeService._record_trade_intent_transition_domain_event",
        "domain_event_service.record_event_in_session",
    ),
    (
        "BEST_EFFORT_INFORMATIONAL",
        "app/services/market_data_service.py",
        "MarketDataService._record_polling_health_event",
        "domain_event_service.record_event",
    ),
    (
        "BEST_EFFORT_INFORMATIONAL",
        "app/services/strategy_service.py",
        "StrategyService._record_domain_event",
        "self.event_service.record_event",
    ),
}
EXPECTED_BROKER_ACTION_ROUTE_OWNERS = {
    (
        "app/api/routes/control_plane.py",
        "reconcile_control_plane",
        "reconcile",
    ),
    (
        "app/api/routes/strategies.py",
        "start_strategy",
        "start_strategy",
    ),
    (
        "app/api/routes/strategies.py",
        "start_strategy_by_name",
        "start_strategy",
    ),
    (
        "app/api/routes/strategies.py",
        "stop_strategy",
        "stop_strategy",
    ),
    (
        "app/api/routes/strategies.py",
        "stop_strategy_by_name",
        "stop_strategy",
    ),
}
EXPECTED_BEST_EFFORT_STRATEGY_EVENTS = {
    "strategy.entry_candidate",
    "strategy.exit_candidate",
}
EXPECTED_POLLING_EVENT_TYPES = {
    "health.polling_fallback_started",
    "health.polling_fallback_stopped",
    "health.stream_recovered",
    "health.stream_stale",
}
EXPECTED_DIRECT_RECORD_EVENT_CALLERS = {
    (
        "app/services/market_data_service.py",
        "MarketDataService._record_polling_health_event",
    ),
    ("app/services/strategy_service.py", "StrategyService._record_domain_event"),
}


def _flatten(expr: ast.AST) -> str | None:
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        prefix = _flatten(expr.value)
        return f"{prefix}.{expr.attr}" if prefix else expr.attr
    if isinstance(expr, ast.Call):
        return _flatten(expr.func)
    return None


def _literal_string(expr: ast.AST) -> str | None:
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return expr.value
    return None


class _FunctionCallCollector(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.class_stack: list[str] = []
        self.function_stack: list[str] = []
        self.calls: list[tuple[str, str]] = []
        self.calls_by_function: dict[str, set[str]] = {}
        self.event_types_by_call: dict[tuple[str, str], set[str]] = {}

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        if not self.function_stack:
            self.generic_visit(node)
            return
        function_name = ".".join([*self.class_stack, self.function_stack[-1]])
        call_name = _flatten(node.func)
        if call_name is not None:
            self.calls.append((function_name, call_name))
            self.calls_by_function.setdefault(function_name, set()).add(call_name)
            event_type = self._event_type_keyword(node)
            if event_type is not None:
                self.event_types_by_call.setdefault(
                    (function_name, call_name), set()
                ).add(event_type)
        self.generic_visit(node)

    @staticmethod
    def _event_type_keyword(node: ast.Call) -> str | None:
        for keyword in node.keywords:
            if keyword.arg == "event_type":
                return _literal_string(keyword.value)
        return None


def _collect_calls() -> dict[str, _FunctionCallCollector]:
    collectors: dict[str, _FunctionCallCollector] = {}
    for path in APP_ROOT.rglob("*.py"):
        relative_path = path.relative_to(APP_ROOT.parent).as_posix()
        tree = ast.parse(path.read_text())
        collector = _FunctionCallCollector(path)
        collector.visit(tree)
        collectors[relative_path] = collector
    return collectors


def _discover_audit_write_paths() -> set[tuple[str, str, str, str]]:
    inventory: set[tuple[str, str, str, str]] = set()
    collectors = _collect_calls()
    for relative_path, collector in collectors.items():
        if relative_path in IGNORED_HELPER_FILES:
            continue
        for function_name, call_name in collector.calls:
            if call_name not in WRITE_CALLS:
                continue
            if call_name in {
                "persist_required_domain_event",
                "record_required_domain_event",
            }:
                classification = "REQUIRED_DURABLE"
            elif call_name == "domain_event_service.record_event_in_session":
                classification = "SESSION_BOUND_DURABLE"
            else:
                classification = "BEST_EFFORT_INFORMATIONAL"
            inventory.add((classification, relative_path, function_name, call_name))
    return inventory


def _route_broker_action_functions() -> dict[tuple[str, str, str], set[str]]:
    routes: dict[tuple[str, str, str], set[str]] = {}
    collectors = _collect_calls()
    for relative_path in {
        "app/api/routes/control_plane.py",
        "app/api/routes/strategies.py",
    }:
        collector = collectors[relative_path]
        for function_name, call_name in collector.calls:
            broker_action_name: str | None = None
            if call_name.endswith(".start_strategy"):
                broker_action_name = "start_strategy"
            elif call_name.endswith(".stop_strategy"):
                broker_action_name = "stop_strategy"
            elif "reconcile" in call_name:
                broker_action_name = "reconcile"
            if broker_action_name is None:
                continue
            key = (relative_path, function_name, broker_action_name)
            routes[key] = collector.calls_by_function.get(function_name, set())
    return routes


def test_audit_closure_inventory_matches_current_write_paths():
    assert _discover_audit_write_paths() == EXPECTED_AUDIT_WRITE_PATHS


def test_audit_test_002_only_allowlisted_best_effort_record_event_callers_remain():
    callers = {
        (relative_path, function_name)
        for _, relative_path, function_name, call_name in _discover_audit_write_paths()
        if call_name
        in {"domain_event_service.record_event", "self.event_service.record_event"}
    }
    assert callers == EXPECTED_DIRECT_RECORD_EVENT_CALLERS


def test_audit_test_002_best_effort_strategy_events_stay_candidate_only():
    best_effort_calls = set()
    tree = ast.parse((APP_ROOT / "services/strategy_service.py").read_text())
    for node in ast.walk(tree):
        if (
            not isinstance(node, ast.Call)
            or _flatten(node.func) != "self._record_domain_event"
        ):
            continue
        audit_persistence = None
        event_type = None
        for keyword in node.keywords:
            if keyword.arg == "audit_persistence":
                audit_persistence = _flatten(keyword.value)
            elif keyword.arg == "event_type":
                event_type = _literal_string(keyword.value)
        if (
            audit_persistence == "AUDIT_PERSISTENCE_BEST_EFFORT"
            and event_type is not None
        ):
            best_effort_calls.add(event_type)
    assert best_effort_calls == EXPECTED_BEST_EFFORT_STRATEGY_EVENTS


def test_audit_obs_001_polling_health_event_types_stay_allowlisted():
    event_types = set()
    tree = ast.parse((APP_ROOT / "services/market_data_service.py").read_text())
    for node in ast.walk(tree):
        if (
            not isinstance(node, ast.Call)
            or _flatten(node.func) != "self._record_polling_health_event"
        ):
            continue
        for keyword in node.keywords:
            if keyword.arg == "event_type":
                event_type = _literal_string(keyword.value)
                if event_type is not None:
                    event_types.add(event_type)
    assert event_types == EXPECTED_POLLING_EVENT_TYPES


def test_audit_api_008_broker_action_routes_keep_authority_and_audit_pattern():
    discovered = _route_broker_action_functions()
    assert set(discovered) == EXPECTED_BROKER_ACTION_ROUTE_OWNERS
    for calls in discovered.values():
        assert "build_operator_audit_context" in calls
        assert "persist_required_domain_event" in calls
