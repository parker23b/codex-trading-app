from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
import types
import typing
from typing import Any, get_args, get_origin

from fastapi.routing import APIRoute
from pydantic import BaseModel

from app.api.auth import requires_operator_auth
from app.api.router import build_api_router
from app.core.broker_environment import IG_DEMO_BASE_URL
from app.core.config import Settings


class RouteClassification(StrEnum):
    PASSIVE_READ = "PASSIVE_READ"
    ACTIVE_READ_REFRESH = "ACTIVE_READ_REFRESH"
    BROKER_READ = "BROKER_READ"
    MUTATION = "MUTATION"
    TEST_ONLY_MUTATION = "TEST_ONLY_MUTATION"


class RouteSurface(StrEnum):
    OPERATOR = "operator"
    INTERNAL_DIAGNOSTIC = "internal/diagnostic"
    TEST_ONLY = "test-only"


class ResponseContractMode(StrEnum):
    EXPLICIT_MODEL = "explicit_model"
    REVIEWED_RAW_EXCEPTION = "reviewed_raw_exception"


@dataclass(frozen=True)
class ActiveReadVariant:
    query_params: tuple[tuple[str, str], ...]
    notes: str

    def query_params_mapping(self) -> dict[str, str]:
        return dict(self.query_params)

    def query_string(self) -> str:
        return "&".join(f"{name}={value}" for name, value in self.query_params)


@dataclass(frozen=True)
class RouteManifestEntry:
    method: str
    path: str
    handler: str
    classification: RouteClassification | None
    surface: RouteSurface = RouteSurface.OPERATOR
    frontend_consumers: tuple[str, ...] = ()
    response_contract_mode: ResponseContractMode = ResponseContractMode.EXPLICIT_MODEL
    reviewed_raw_exception_rationale: str | None = None
    notes: str = ""
    active_read_variants: tuple[ActiveReadVariant, ...] = ()
    testing_route: bool = False

    @property
    def key(self) -> tuple[str, str]:
        return (self.method, self.path)

    @property
    def frontend_consumed(self) -> bool:
        return bool(self.frontend_consumers)


@dataclass(frozen=True)
class RegisteredRoute:
    method: str
    path: str
    handler: str
    response_model: Any

    @property
    def key(self) -> tuple[str, str]:
        return (self.method, self.path)


def _entry(
    method: str,
    path: str,
    handler: str,
    classification: RouteClassification,
    *,
    surface: RouteSurface = RouteSurface.OPERATOR,
    frontend_consumers: tuple[str, ...] = (),
    response_contract_mode: ResponseContractMode = (
        ResponseContractMode.EXPLICIT_MODEL
    ),
    reviewed_raw_exception_rationale: str | None = None,
    notes: str = "",
    active_read_variants: tuple[ActiveReadVariant, ...] = (),
    testing_route: bool = False,
) -> RouteManifestEntry:
    return RouteManifestEntry(
        method=method,
        path=path,
        handler=handler,
        classification=classification,
        surface=surface,
        frontend_consumers=frontend_consumers,
        response_contract_mode=response_contract_mode,
        reviewed_raw_exception_rationale=reviewed_raw_exception_rationale,
        notes=notes,
        active_read_variants=active_read_variants,
        testing_route=testing_route,
    )


