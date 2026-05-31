from __future__ import annotations

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

TARGETED_INDEX_ASSERTION_NAMES = {
    "ix_allocationalert_updated_at_desc",
    "ix_allocationalert_state_updated_at",
    "ix_allocationalert_severity_updated_at",
    "ix_allocationcycle_received_at_desc",
    "ix_domain_events_category_created_at",
    "ix_domain_events_correlation_created_at",
    "ix_domain_events_created_at_desc",
    "ix_domain_events_error_type_created_at",
    "ix_domain_events_instrument_created_at",
    "ix_domain_events_severity_created_at",
    "ix_domain_events_strategy_created_at",
    "ix_observabilitystate_key_updated_desc",
    "ix_observabilitystate_scope_updated_desc",
    "ix_observabilitystate_worker_updated_desc",
    "ix_promotion_request_status_requested_at",
    "ix_runtimelease_owner_expires",
    "ix_strategy_deployment_state_strategy",
    "ix_watchlist_entry_tier_status_priority",
    "uq_trade_intent_active_instrument",
}


def filtered_metadata_diffs(connection, metadata):
    context = MigrationContext.configure(
        connection,
        opts={
            "compare_type": True,
            "compare_server_default": False,
            "target_metadata": metadata,
            "render_as_batch": connection.dialect.name == "sqlite",
        },
    )
    diffs = compare_metadata(context, metadata)
    filtered_diffs = []
    for diff in diffs:
        kind = diff[0]
        if kind not in {"add_index", "remove_index"}:
            filtered_diffs.append(diff)
            continue
        index_name = diff[1].name
        if index_name not in TARGETED_INDEX_ASSERTION_NAMES:
            filtered_diffs.append(diff)
    return filtered_diffs
