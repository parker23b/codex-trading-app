from __future__ import annotations

from dataclasses import replace

from app.api.route_inventory import (
    ActiveReadVariant,
    RegisteredRoute,
    ResponseContractMode,
    ROUTE_MANIFEST,
    discover_registered_routes,
    render_backend_api_routes_markdown,
    validate_route_inventory,
)


def _replace_manifest_entry(path: str, method: str, **changes):
    updated = []
    for entry in ROUTE_MANIFEST:
        if entry.path == path and entry.method == method:
            updated.append(replace(entry, **changes))
        else:
            updated.append(entry)
    return tuple(updated)


def test_route_inventory_guard_matches_current_router():
    assert validate_route_inventory() == []


def test_route_inventory_guard_renders_current_docs():
    rendered = render_backend_api_routes_markdown()
    assert rendered == open("docs/backend-api-routes.md", encoding="utf-8").read()


def test_route_inventory_guard_detects_undocumented_route_registration():
    discovered_enabled = discover_registered_routes(testing_routes_enabled=True)
    discovered_disabled = discover_registered_routes(testing_routes_enabled=False)
    fake_route = RegisteredRoute(
        method="GET",
        path="/undocumented",
        handler="app.api.routes.fake.fake_route",
        response_model=dict[str, str],
    )
    discovered_enabled = {**discovered_enabled, fake_route.key: fake_route}

    errors = validate_route_inventory(
        discovered_enabled=discovered_enabled,
        discovered_disabled=discovered_disabled,
    )

    assert any("Undocumented registered routes" in error for error in errors)


def test_route_inventory_guard_detects_missing_classification():
    manifest = _replace_manifest_entry("/dashboard", "GET", classification=None)

    errors = validate_route_inventory(manifest=manifest)

    assert any("Missing classification" in error for error in errors)


def test_route_inventory_guard_detects_frontend_consumed_raw_response_without_exception():
    manifest = _replace_manifest_entry(
        "/health",
        "GET",
        frontend_consumers=("getHealth",),
        response_contract_mode=ResponseContractMode.EXPLICIT_MODEL,
        reviewed_raw_exception_rationale=None,
    )

    errors = validate_route_inventory(manifest=manifest)

    assert any(
        "Frontend-consumed route GET /health has a raw response" in error
        for error in errors
    )


def test_route_inventory_guard_detects_active_read_auth_bypass():
    manifest = _replace_manifest_entry(
        "/dashboard",
        "GET",
        active_read_variants=(
            ActiveReadVariant(
                query_params=(("refresh", "true"),),
                notes="Synthetic auth-bypass regression fixture.",
            ),
        ),
    )

    errors = validate_route_inventory(manifest=manifest)

    assert any(
        "GET /dashboard?refresh=true is an active-read variant" in error
        for error in errors
    )


def test_route_inventory_guard_detects_invalid_test_only_registration():
    discovered_enabled = discover_registered_routes(testing_routes_enabled=True)

    errors = validate_route_inventory(
        discovered_enabled=discovered_enabled,
        discovered_disabled=discovered_enabled,
    )

    assert any(
        "Test-only routes registered when testing is disabled" in error
        for error in errors
    )