ROUTE_MANIFEST: tuple[RouteManifestEntry, ...] = (
    _entry(
        "GET",
        "/health",
        "app.api.routes.health.health_check",
        RouteClassification.PASSIVE_READ,
        surface=RouteSurface.INTERNAL_DIAGNOSTIC,
        response_contract_mode=ResponseContractMode.REVIEWED_RAW_EXCEPTION,
        reviewed_raw_exception_rationale=(
            "Static service heartbeat used for local diagnostics only; not a current "
            "frontend-consumed operator contract."
        ),
        notes="Static health response.",
    ),
    _entry(
        "GET",
        "/health/stream",
        "app.api.routes.health.stream_health_check",
        RouteClassification.PASSIVE_READ,
        surface=RouteSurface.INTERNAL_DIAGNOSTIC,
        frontend_consumers=("getStreamHealth",),
        notes="Streaming health projection.",
    ),
    _entry(
        "GET",
        "/system/health",
        "app.api.routes.health.system_health_check",
        RouteClassification.PASSIVE_READ,
        surface=RouteSurface.INTERNAL_DIAGNOSTIC,
        notes="Aggregated health projection.",
    ),
    _entry(
        "GET",
        "/system/telemetry",
        "app.api.routes.health.operational_telemetry",
        RouteClassification.PASSIVE_READ,
        surface=RouteSurface.INTERNAL_DIAGNOSTIC,
        frontend_consumers=("getOperationalTelemetry", "getBrokerAuthStatus"),
        notes="Aggregated telemetry projection.",
    ),
    _entry(
        "GET",
        "/system/broker-environment",
        "app.api.routes.health.broker_environment_status",
        RouteClassification.PASSIVE_READ,
        surface=RouteSurface.INTERNAL_DIAGNOSTIC,
        frontend_consumers=("getBrokerEnvironmentStatus",),
        notes="Backend-owned broker environment and dealing status projection.",
    ),
    _entry(
        "GET",
        "/system/limits",
        "app.api.routes.system.get_system_operating_limits",
        RouteClassification.PASSIVE_READ,
        frontend_consumers=("getSystemOperatingLimits",),
        notes="Settings and operating-limits projection.",
    ),
    _entry(
        "GET",
        "/broker/positions",
        "app.api.routes.broker.list_broker_positions",
        RouteClassification.BROKER_READ,
        notes="Broker position read path.",
    ),
    _entry(
        "GET",
        "/control-plane/summary",
        "app.api.routes.control_plane.get_control_plane_summary",
        RouteClassification.PASSIVE_READ,
        frontend_consumers=("getControlPlaneSummary",),
        notes="Control-plane summary projection.",
    ),
    _entry(
        "GET",
        "/control-plane/operator-state",
        "app.api.routes.control_plane.get_operator_control_state",
        RouteClassification.PASSIVE_READ,
        frontend_consumers=("getOperatorControlState",),
        notes="Operator override read.",
    ),
    _entry(
        "PUT",
        "/control-plane/operator-state",
        "app.api.routes.control_plane.update_operator_control_state",
        RouteClassification.MUTATION,
        frontend_consumers=("updateOperatorControlState",),
        notes="Operator override mutation.",
    ),
    _entry(
        "GET",
        "/control-plane/strategies/{strategy_name}",
        "app.api.routes.control_plane.get_control_plane_strategy_detail",
        RouteClassification.PASSIVE_READ,
        frontend_consumers=("getControlPlaneFamily",),
        notes="Control-plane family detail projection.",
    ),
    _entry(
        "POST",
        "/control-plane/reconcile",
        "app.api.routes.control_plane.reconcile_control_plane",
        RouteClassification.MUTATION,
        notes="Deployment/runtime reconciliation mutation.",
    ),
    _entry(
        "PUT",
        "/control-plane/governance/{strategy_name}",
        "app.api.routes.control_plane.update_strategy_governance",
        RouteClassification.MUTATION,
        frontend_consumers=("updateStrategyGovernance",),
        notes="Governance mutation.",
    ),
    _entry(
        "GET",
        "/coverage/summary",
        "app.api.routes.coverage.get_coverage_summary",
        RouteClassification.PASSIVE_READ,
        frontend_consumers=("getCoverageSummary",),
        notes="Coverage projection using passive watchlist snapshots.",
    ),
    _entry(
        "GET",
        "/dashboard",
        "app.api.routes.dashboard.get_dashboard",
        RouteClassification.PASSIVE_READ,
        frontend_consumers=("getDashboardSnapshot",),
        notes="Persisted dashboard snapshot without broker account read.",
    ),
    _entry(
        "GET",
        "/events",
        "app.api.routes.events.list_events",
        RouteClassification.PASSIVE_READ,
        frontend_consumers=("getDomainEvents",),
        notes="Domain-event history projection.",
    ),
    _entry(
        "GET",
        "/events/{event_id}",
        "app.api.routes.events.get_event",
        RouteClassification.PASSIVE_READ,
        notes="Single domain-event read.",
    ),
    _entry(
        "GET",
        "/allocation/cycles",
        "app.api.routes.allocation.list_allocation_cycles",
        RouteClassification.PASSIVE_READ,
        frontend_consumers=("getAllocationCycles",),
        notes="Allocation-cycle read.",
    ),
    _entry(
        "GET",
        "/allocation/cycles/{cycle_id}",
        "app.api.routes.allocation.get_allocation_cycle",
        RouteClassification.PASSIVE_READ,
        frontend_consumers=("getAllocationCycle",),
        notes="Allocation-cycle detail read.",
    ),
    _entry(
        "GET",
        "/allocation/intents",
        "app.api.routes.allocation.list_allocation_intents",
        RouteClassification.PASSIVE_READ,
        frontend_consumers=("getAllocationIntents",),
        notes="Allocation-intent read.",
    ),
    _entry(
        "GET",
        "/allocation/intents/{trade_intent_id}",
        "app.api.routes.allocation.get_allocation_intent",
        RouteClassification.PASSIVE_READ,
        frontend_consumers=("getAllocationIntent",),
        notes="Allocation-intent detail read.",
    ),
    _entry(
        "GET",
        "/allocation/drift",
        "app.api.routes.allocation.get_allocation_drift_summary",
        RouteClassification.PASSIVE_READ,
        frontend_consumers=("getAllocationDriftSummary",),
        notes="Computed allocation-drift projection.",
    ),
    _entry(
        "GET",
        "/allocation/alerts",
        "app.api.routes.allocation.list_allocation_alerts",
        RouteClassification.PASSIVE_READ,
        frontend_consumers=("getAllocationAlerts",),
        active_read_variants=(
            ActiveReadVariant(
                query_params=(("refresh", "true"),),
                notes="Explicit alert refresh persists recalculated alerts.",
            ),
        ),
        notes="Default alert reads are passive when refresh=false.",
    ),
    _entry(
        "POST",
        "/allocation/alerts/{alert_id}/acknowledge",
        "app.api.routes.allocation.acknowledge_allocation_alert",
        RouteClassification.MUTATION,
        frontend_consumers=("acknowledgeAllocationAlert",),
        notes="Acknowledges an allocation alert.",
    ),
    _entry(
        "POST",
        "/allocation/alerts/{alert_id}/resolve",
        "app.api.routes.allocation.resolve_allocation_alert",
        RouteClassification.MUTATION,
        frontend_consumers=("resolveAllocationAlert",),
        notes="Resolves an allocation alert.",
    ),
    _entry(
        "GET",
        "/allocation/alerts/unresolved-critical",
        "app.api.routes.allocation.list_unresolved_critical_allocation_alerts",
        RouteClassification.PASSIVE_READ,
        frontend_consumers=("getUnresolvedCriticalAllocationAlerts",),
        notes="Reads persisted unresolved critical alerts without refresh.",
    ),
    _entry(
        "GET",
        "/allocation/exposure",
        "app.api.routes.allocation.get_allocation_exposure_summary",
        RouteClassification.PASSIVE_READ,
        frontend_consumers=("getAllocationExposureSummary",),
        notes="Computed allocation-exposure projection.",
    ),
    _entry(
        "GET",
        "/market-status/{instrument}",
        "app.api.routes.market_status.get_market_status",
        RouteClassification.BROKER_READ,
        notes="Broker/market status read.",
    ),
    _entry(
        "GET",
        "/markets/overview",
        "app.api.routes.markets.get_market_overview",
        RouteClassification.BROKER_READ,
        frontend_consumers=("getMarketOverview",),
        notes="Broker-backed markets overview.",
    ),
    _entry(
        "GET",
        "/markets/catalogue",
        "app.api.routes.markets.get_market_catalogue",
        RouteClassification.PASSIVE_READ,
        frontend_consumers=("getMarketCatalogue",),
        notes="Markets catalogue projection.",
    ),
    _entry(
        "GET",
        "/watchlist/shortlist",
        "app.api.routes.markets.get_shortlist",
        RouteClassification.PASSIVE_READ,
        notes="Shortlist projection.",
    ),
    _entry(
        "POST",
        "/watchlist/shortlist/{instrument_id}",
        "app.api.routes.markets.add_shortlist_item",
        RouteClassification.MUTATION,
        frontend_consumers=("addShortlistInstrument",),
        notes="Shortlist add mutation.",
    ),
    _entry(
        "DELETE",
        "/watchlist/shortlist/{instrument_id}",
        "app.api.routes.markets.remove_shortlist_item",
        RouteClassification.MUTATION,
        frontend_consumers=("removeShortlistInstrument",),
        notes="Shortlist remove mutation.",
    ),
    _entry(
        "POST",
        "/strategy-watchlist/bulk",
        "app.api.routes.markets.add_strategy_watchlist_items",
        RouteClassification.MUTATION,
        frontend_consumers=("addStrategyWatchlistInstruments",),
        notes="Bulk strategy-watchlist mutation.",
    ),
    _entry(
        "GET",
        "/strategy-watchlist",
        "app.api.routes.markets.get_strategy_watchlist",
        RouteClassification.PASSIVE_READ,
        frontend_consumers=("getStrategyWatchlist",),
        notes="Strategy-watchlist projection with sync=false.",
    ),
    _entry(
        "DELETE",
        "/strategy-watchlist/{instrument_id}",
        "app.api.routes.markets.remove_strategy_watchlist_item",
        RouteClassification.MUTATION,
        frontend_consumers=("removeStrategyWatchlistInstrument",),
        notes="Strategy-watchlist remove mutation.",
    ),
    _entry(
        "GET",
        "/market-data/feed-state",
        "app.api.routes.markets.get_feed_state",
        RouteClassification.BROKER_READ,
        frontend_consumers=("getFeedState",),
        notes="Feed-state snapshot with broker-backed readiness metadata.",
    ),
    _entry(
        "GET",
        "/market-data/feed-state/{instrument_id}",
        "app.api.routes.markets.get_instrument_feed_state",
        RouteClassification.BROKER_READ,
        frontend_consumers=("getInstrumentFeedState",),
        notes="Per-instrument feed-state snapshot.",
    ),
    _entry(
        "GET",
        "/live/instruments/{instrument_id}/chart",
        "app.api.routes.markets.get_live_instrument_chart",
        RouteClassification.BROKER_READ,
        frontend_consumers=("getLiveInstrumentChart",),
        notes="Live chart projection with broker candle reads.",
    ),
    _entry(
        "GET",
        "/charts/equity",
        "app.api.routes.charts.get_equity_chart",
        RouteClassification.PASSIVE_READ,
        response_contract_mode=ResponseContractMode.REVIEWED_RAW_EXCEPTION,
        reviewed_raw_exception_rationale=(
            "Persisted chart projection not currently consumed by frontend/lib/api.ts; "
            "keep raw until an operator surface depends on it."
        ),
        notes="Persisted equity chart projection.",
    ),
    _entry(
        "GET",
        "/charts/drawdown",
        "app.api.routes.charts.get_drawdown_chart",
        RouteClassification.PASSIVE_READ,
        response_contract_mode=ResponseContractMode.REVIEWED_RAW_EXCEPTION,
        reviewed_raw_exception_rationale=(
            "Persisted chart projection not currently consumed by frontend/lib/api.ts; "
            "keep raw until an operator surface depends on it."
        ),
        notes="Persisted drawdown chart projection.",
    ),
    _entry(
        "GET",
        "/charts/risk-allocation",
        "app.api.routes.charts.get_risk_allocation_chart",
        RouteClassification.PASSIVE_READ,
        frontend_consumers=("getRiskAllocationChart",),
        notes="Risk-allocation chart contract is backend-owned.",
    ),
    _entry(
        "GET",
        "/positions",
        "app.api.routes.positions.list_positions",
        RouteClassification.PASSIVE_READ,
        notes="Compatibility open-position read.",
    ),
    _entry(
        "GET",
        "/executions",
        "app.api.routes.executions.list_executions",
        RouteClassification.PASSIVE_READ,
        frontend_consumers=("getExecutions",),
        notes="Execution-history read.",
    ),
    _entry(
        "GET",
        "/trades",
        "app.api.routes.trades.list_trades",
        RouteClassification.PASSIVE_READ,
        frontend_consumers=("getTrades",),
        notes="Trade-history read.",
    ),
    _entry(
        "GET",
        "/trades/positions",
        "app.api.routes.trades.list_positions_compat",
        RouteClassification.PASSIVE_READ,
        frontend_consumers=("getOpenPositions",),
        notes="Frontend-consumed compatibility positions read.",
    ),
    _entry(
        "GET",
        "/strategies",
        "app.api.routes.strategies.list_strategies",
        RouteClassification.PASSIVE_READ,
        frontend_consumers=("getStrategies",),
        notes="Strategy-summary projection.",
    ),
    _entry(
        "POST",
        "/strategy/start",
        "app.api.routes.strategies.start_strategy",
        RouteClassification.MUTATION,
        frontend_consumers=("startStrategy",),
        notes="Strategy start mutation.",
    ),
    _entry(
        "POST",
        "/strategy/stop",
        "app.api.routes.strategies.stop_strategy",
        RouteClassification.MUTATION,
        frontend_consumers=("stopStrategy",),
        notes="Strategy stop mutation.",
    ),
    _entry(
        "POST",
        "/strategies/{name}/start",
        "app.api.routes.strategies.start_strategy_by_name",
        RouteClassification.MUTATION,
        notes="Compatibility strategy start mutation.",
    ),
    _entry(
        "POST",
        "/strategies/{name}/stop",
        "app.api.routes.strategies.stop_strategy_by_name",
        RouteClassification.MUTATION,
        notes="Compatibility strategy stop mutation.",
    ),
    _entry(
        "GET",
        "/aimee/snapshot",
        "app.api.routes.aimee.get_snapshot",
        RouteClassification.PASSIVE_READ,
        frontend_consumers=("getAimeeSnapshot",),
        notes="Passive AIMEE snapshot.",
    ),
    _entry(
        "GET",
        "/reviews/operator-summary",
        "app.api.routes.ai_reviewer.get_operator_summary",
        RouteClassification.PASSIVE_READ,
        frontend_consumers=("getOperatorSummaryReview",),
        active_read_variants=(
            ActiveReadVariant(
                query_params=(("persist", "true"),),
                notes="Explicit review archival persists a GeneratedReviewRecord.",
            ),
        ),
        notes="Default operator-summary review is a passive preview.",
    ),
    _entry(
        "GET",
        "/reviews/daily",
        "app.api.routes.ai_reviewer.get_daily_review",
        RouteClassification.PASSIVE_READ,
        active_read_variants=(
            ActiveReadVariant(
                query_params=(("persist", "true"),),
                notes="Explicit daily-review archival persists a GeneratedReviewRecord.",
            ),
        ),
        notes="Default daily review is a passive preview.",
    ),
    _entry(
        "GET",
        "/reviews/strategies/{strategy_name}",
        "app.api.routes.ai_reviewer.get_strategy_review",
        RouteClassification.PASSIVE_READ,
        active_read_variants=(
            ActiveReadVariant(
                query_params=(("persist", "true"),),
                notes=(
                    "Explicit strategy-review archival persists a "
                    "GeneratedReviewRecord."
                ),
            ),
        ),
        notes="Default strategy review is a passive preview.",
    ),
    _entry(
        "GET",
        "/reviews/runtime-health",
        "app.api.routes.ai_reviewer.get_runtime_health_review",
        RouteClassification.PASSIVE_READ,
        active_read_variants=(
            ActiveReadVariant(
                query_params=(("persist", "true"),),
                notes=(
                    "Explicit runtime-health review archival persists a "
                    "GeneratedReviewRecord."
                ),
            ),
        ),
        notes="Default runtime-health review is a passive preview.",
    ),
    _entry(
        "GET",
        "/reviews/trades/{trade_id}/postmortem",
        "app.api.routes.ai_reviewer.get_trade_postmortem",
        RouteClassification.PASSIVE_READ,
        active_read_variants=(
            ActiveReadVariant(
                query_params=(("persist", "true"),),
                notes=(
                    "Explicit trade-postmortem archival persists a "
                    "GeneratedReviewRecord."
                ),
            ),
        ),
        notes="Default trade postmortem is a passive preview.",
    ),
    _entry(
        "POST",
        "/reviews/questions",
        "app.api.routes.ai_reviewer.answer_operational_question",
        RouteClassification.MUTATION,
        frontend_consumers=("askOperationalQuestion",),
        notes="Explicit advisory-question persistence route.",
    ),
    _entry(
        "GET",
        "/reviews/history",
        "app.api.routes.ai_reviewer.list_review_history",
        RouteClassification.PASSIVE_READ,
        frontend_consumers=("getReviewHistory",),
        notes="Persisted review-history read.",
    ),
    _entry(
        "GET",
        "/reviews/history/{review_id}",
        "app.api.routes.ai_reviewer.get_review_record",
        RouteClassification.PASSIVE_READ,
        notes="Persisted review-record read.",
    ),
    _entry(
        "POST",
        "/testing/reset-history",
        "app.api.routes.testing.reset_history",
        RouteClassification.TEST_ONLY_MUTATION,
        surface=RouteSurface.TEST_ONLY,
        frontend_consumers=("resetTestHistory",),
        notes="Conditional destructive test reset route.",
        testing_route=True,
    ),
)


def manifest_by_key(
    manifest: tuple[RouteManifestEntry, ...] = ROUTE_MANIFEST,
) -> dict[tuple[str, str], RouteManifestEntry]:
    return {entry.key: entry for entry in manifest}


def discover_registered_routes(
    *, testing_routes_enabled: bool, **settings_overrides: object
) -> dict[tuple[str, str], RegisteredRoute]:
    router = build_api_router(
        Settings(
            ig_api_base_url=IG_DEMO_BASE_URL,
            ig_trading_enabled=False,
            ig_live_trading_acknowledged=False,
            testing_routes_enabled=testing_routes_enabled,
            **settings_overrides,
        )
    )
    discovered: dict[tuple[str, str], RegisteredRoute] = {}
    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue
        methods = sorted(
            method
            for method in (route.methods or set())
            if method not in {"HEAD", "OPTIONS"}
        )
        for method in methods:
            registered = RegisteredRoute(
                method=method,
                path=route.path,
                handler=f"{route.endpoint.__module__}.{route.endpoint.__name__}",
                response_model=route.response_model,
            )
            discovered[registered.key] = registered
    return discovered


def _is_model_type(value: Any) -> bool:
    return isinstance(value, type) and issubclass(value, BaseModel)


def has_explicit_response_model(response_model: Any) -> bool:
    if response_model is None:
        return False
    if _is_model_type(response_model):
        return True

    origin = get_origin(response_model)
    if origin is None:
        return False
    if origin in {list, tuple, set, frozenset}:
        return all(
            has_explicit_response_model(argument)
            for argument in get_args(response_model)
        )
    if origin is dict:
        return False
    if origin in {types.UnionType, typing.Union}:
        return all(
            has_explicit_response_model(argument)
            for argument in get_args(response_model)
        )
    return False


def format_response_model(response_model: Any) -> str:
    if response_model is None:
        return "None"
    if _is_model_type(response_model):
        return response_model.__name__

    origin = get_origin(response_model)
    if origin is None:
        return getattr(response_model, "__name__", repr(response_model))

    args = get_args(response_model)
    if origin is list:
        return f"list[{format_response_model(args[0])}]"
    if origin is tuple:
        return f"tuple[{', '.join(format_response_model(arg) for arg in args)}]"
    if origin is dict:
        key_repr, value_repr = (format_response_model(arg) for arg in args)
        return f"dict[{key_repr}, {value_repr}]"
    if origin in {types.UnionType, typing.Union}:
        return " | ".join(format_response_model(arg) for arg in args)
    return repr(response_model)


def validate_route_inventory(
    *,
    manifest: tuple[RouteManifestEntry, ...] = ROUTE_MANIFEST,
    discovered_enabled: dict[tuple[str, str], RegisteredRoute] | None = None,
    discovered_disabled: dict[tuple[str, str], RegisteredRoute] | None = None,
) -> list[str]:
    enabled = discovered_enabled or discover_registered_routes(
        testing_routes_enabled=True
    )
    disabled = discovered_disabled or discover_registered_routes(
        testing_routes_enabled=False
    )
    manifest_map = manifest_by_key(manifest)
    errors: list[str] = []

    enabled_keys = set(enabled)
    disabled_keys = set(disabled)
    manifest_keys = set(manifest_map)

    undocumented = sorted(enabled_keys - manifest_keys)
    if undocumented:
        errors.append(
            "Undocumented registered routes: "
            + ", ".join(f"{method} {path}" for method, path in undocumented)
        )

    missing = sorted(manifest_keys - enabled_keys)
    if missing:
        errors.append(
            "Manifest routes not registered: "
            + ", ".join(f"{method} {path}" for method, path in missing)
        )

    testing_only_keys = {
        key for key, entry in manifest_map.items() if entry.testing_route
    }
    enabled_only = enabled_keys - disabled_keys
    if enabled_only != testing_only_keys:
        errors.append(
            "Testing-route gating mismatch: enabled-only routes are "
            + ", ".join(f"{method} {path}" for method, path in sorted(enabled_only))
            + "; expected "
            + ", ".join(
                f"{method} {path}" for method, path in sorted(testing_only_keys)
            )
        )

    leaked_test_routes = disabled_keys & testing_only_keys
    if leaked_test_routes:
        errors.append(
            "Test-only routes registered when testing is disabled: "
            + ", ".join(
                f"{method} {path}" for method, path in sorted(leaked_test_routes)
            )
        )

    for key in sorted(enabled_keys & manifest_keys):
        registered = enabled[key]
        entry = manifest_map[key]

        if entry.classification is None:
            errors.append(
                f"Missing classification for manifest entry {entry.method} {entry.path}."
            )
            continue

        if registered.handler != entry.handler:
            errors.append(
                f"Handler drift for {entry.method} {entry.path}: "
                f"registered {registered.handler}, manifest {entry.handler}."
            )

        explicit_model = has_explicit_response_model(registered.response_model)
        if (
            explicit_model
            and entry.response_contract_mode
            == ResponseContractMode.REVIEWED_RAW_EXCEPTION
        ):
            errors.append(
                f"Reviewed raw-response exception is stale for {entry.method} {entry.path}; "
                "the route now has an explicit response model."
            )
        if (
            not explicit_model
            and entry.response_contract_mode
            != ResponseContractMode.REVIEWED_RAW_EXCEPTION
        ):
            errors.append(
                f"Raw response route {entry.method} {entry.path} is missing a reviewed exception."
            )
        if (
            not explicit_model
            and entry.frontend_consumed
            and entry.response_contract_mode
            != ResponseContractMode.REVIEWED_RAW_EXCEPTION
        ):
            errors.append(
                f"Frontend-consumed route {entry.method} {entry.path} has a raw response "
                "without a reviewed exception."
            )
        if (
            entry.response_contract_mode == ResponseContractMode.REVIEWED_RAW_EXCEPTION
            and not entry.reviewed_raw_exception_rationale
        ):
            errors.append(
                f"Reviewed raw-response exception for {entry.method} {entry.path} "
                "is missing rationale."
            )

        auth_settings = Settings(
            ig_api_base_url=IG_DEMO_BASE_URL,
            ig_trading_enabled=False,
            ig_live_trading_acknowledged=False,
            testing_routes_enabled=entry.testing_route,
        )
        auth_required_for_base = requires_operator_auth(
            method=entry.method,
            path=entry.path,
            query_params={},
            settings=auth_settings,
        )
        if (
            entry.classification
            in {
                RouteClassification.MUTATION,
                RouteClassification.TEST_ONLY_MUTATION,
            }
            and not auth_required_for_base
        ):
            errors.append(
                f"{entry.method} {entry.path} is classified as {entry.classification} "
                "but does not require operator auth."
            )
        if (
            entry.classification
            in {
                RouteClassification.PASSIVE_READ,
                RouteClassification.BROKER_READ,
            }
            and not entry.active_read_variants
            and auth_required_for_base
        ):
            errors.append(
                f"{entry.method} {entry.path} unexpectedly requires operator auth "
                f"despite classification {entry.classification}."
            )

        for variant in entry.active_read_variants:
            if not requires_operator_auth(
                method=entry.method,
                path=entry.path,
                query_params=variant.query_params_mapping(),
                settings=auth_settings,
            ):
                errors.append(
                    f"{entry.method} {entry.path}?{variant.query_string()} is an active-read "
                    "variant but does not require operator auth."
                )

        if entry.testing_route:
            if entry.classification != RouteClassification.TEST_ONLY_MUTATION:
                errors.append(
                    f"Testing route {entry.method} {entry.path} must use "
                    "TEST_ONLY_MUTATION classification."
                )
            if entry.surface != RouteSurface.TEST_ONLY:
                errors.append(
                    f"Testing route {entry.method} {entry.path} must use test-only surface."
                )

    return errors


def _classification_label(entry: RouteManifestEntry) -> str:
    label = (
        entry.classification.value
        if entry.classification is not None
        else "UNCLASSIFIED"
    )
    if entry.active_read_variants:
        label += " with ACTIVE_READ_REFRESH variant(s)"
    return label


def _response_contract_label(
    entry: RouteManifestEntry, registered: RegisteredRoute
) -> str:
    if entry.response_contract_mode == ResponseContractMode.REVIEWED_RAW_EXCEPTION:
        return "Reviewed raw exception"
    return f"Explicit model: {format_response_model(registered.response_model)}"


def render_backend_api_routes_markdown(
    manifest: tuple[RouteManifestEntry, ...] = ROUTE_MANIFEST,
    *,
    discovered_enabled: dict[tuple[str, str], RegisteredRoute] | None = None,
    discovered_disabled: dict[tuple[str, str], RegisteredRoute] | None = None,
) -> str:
    enabled = discovered_enabled or discover_registered_routes(
        testing_routes_enabled=True
    )
    disabled = discovered_disabled or discover_registered_routes(
        testing_routes_enabled=False
    )
    manifest_map = manifest_by_key(manifest)
    always_on_count = len(disabled)
    conditional_count = len(enabled) - len(disabled)
    frontend_consumed_count = sum(1 for entry in manifest if entry.frontend_consumed)
    active_read_variant_count = sum(
        len(entry.active_read_variants) for entry in manifest
    )
    raw_exceptions = [
        entry
        for entry in manifest
        if entry.response_contract_mode == ResponseContractMode.REVIEWED_RAW_EXCEPTION
    ]
    classification_counts = Counter(
        entry.classification.value
        for entry in manifest
        if entry.classification is not None
    )

    lines = [
        "# Backend API route reference",
        "",
        "This document is rendered from the checked-in route manifest in "
        "`backend/app/api/route_inventory.py` by "
        "`python3 scripts/check_backend_route_inventory.py --write-docs`.",
        "",
        "## Current inventory",
        "",
        f"- Registered route count: `{len(enabled)}` total (`{always_on_count}` always-on, `{conditional_count}` conditional test-only).",
        f"- Frontend-consumed route families: `{frontend_consumed_count}`.",
        f"- Query-triggered active-read variants: `{active_read_variant_count}`.",
        f"- Reviewed raw-response exceptions: `{len(raw_exceptions)}`.",
        "",
        "## Classification counts",
        "",
    ]
    for classification in RouteClassification:
        lines.append(
            f"- `{classification.value}`: `{classification_counts.get(classification.value, 0)}`"
        )

    lines.extend(
        [
            "",
            "## Route reference",
            "",
            "| Method | Path | Handler | Classification | Scope | Frontend consumers | Response contract | Notes |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )

    for key in sorted(enabled):
        entry = manifest_map[key]
        registered = enabled[key]
        consumers = (
            ", ".join(f"`{name}`" for name in entry.frontend_consumers) or "None"
        )
        notes = entry.notes
        if entry.active_read_variants:
            variant_notes = "; ".join(
                f"`?{variant.query_string()}` -> {variant.notes}"
                for variant in entry.active_read_variants
            )
            notes = f"{notes} Active-read variants: {variant_notes}".strip()
        if entry.testing_route:
            notes = (
                f"{notes} Registered only when `TESTING_ROUTES_ENABLED=true`.".strip()
            )
        lines.append(
            "| "
            + " | ".join(
                (
                    entry.method,
                    f"`{entry.path}`",
                    f"`{registered.handler}`",
                    f"`{_classification_label(entry)}`",
                    f"`{entry.surface.value}`",
                    consumers,
                    _response_contract_label(entry, registered),
                    notes or "",
                )
            )
            + " |"
        )

    lines.extend(["", "## Reviewed raw-response exceptions", ""])
    for entry in raw_exceptions:
        lines.append(
            f"- `{entry.method} {entry.path}`: {entry.reviewed_raw_exception_rationale}"
        )

    lines.extend(["", "## Guardrails", ""])
    lines.extend(
        [
            "- Registered FastAPI routes are checked against the checked-in manifest.",
            "- A new route fails the check if it is undocumented, unclassified, or wired to a different handler than the manifest expects.",
            "- Mutation routes and query-triggered active-read routes fail the check if they bypass `requires_operator_auth()`.",
            "- Test-only routes fail the check if they register outside the explicit testing gate.",
            "- Raw responses are allowed only through a reviewed exception entry with rationale.",
            "- Frontend-consumed route families are expected to keep explicit backend response models; the reviewed raw-exception path is reserved for deliberate cases only.",
        ]
    )
    lines.append("")
    return "\n".join(lines)
