const TIMESTAMP = "2026-05-17T10:00:00.000Z";

function response(status, json, options = {}) {
  return { status, json, delayMs: options.delayMs ?? 0 };
}

function ok(json) {
  return response(200, json);
}

function unavailable(detail) {
  return response(503, { detail });
}

function delayed(route, delayMs) {
  return {
    ...route,
    delayMs,
  };
}

function safeIdentifier(display, fingerprint) {
  return {
    display,
    fingerprint,
  };
}

function baseTelemetry(overrides = {}) {
  return {
    status: "ok",
    last_heartbeat: TIMESTAMP,
    heartbeat_age_ms: 2000,
    last_price_update: TIMESTAMP,
    last_price_age_ms: 1200,
    last_reconciliation: TIMESTAMP,
    last_reconciliation_age_ms: 5400,
    last_audit_write_failure: null,
    last_audit_write_failure_age_ms: null,
    stream_connected: true,
    stream_last_tick_at: TIMESTAMP,
    stream_last_tick_age_ms: 1200,
    subscribed_instrument_count: 1,
    desired_instrument_count: 1,
    broker_connected: true,
    feed_source_state: "LIVE",
    feed_health_state: "HEALTHY",
    broker_connectivity_state: "CONNECTED",
    entry_eligible: true,
    exit_eligible: true,
    entry_block_reason: null,
    exit_block_reason: null,
    open_risk_management_state: "MANAGED",
    open_risk_management_reason: "Open risk is managed.",
    audit_write_degraded: false,
    polling_fallback_active: false,
    polling_fallback_active_instrument_count: 0,
    stale_stream_instrument_count: 0,
    stream_degraded: false,
    runtime_degraded: false,
    degradation_reasons: [],
    broker_latency_ms: 48,
    runtime_count: 1,
    active_runtime_count: 1,
    stale_runtime_count: 0,
    stale_price_runtime_count: 0,
    reconciliation_mismatches: 0,
    order_failures_last_5m: 0,
    rejected_orders_last_5m: 0,
    audit_write_failures_last_5m: 0,
    strategies_paused_by_health: 0,
    ...overrides,
  };
}

function baseStreamHealth(overrides = {}) {
  return {
    enabled: true,
    connected: true,
    dependency_ready: true,
    subscribed_instruments: ["CS.D.EURUSD.MINI.IP"],
    last_tick_at: TIMESTAMP,
    last_status: "Connected",
    last_error: null,
    ...overrides,
  };
}

function baseCoverageSummary(overrides = {}) {
  return {
    streaming: {
      active_instruments: [],
      execution_readiness: [],
      desired_instruments: [],
      pinned_instruments: [],
      capped_instruments: [],
      asset_class_usage: {},
    },
    tier2: {
      refresh_queue: [],
      active_candidates: [],
    },
    promotions: {
      pending_count: 0,
      accepted_count: 0,
      rejected_count: 0,
      expired_count: 0,
      recent_requests: [],
    },
    trade_allocator: {
      selected_count: 0,
      rejected_count: 0,
      reason_counts: {},
      recent_decisions: [],
    },
    ...overrides,
  };
}

function baseFamily(overrides = {}) {
  return {
    strategy_name: "Breakout",
    display_name: "Breakout",
    description: "Momentum breakout strategy",
    governance: {
      approval_state: "APPROVED",
      autonomous_operation_allowed: true,
      emergency_stop: false,
      approved_asset_classes: ["FOREX"],
      approved_instruments: ["CS.D.EURUSD.MINI.IP"],
      approved_profile_names: ["default"],
      supported_asset_classes: ["FOREX"],
      available_profile_names: ["default"],
      updated_at: TIMESTAMP,
    },
    deployment: {
      state: "AUTO_DEPLOYED",
      selected_profile: "default",
      selected_profile_parameters: {},
      selected_instrument: "CS.D.EURUSD.MINI.IP",
      selected_asset_class: "FOREX",
      suitability_score: 1,
      suitability_reason: "eligible",
      profile_selected_at: TIMESTAMP,
      profile_change_reason: null,
      last_restart_reason: null,
      blocked_reason: null,
      degraded_reason: null,
      last_evaluated_at: TIMESTAMP,
      last_deployed_at: TIMESTAMP,
      updated_at: TIMESTAMP,
      open_risk_management_state: "MANAGED",
      open_risk_management_reason: "Open risk is managed.",
    },
    runtime: {
      is_running: true,
      active_runtime_id: "runtime-1",
      active_instrument: "CS.D.EURUSD.MINI.IP",
      active_profile_name: "default",
      active_parameters: {},
      control_mode: "AUTO",
      runtime_mode: "NORMAL",
      recovery_state: null,
      updated_at: TIMESTAMP,
      persisted_runtimes: [],
    },
    alignment: {
      is_aligned: true,
      status: "ALIGNED",
      reason: "Runtime matches deployment.",
      checks: [],
    },
    recent_events: [],
    ...overrides,
  };
}

function baseControlPlaneSummary(overrides = {}) {
  return {
    autonomous_control_enabled: true,
    configured_autonomous_control_enabled: true,
    effective_autonomous_control_enabled: true,
    autonomy_override_active: false,
    autonomy_override_value: null,
    autonomy_override_reason: null,
    autonomy_updated_at: TIMESTAMP,
    feed_source_state: "LIVE",
    feed_health_state: "HEALTHY",
    broker_connectivity_state: "CONNECTED",
    entry_eligible: true,
    exit_eligible: true,
    entry_block_reason: null,
    exit_block_reason: null,
    open_risk_management_state: "MANAGED",
    open_risk_management_reason: "Global open-risk state is managed.",
    counts: {
      AUTO_DEPLOYED: 1,
    },
    misaligned_count: 0,
    families: [baseFamily()],
    ...overrides,
  };
}

function baseSystemLimits(overrides = {}) {
  return {
    autonomous_control_enabled: true,
    risk: {
      max_open_positions: 8,
      max_positions_per_strategy: 2,
      max_open_risk_percent: 5,
      daily_loss_limit: 750,
      max_position_notional: 100000,
      max_unhealthy_runtimes: 1,
      global_entry_kill_switch: false,
    },
    execution: {
      max_price_age_ms: 15000,
      max_spread_pips: 3,
      max_spread_percent_of_price: 0.003,
      entry_burst_limit: 3,
      entry_burst_window_seconds: 60,
      failed_entry_retry_cooldown_seconds: 60,
      duplicate_signal_window_seconds: 60,
      cooldown_after_loss_seconds: 60,
      cooldown_after_exit_seconds: 60,
      allocator_enabled: true,
      allocator_max_decisions_per_cycle: 10,
      allocator_max_open_positions_per_instrument: 1,
      allocator_signal_stale_after_seconds: 60,
    },
    coverage: {
      streaming_enabled: true,
      max_instruments: 8,
      requested_frequency: "1s",
      max_promotions_per_minute: 4,
      max_subscription_churn_per_minute: 4,
      promotion_score_threshold: 0.7,
      eviction_score_threshold: 0.3,
      min_tier1_residency_seconds: 60,
      demotion_cooldown_seconds: 60,
      tier2_refresh_enabled: true,
      tier2_refresh_interval_seconds: 15,
      tier2_refresh_batch_size: 4,
      tier2_refresh_stale_after_seconds: 45,
      tier2_promotion_score_threshold: 0.8,
      tier2_promotion_ttl_seconds: 60,
      asset_class_slot_budgets: {},
      seed_instruments: [],
      tier2_seed_instruments: [],
    },
    screening: [],
    ...overrides,
  };
}

function baseDashboardSnapshot(overrides = {}) {
  return {
    accountValue: 10000,
    accountValuePercent: 0.4,
    dailyPnl: 120,
    dailyPnlPercent: 1.2,
    openRisk: 1.3,
    winRate: 0.58,
    riskReward: 1.7,
    brokerInfo: null,
    runningStrategies: [
      {
        name: "Breakout",
        instrument: "CS.D.EURUSD.MINI.IP",
        mode: "AUTO",
        status: "RUNNING",
      },
    ],
    ...overrides,
  };
}

function baseExposure(overrides = {}) {
  return {
    totals: {
      reserved_risk_percent: 0.6,
      live_risk_percent: 1.2,
      provisional_live_risk_percent: 0,
      reserved_risk_amount: 60,
      live_risk_amount: 120,
      provisional_live_risk_amount: 0,
      reserved_intent_count: 1,
      open_position_count: 1,
      remaining_portfolio_risk_percent: 3.2,
    },
    by_strategy: [
      {
        bucket_type: "strategy",
        name: "Breakout",
        total_risk_percent: 1.2,
        utilization_percent: 24,
        remaining_risk_percent: 3.8,
      },
    ],
    by_family: [
      {
        bucket_type: "family",
        name: "Breakout",
        total_risk_percent: 1.2,
        utilization_percent: 24,
        remaining_risk_percent: 3.8,
      },
    ],
    by_instrument: [
      {
        bucket_type: "instrument",
        name: "CS.D.EURUSD.MINI.IP",
        total_risk_percent: 1.2,
        utilization_percent: 24,
        remaining_risk_percent: 3.8,
      },
    ],
    by_currency: [],
    currency_directional: [],
    hotspots: [
      {
        bucket_type: "family",
        name: "Breakout",
        utilization_percent: 24,
        net_bias: null,
      },
    ],
    notes: {},
    ...overrides,
  };
}

function baseDrift(overrides = {}) {
  return {
    window_minutes: 720,
    drift_warning_percent: 10,
    drift_critical_percent: 20,
    material_drift_count: 0,
    worst_intents: [],
    by_strategy: [],
    by_family: [],
    by_instrument: [],
    ...overrides,
  };
}

function baseAlert(overrides = {}) {
  return {
    id: 5,
    alert_key: "risk-drift-5",
    alert_type: "material_execution_drift",
    severity: "error",
    state: "OPEN",
    escalation_level: "critical",
    title: "Material execution drift",
    message: "Submitted risk moved materially from approved allocation.",
    count: 1,
    recurrence_count: 1,
    first_seen_at: TIMESTAMP,
    last_seen_at: TIMESTAMP,
    acknowledged_at: null,
    resolved_at: null,
    related_intent_ids: [7],
    related_cycle_ids: ["cycle-1"],
    related_execution_ids: [42],
    details: {},
    ...overrides,
  };
}

function baseExecution(overrides = {}) {
  return {
    id: 42,
    trade_intent_id: 7,
    strategy_name: "Breakout",
    instrument: "CS.D.EURUSD.MINI.IP",
    phase: "ENTRY",
    status: "SUBMISSION_PENDING",
    client_request_id: "intent-7-entry",
    broker_reference: null,
    local_position_id: null,
    local_trade_id: null,
    signal_time: TIMESTAMP,
    submitted_at: null,
    acknowledged_at: null,
    completed_at: null,
    last_transition_at: TIMESTAMP,
    requested_size: 1,
    filled_size: null,
    requested_price: 1.08,
    average_fill_price: null,
    intended_risk_amount: 20,
    submitted_risk_amount: null,
    fill_derived_risk_amount: null,
    risk_truth_confidence: "UNKNOWN",
    risk_reconciliation: null,
    material_execution_drift: false,
    critical_execution_drift: false,
    reason: "Broker submission is not confirmed yet.",
    error_code: null,
    error_message: null,
    requires_manual_review: false,
    details: {},
    created_at: TIMESTAMP,
    updated_at: TIMESTAMP,
    ...overrides,
  };
}

function baseTrade(overrides = {}) {
  return {
    id: 12,
    strategy_name: "Breakout",
    broker_reference: "ENTRY-REF-1",
    close_broker_reference: "CLOSE-REF-1",
    close_execution_source: "BROKER_CONFIRMED",
    instrument: "CS.D.EURUSD.MINI.IP",
    direction: "BUY",
    size: 1,
    open_price: 1.08,
    close_price: 1.09,
    open_time: "2026-05-17T09:00:00.000Z",
    close_time: TIMESTAMP,
    pnl: 100,
    account_type: "DEMO",
    r_multiple: 1.2,
    reason: "Strategy exit triggered",
    ...overrides,
  };
}

function basePosition(overrides = {}) {
  return {
    id: 1,
    strategy_name: "Breakout",
    instrument: "CS.D.EURUSD.MINI.IP",
    direction: "BUY",
    size: 1,
    open_price: 1.08,
    open_time: "2026-05-17T09:30:00.000Z",
    current_price: 1.09,
    unrealized_pnl: 80,
    risk_percent: 1.2,
    is_open: true,
    broker_reference: "BROKER-OPEN-1",
    manual_override: false,
    account_type: "DEMO",
    reason: "Protective exit coverage required.",
    ...overrides,
  };
}

function baseStrategy(overrides = {}) {
  return {
    name: "Breakout",
    description: "Momentum breakout strategy",
    instrument: "CS.D.EURUSD.MINI.IP",
    status: "RUNNING",
    current_pnl: 80,
    last_price: 1.09,
    price_status: "LIVE",
    price_error: null,
    last_price_updated_at: TIMESTAMP,
    trade_count: 4,
    win_rate: 0.5,
    account_type: "DEMO",
    position_size: 1,
    risk_per_trade: 1,
    active_instruments: ["CS.D.EURUSD.MINI.IP"],
    authorized: true,
    evaluating_instrument_count: 1,
    candidates_generated_today: 3,
    candidates_promoted_today: 1,
    candidates_blocked_today: 1,
    active_runtime_count: 1,
    open_position_count: 1,
    warning_message: null,
    warning_instrument: null,
    warning_status: null,
    active_runtimes: [],
    open_positions: [],
    instrument_options: [
      {
        epic: "CS.D.EURUSD.MINI.IP",
        label: "EUR/USD",
        category: "Forex",
      },
    ],
    parameters: [],
    ...overrides,
  };
}

function baseMarketCatalogueRow(overrides = {}) {
  return {
    id: "CS.D.EURUSD.MINI.IP",
    instrument: "CS.D.EURUSD.MINI.IP",
    name: "EUR/USD",
    symbol: "EUR/USD",
    asset_class: "FOREX",
    category: "Forex",
    currency: "USD",
    base_currency: "EUR",
    quote_currency: "USD",
    forex_major: true,
    tradable: true,
    shortlisted: false,
    in_strategy_watchlist: false,
    streaming_now: false,
    activity_level: "HIGH",
    strategy_compatibility: ["Breakout"],
    reference_price: 1.08,
    shortlisted_at: null,
    note: null,
    ...overrides,
  };
}

function baseEvent(overrides = {}) {
  return {
    id: 1,
    event_type: "health.stream_stale",
    category: "health",
    severity: "warning",
    title: "Stream stale",
    message: "Stream freshness degraded.",
    source: "runtime",
    strategy_name: null,
    instrument: null,
    correlation_id: null,
    payload_json: {},
    created_at: TIMESTAMP,
    ...overrides,
  };
}

function baseAimeeSnapshot(overrides = {}) {
  return {
    review: {
      metadata: {
        review_id: 101,
        review_type: "operator_summary",
        generated_at: TIMESTAMP,
        requested_date: null,
        scope: {},
        source_coverage: {
          trades_available: true,
          positions_available: true,
          executions_available: true,
          runtimes_available: true,
          reconciliation_available: true,
          broker_summary_available: false,
          stream_health_available: false,
          coverage_notes: ["Telemetry unavailable"],
        },
        generation_mode: "deterministic_only",
      },
      facts: {
        account_value: 10000,
        account_value_change_percent: 0,
        daily_pnl: 120,
        daily_pnl_percent: 1.2,
        open_risk_percent: 1.2,
        open_positions_count: 1,
        active_runtimes: 1,
        main_open_risk: {
          strategy_name: "Breakout",
          instrument: "CS.D.EURUSD.MINI.IP",
          share_of_open_risk_percent: 80,
        },
        largest_risk_share_percent: 80,
        top_risk_exposures: [],
        strategy_health: [],
        risk_rejections_24h: 0,
        execution_failures_24h: 0,
        reconciliation_issues_24h: 0,
        stale_runtimes: 0,
        stream_connected: false,
        stream_last_tick_at: null,
        baseline_open_risk_percent: null,
        baseline_largest_risk_share_percent: null,
        baseline_trade_count_24h: null,
        baseline_win_rate_24h: null,
      },
      derived_observations: [
        {
          code: "review-attention",
          label: "Open risk needs attention.",
          detail: "Operator review remains necessary while telemetry confidence is degraded.",
          severity: "warning",
        },
      ],
      possible_contributors: [],
      warnings: [
        {
          code: "telemetry-unavailable",
          severity: "warning",
          message: "Telemetry source unavailable",
        },
      ],
      supporting_metrics: [],
      ai_summary: null,
      provenance: null,
    },
    history: [],
    controlPlane: baseControlPlaneSummary(),
    coverage: baseCoverageSummary(),
    telemetry: null,
    events: [baseEvent()],
    strategies: [baseStrategy()],
    updatedAt: TIMESTAMP,
    ...overrides,
  };
}

function baseQuestionResponse(overrides = {}) {
  return {
    review_id: 202,
    derived_observations: [
      {
        code: "review-concentration",
        label: "Open risk remains concentrated.",
        detail: "Open risk remains concentrated in EUR/USD and still needs review.",
        severity: "warning",
      },
    ],
    warnings: [
      {
        code: "risk-concentration",
        severity: "warning",
        message: "Open risk concentration needs review.",
      },
    ],
    supporting_metrics: [
      {
        key: "open_risk",
        label: "Open risk",
        value: 1.2,
        unit: "pct",
      },
    ],
    ai_summary: {
      summary: "Open risk remains concentrated in EUR/USD and still needs review.",
    },
    ...overrides,
  };
}

function baseRoutes() {
  return {
    "GET /system/telemetry": ok(baseTelemetry()),
    "GET /health/stream": ok(baseStreamHealth()),
    "GET /coverage/summary": ok(baseCoverageSummary()),
    "GET /control-plane/summary": ok(baseControlPlaneSummary()),
    "GET /system/limits": ok(baseSystemLimits()),
    "GET /dashboard": ok(baseDashboardSnapshot()),
    "GET /allocation/exposure": ok(baseExposure()),
    "GET /allocation/alerts": ok([]),
    "GET /allocation/drift": ok(baseDrift()),
    "GET /allocation/cycles": ok([]),
    "GET /allocation/intents": ok([]),
    "GET /executions": ok([]),
    "GET /trades": ok([]),
    "GET /trades/positions": ok([]),
    "GET /strategies": ok([]),
    "GET /events": ok([]),
    "GET /markets/overview": ok({
      generatedAt: TIMESTAMP,
      summary: {
        category: "forex",
        label: "Forex",
        description: "Major FX instruments.",
        status: "OPEN",
        headline: "Forex open",
        detail: "Market overview available.",
        nextTransitionAt: "2026-05-17T17:00:00.000Z",
        nextTransitionLabel: "Close",
        tradableCount: 1,
        activeCount: 0,
        totalCount: 1,
      },
      instruments: [],
    }),
    "GET /markets/catalogue": ok({
      generated_at: TIMESTAMP,
      instruments: [],
      summary: {
        total_count: 0,
        shortlisted_count: 0,
        strategy_watchlist_count: 0,
        streaming_count: 0,
      },
    }),
    "GET /strategy-watchlist": ok({
      generated_at: TIMESTAMP,
      limit: 8,
      active_count: 0,
      normal_count: 0,
      streaming_count: 0,
      protective_count: 0,
      cap_exceeded_by_protective_coverage: false,
      instruments: [],
    }),
    "GET /aimee/snapshot": ok(baseAimeeSnapshot()),
    "POST /reviews/questions": ok(baseQuestionResponse()),
  };
}

function mergeRoutes(overrides) {
  return {
    ...baseRoutes(),
    ...overrides,
  };
}

export function buildScenarioRoutes(name) {
  switch (name) {
    case "dashboard-stale-truth":
      return mergeRoutes({
        "GET /control-plane/summary": ok(
          baseControlPlaneSummary({
            feed_source_state: "STALE",
            feed_health_state: "DEGRADED",
            entry_eligible: false,
            entry_block_reason: "stale_market_data",
          }),
        ),
        "GET /coverage/summary": ok(
          baseCoverageSummary({
            streaming: {
              active_instruments: [],
              desired_instruments: ["CS.D.EURUSD.MINI.IP"],
              pinned_instruments: [],
              capped_instruments: [],
              asset_class_usage: {},
              execution_readiness: [
                {
                  instrument: "CS.D.EURUSD.MINI.IP",
                  is_ok: false,
                  market_open: true,
                  tradable: true,
                  quote_fresh: false,
                  spread_ok: true,
                  session_valid: true,
                  dealing_allowed: true,
                  last_price_age_ms: 120000,
                  spread: null,
                  reason: "stale_market_data",
                },
              ],
            },
          }),
        ),
        "GET /trades": ok([
          baseTrade({
            id: 12,
            close_execution_source: "SIMULATED_LOCAL_CLOSE",
            close_broker_reference: "LOCAL-CLOSE-1",
            pnl: 45,
          }),
          baseTrade({
            id: 13,
            broker_reference: "ENTRY-REF-2",
            close_broker_reference: "CLOSE-REF-2",
            close_execution_source: "BROKER_CONFIRMED",
            pnl: -20,
          }),
        ]),
        "GET /trades/positions": ok([
          basePosition({
            id: 22,
            broker_reference: null,
            broker_sync_status: "SIMULATED_LOCAL_FILL",
            risk_truth_confidence: "SIMULATED_LOCAL_FILL",
            reason: "Local simulated fill; broker confirmation is unavailable.",
          }),
        ]),
      });
    case "live-outage":
      return mergeRoutes({
        "GET /system/telemetry": unavailable("Backend source unavailable."),
        "GET /health/stream": unavailable("Backend source unavailable."),
        "GET /coverage/summary": unavailable("Backend source unavailable."),
        "GET /control-plane/summary": unavailable("Backend source unavailable."),
        "GET /allocation/exposure": unavailable("Backend source unavailable."),
        "GET /allocation/alerts": unavailable("Backend source unavailable."),
        "GET /events": unavailable("Backend source unavailable."),
        "GET /executions": unavailable("Backend source unavailable."),
        "GET /trades/positions": unavailable("Backend source unavailable."),
        "GET /strategies": unavailable("Backend source unavailable."),
        "GET /aimee/snapshot": ok(
          baseAimeeSnapshot({
            telemetry: null,
            controlPlane: null,
            coverage: null,
            review: null,
            strategies: [],
            events: [],
          }),
        ),
      });
    case "risk-truth-degraded":
      return mergeRoutes({
        "GET /allocation/exposure": unavailable("Allocation exposure backend unavailable."),
        "GET /allocation/alerts": ok([baseAlert()]),
        "GET /allocation/intents": ok([
          {
            id: 7,
            strategy_name: "Breakout",
            family_name: "Breakout",
            instrument: "CS.D.EURUSD.MINI.IP",
            estimated_risk_amount: 35,
            submitted_risk_amount: null,
            fill_derived_risk_amount: null,
            risk_truth_confidence: "SIMULATED_LOCAL_FILL",
            latest_execution: baseExecution({
              status: "SUBMISSION_PENDING",
              requested_size: 1,
            }),
            position: null,
          },
          {
            id: 8,
            strategy_name: "Breakout",
            family_name: "Breakout",
            instrument: "CS.D.GBPUSD.MINI.IP",
            estimated_risk_amount: 40,
            submitted_risk_amount: 39,
            fill_derived_risk_amount: 28,
            risk_truth_confidence: "PARTIAL_FILL_PROVISIONAL",
            latest_execution: baseExecution({
              id: 43,
              instrument: "CS.D.GBPUSD.MINI.IP",
              status: "PARTIALLY_FILLED",
              average_fill_price: null,
              filled_size: 0.6,
              requested_size: 1,
            }),
            position: {
              risk_truth_confidence: "PARTIAL_FILL_PROVISIONAL",
            },
          },
        ]),
      });
    case "risk-alert-mutation-failure":
      return mergeRoutes({
        "GET /allocation/alerts": ok([baseAlert()]),
        "POST /allocation/alerts/5/acknowledge": response(503, {
          detail: "backend domain-event persistence failed for alert 5",
        }),
      });
    case "risk-recovery-adoption-truth":
      return mergeRoutes({
        "GET /allocation/intents": ok([
          {
            id: 71,
            strategy_name: "Breakout",
            family_name: "Breakout",
            instrument: "CS.D.EURUSD.MINI.IP",
            direction: "BUY",
            state: "RECOVERED_POSITION_ATTACHED",
            signal_time: TIMESTAMP,
            decision_reason_code: "runtime_recovery",
            decision_reason: "Recovered broker-confirmed open risk was reattached during startup recovery.",
            estimated_risk_amount: 48,
            submitted_risk_amount: 48,
            fill_derived_risk_amount: 47,
            risk_truth_confidence: "BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED",
            allocation: {},
            allocation_outcome: {},
            risk_tracking: {},
            risk_reconciliation: {},
            latest_execution: baseExecution({
              id: 171,
              phase: "ENTRY",
              status: "POSITION_OPENED",
              broker_reference: safeIdentifier("BRK…OVR-71", "fp-rec-71"),
              average_fill_price: 1.081,
              filled_size: 1,
              reason: "Recovered broker open risk remains live after restart.",
            }),
            executions: [],
            position: {
              id: 71,
              broker_reference: safeIdentifier("BRK…OVR-71", "fp-rec-71"),
              instrument: "CS.D.EURUSD.MINI.IP",
              direction: "BUY",
              size: 1,
              open_price: 1.081,
              current_price: 1.09,
              unrealized_pnl: 32,
              risk_percent: 1.1,
              entry_risk_amount: 47,
              risk_truth_confidence: "BROKER_CONFIRMED_AVERAGE_FILL_ESTIMATED",
              open_time: "2026-05-17T08:45:00.000Z",
              is_open: true,
            },
            trade: null,
            details: {},
            created_at: TIMESTAMP,
            updated_at: TIMESTAMP,
          },
          {
            id: 72,
            strategy_name: "Breakout",
            family_name: "Breakout",
            instrument: "CS.D.GBPUSD.MINI.IP",
            direction: "SELL",
            state: "EXTERNAL_POSITION_ADOPTED",
            signal_time: TIMESTAMP,
            decision_reason_code: "broker_reconciliation_adopted",
            decision_reason: "Broker position was adopted during reconciliation rather than opened by normal strategy entry.",
            estimated_risk_amount: 36,
            submitted_risk_amount: null,
            fill_derived_risk_amount: null,
            risk_truth_confidence: "UNKNOWN",
            allocation: {},
            allocation_outcome: {},
            risk_tracking: {},
            risk_reconciliation: {},
            latest_execution: baseExecution({
              id: 172,
              phase: "ENTRY",
              status: "NEEDS_MANUAL_REVIEW",
              broker_reference: safeIdentifier("BRK…OPT-72", "fp-adopt-72"),
              reason: "Adopted external broker position remains open until local lifecycle catches up.",
              requires_manual_review: true,
            }),
            executions: [],
            position: {
              id: 72,
              broker_reference: safeIdentifier("BRK…OPT-72", "fp-adopt-72"),
              instrument: "CS.D.GBPUSD.MINI.IP",
              direction: "SELL",
              size: 0.8,
              open_price: 1.245,
              current_price: 1.238,
              unrealized_pnl: 21,
              risk_percent: 0.9,
              entry_risk_amount: 36,
              risk_truth_confidence: "UNKNOWN",
              open_time: "2026-05-17T08:40:00.000Z",
              is_open: true,
            },
            trade: null,
            details: {},
            created_at: TIMESTAMP,
            updated_at: TIMESTAMP,
          },
        ]),
      });
    case "strategies-start-failure-detail":
      return mergeRoutes({
        "GET /strategies": ok([
          baseStrategy({
            status: "STOPPED",
            current_pnl: 0,
            last_price: null,
            price_status: "STOPPED",
            active_instruments: [],
            active_runtime_count: 0,
            open_position_count: 0,
            active_runtimes: [],
            open_positions: [],
          }),
        ]),
        "POST /strategy/start": delayed(
          response(503, {
            detail: "strategy runtime start failed because durable audit persistence is unavailable",
          }),
          400,
        ),
      });
    case "strategies-start-refresh-failure":
      return mergeRoutes({
        "GET /strategies": [
          ok([
            baseStrategy({
              status: "STOPPED",
              current_pnl: 0,
              last_price: null,
              price_status: "STOPPED",
              active_instruments: [],
              active_runtime_count: 0,
              open_position_count: 0,
              active_runtimes: [],
              open_positions: [],
            }),
          ]),
          ok([
            baseStrategy({
              status: "STOPPED",
              current_pnl: 0,
              last_price: null,
              price_status: "STOPPED",
              active_instruments: [],
              active_runtime_count: 0,
              open_position_count: 0,
              active_runtimes: [],
              open_positions: [],
            }),
          ]),
          unavailable("strategy truth refresh failed after runtime start"),
        ],
        "POST /strategy/start": delayed(
          ok({
            status: "started",
            strategy: "Breakout",
            instrument: "CS.D.EURUSD.MINI.IP",
          }),
          400,
        ),
      });
    case "strategies-start-disabled-reason":
      return mergeRoutes({
        "GET /strategies": ok([
          baseStrategy({
            status: "STOPPED",
            current_pnl: 0,
            instrument: "",
            last_price: null,
            price_status: "STOPPED",
            active_instruments: [],
            active_runtime_count: 0,
            open_position_count: 0,
            active_runtimes: [],
            open_positions: [],
            instrument_options: [],
          }),
        ]),
      });
    case "strategies-open-risk":
      return mergeRoutes({
        "GET /strategies": ok([
          baseStrategy({
            active_runtimes: [
              {
                instrument: "CS.D.EURUSD.MINI.IP",
                has_open_position: true,
                direction: "BUY",
                broker_reference: "BROKER-OPEN-1",
                unrealized_pnl: 80,
              },
            ],
            open_positions: [basePosition()],
          }),
        ]),
        "GET /executions": ok([
          baseExecution({
            status: "POSITION_OPENED",
            broker_reference: "BROKER-OPEN-1",
            reason: "Broker-confirmed open position remains live.",
          }),
        ]),
      });
    case "strategies-stop-open-risk-confirmation":
      return mergeRoutes({
        "GET /strategies": [
          ok([
            baseStrategy({
              active_runtimes: [
                {
                  instrument: "CS.D.EURUSD.MINI.IP",
                  has_open_position: true,
                  direction: "BUY",
                  broker_reference: "BROKER-OPEN-9",
                  unrealized_pnl: 45,
                  control_mode: "MANUAL",
                  runtime_mode: "EXITS_ONLY",
                },
              ],
              open_positions: [basePosition({ broker_reference: "BROKER-OPEN-9" })],
            }),
          ]),
          ok([
            baseStrategy({
              active_runtimes: [
                {
                  instrument: "CS.D.EURUSD.MINI.IP",
                  has_open_position: true,
                  direction: "BUY",
                  broker_reference: "BROKER-OPEN-9",
                  unrealized_pnl: 45,
                  control_mode: "MANUAL",
                  runtime_mode: "EXITS_ONLY",
                },
              ],
              open_positions: [basePosition({ broker_reference: "BROKER-OPEN-9" })],
            }),
          ]),
          ok([
            baseStrategy({
              status: "STOPPED",
              current_pnl: 0,
              last_price: 1.09,
              price_status: "POSITION",
              active_instruments: [],
              active_runtime_count: 0,
              open_position_count: 1,
              active_runtimes: [],
              open_positions: [basePosition({ broker_reference: "BROKER-OPEN-9" })],
            }),
          ]),
        ],
        "POST /strategy/stop": delayed(
          ok({
            status: "stopped",
            strategy: "Breakout",
            instrument: "CS.D.EURUSD.MINI.IP",
          }),
          400,
        ),
      });
    case "strategies-stop-failure-detail":
      return mergeRoutes({
        "GET /strategies": [
          ok([
            baseStrategy({
              active_runtimes: [
                {
                  instrument: "CS.D.EURUSD.MINI.IP",
                  has_open_position: true,
                  direction: "BUY",
                  broker_reference: "BROKER-OPEN-10",
                  unrealized_pnl: 30,
                  control_mode: "MANUAL",
                  runtime_mode: "EXITS_ONLY",
                },
              ],
              open_positions: [basePosition({ broker_reference: "BROKER-OPEN-10" })],
            }),
          ]),
          ok([
            baseStrategy({
              active_runtimes: [
                {
                  instrument: "CS.D.EURUSD.MINI.IP",
                  has_open_position: true,
                  direction: "BUY",
                  broker_reference: "BROKER-OPEN-10",
                  unrealized_pnl: 30,
                  control_mode: "MANUAL",
                  runtime_mode: "EXITS_ONLY",
                },
              ],
              open_positions: [basePosition({ broker_reference: "BROKER-OPEN-10" })],
            }),
          ]),
        ],
        "POST /strategy/stop": delayed(
          response(503, {
            detail: "runtime stop failed because open-risk handoff audit persistence failed",
          }),
          400,
        ),
      });
    case "strategies-execution-simulated-provenance":
      return mergeRoutes({
        "GET /strategies": ok([
          baseStrategy({
            open_position_count: 0,
            active_runtimes: [],
            open_positions: [],
          }),
        ]),
        "GET /executions": ok([
          baseExecution({
            id: 91,
            status: "POSITION_OPENED",
            broker_reference: "SIM-ENTRY-91",
            reason: "Local simulated fill remains visible until broker reconciliation is complete.",
            details: {
              execution_source: "SIMULATED_LOCAL_FILL",
            },
          }),
        ]),
      });
    case "aimee-passive":
      return mergeRoutes({});
    case "aimee-advisory-failure":
      return mergeRoutes({
        "POST /reviews/questions": response(503, {
          detail: "review persistence failed for advisory question",
        }),
      });
    case "dashboard-entry-manual-review":
      return mergeRoutes({
        "GET /executions": ok([
          baseExecution({
            id: 51,
            status: "NEEDS_MANUAL_REVIEW",
            requires_manual_review: true,
            reason: "Broker confirmation timed out; entry fill status remains ambiguous.",
            error_message: "Broker confirmation timed out; entry fill status remains ambiguous.",
          }),
          baseExecution({
            id: 52,
            status: "RISK_REJECTED",
            requires_manual_review: false,
            reason: "stale_market_data blocked a new order attempt.",
          }),
          baseExecution({
            id: 53,
            status: "SUBMISSION_PENDING",
            requires_manual_review: false,
            reason: "Entry request is still pending broker submission.",
          }),
        ]),
        "GET /trades/positions": ok([]),
        "GET /dashboard": ok(
          baseDashboardSnapshot({
            openRisk: 0,
            runningStrategies: [],
          }),
        ),
      });
    case "strategies-close-manual-review":
      return mergeRoutes({
        "GET /strategies": ok([
          baseStrategy({
            open_position_count: 1,
            active_runtimes: [
              {
                strategy_name: "Breakout",
                instrument: "CS.D.EURUSD.MINI.IP",
                runtime_key: "Breakout:CS.D.EURUSD.MINI.IP",
                has_open_position: true,
                broker_reference: safeIdentifier("BRK…OPEN-2", "fp-open-2"),
                direction: "BUY",
                current_price: 1.09,
                unrealized_pnl: 35,
              },
            ],
            open_positions: [
              basePosition({
                broker_reference: safeIdentifier("BRK…OPEN-2", "fp-open-2"),
                reason: "Close remains under manual review until broker truth is reconciled.",
              }),
            ],
          }),
        ]),
        "GET /executions": ok([
          baseExecution({
            id: 61,
            phase: "CLOSE",
            status: "NEEDS_MANUAL_REVIEW",
            requires_manual_review: true,
            broker_reference: "CLOSE-REQ-2",
            reason: "Broker close confirmation timed out; open risk still remains live.",
            error_message: "Broker close confirmation timed out; open risk still remains live.",
          }),
          baseExecution({
            id: 62,
            phase: "CLOSE",
            status: "CLOSE_REQUESTED",
            requires_manual_review: false,
            broker_reference: "CLOSE-REQ-3",
            reason: "Close submitted; final broker close is not confirmed.",
          }),
        ]),
      });
    case "control-plane-misaligned-truth":
      return mergeRoutes({
        "GET /control-plane/summary": ok(
          baseControlPlaneSummary({
            misaligned_count: 1,
            entry_eligible: false,
            entry_block_reason: "runtime_misaligned",
            families: [
              baseFamily({
                deployment: {
                  ...baseFamily().deployment,
                  state: "DEGRADED",
                  selected_instrument: "CS.D.EURUSD.MINI.IP",
                  degraded_reason: "Runtime and deployment remain misaligned across instrument and mode.",
                  open_risk_management_state: "UNAVAILABLE",
                  open_risk_management_reason: "Runtime and deployment drift are unresolved; open risk cannot be treated as cleared.",
                },
                runtime: {
                  ...baseFamily().runtime,
                  active_instrument: "CS.D.GBPUSD.MINI.IP",
                  control_mode: "MANUAL",
                  runtime_mode: "EXITS_ONLY",
                },
                alignment: {
                  is_aligned: false,
                  status: "MISMATCH",
                  reason: "Runtime remains on GBP/USD while deployment intends EUR/USD.",
                  checks: [
                    {
                      code: "instrument",
                      passed: false,
                      expected: "CS.D.EURUSD.MINI.IP",
                      actual: "CS.D.GBPUSD.MINI.IP",
                    },
                  ],
                },
              }),
            ],
          }),
        ),
      });
    case "control-plane-unsupported-states":
      return mergeRoutes({
        "GET /control-plane/summary": ok(
          baseControlPlaneSummary({
            effective_autonomous_control_enabled: false,
            autonomy_override_active: true,
            autonomy_override_value: false,
            autonomy_override_reason: "Operator forced governed autonomy pause while unsupported family state requires review.",
            entry_eligible: false,
            exit_eligible: true,
            entry_block_reason: "operator_override_active",
            open_risk_management_state: "UNKNOWN",
            open_risk_management_reason: "Open-risk management truth is unsupported and cannot be treated as safe.",
            counts: {
              EMERGENCY_STOPPED: 1,
            },
            families: [
              baseFamily({
                governance: {
                  ...baseFamily().governance,
                  approval_state: "BROKER_MAGIC",
                  autonomous_operation_allowed: false,
                  emergency_stop: true,
                },
                deployment: {
                  ...baseFamily().deployment,
                  state: "BROKER_MAGIC",
                  degraded_reason: "Backend returned an unsupported deployment state while emergency controls remained active.",
                  open_risk_management_state: "UNKNOWN",
                  open_risk_management_reason: "Open-risk management truth is unsupported and cannot be treated as safe.",
                },
                runtime: {
                  ...baseFamily().runtime,
                  control_mode: "BROKER_MAGIC",
                  runtime_mode: "BROKER_MAGIC",
                },
                alignment: {
                  is_aligned: false,
                  status: "BROKER_MAGIC",
                  reason: "Backend returned an unsupported alignment state; family truth is degraded.",
                  checks: [],
                },
              }),
            ],
          }),
        ),
      });
    case "strategies-recovered-open-risk":
      return mergeRoutes({
        "GET /strategies": ok([
          baseStrategy({
            status: "STOPPED",
            current_pnl: 0,
            last_price: 1.09,
            price_status: "POSITION",
            active_instruments: [],
            active_runtime_count: 0,
            open_position_count: 1,
            active_runtimes: [],
            open_positions: [
              {
                broker_reference: safeIdentifier("BRK…RCV-14", "fp-rcv-14"),
                instrument: "CS.D.EURUSD.MINI.IP",
                direction: "BUY",
                size: 1,
                open_price: 1.08,
                current_price: 1.09,
                unrealized_pnl: 28,
                risk_percent: 1.15,
              },
            ],
            persisted_runtimes: [
              {
                runtime_id: safeIdentifier("run…breakout-14", "fp-run-14"),
                instrument: "CS.D.EURUSD.MINI.IP",
                status: "STOPPED",
                recovery_state: "PAUSED",
                recovery_reason: "Recovered during startup reconciliation from broker-confirmed open position truth.",
                control_mode: "MANUAL",
                runtime_mode: "STOPPED",
                parameters: {},
              },
            ],
          }),
        ]),
        "GET /executions": ok([
          baseExecution({
            id: 141,
            status: "POSITION_OPENED",
            broker_reference: safeIdentifier("BRK…RCV-14", "fp-rcv-14"),
            reason: "Recovered broker open risk remains live after runtime stop.",
          }),
        ]),
      });
    case "coverage-polling-fallback":
      return mergeRoutes({
        "GET /coverage/summary": ok(
          baseCoverageSummary({
            streaming: {
              active_instruments: [
                {
                  instrument: "CS.D.EURUSD.MINI.IP",
                  tier: "TIER1",
                  status: "ACTIVE",
                  asset_class: "FOREX",
                  pinned: false,
                  reason: "strategy_watchlist",
                  reason_detail: null,
                  protective: false,
                  priority_score: 1,
                  requested_frequency: "1s",
                  promotion_expires_at: null,
                  last_streamed_at: TIMESTAMP,
                  last_refreshed_at: TIMESTAMP,
                  streamed: true,
                },
              ],
              execution_readiness: [
                {
                  instrument: "CS.D.EURUSD.MINI.IP",
                  is_ok: false,
                  market_open: true,
                  tradable: true,
                  quote_fresh: false,
                  spread_ok: true,
                  session_valid: true,
                  dealing_allowed: true,
                  last_price_age_ms: 45000,
                  spread: null,
                  reason: "polling_fallback",
                },
              ],
              desired_instruments: ["CS.D.EURUSD.MINI.IP"],
              pinned_instruments: [],
              capped_instruments: [],
              asset_class_usage: {},
            },
          }),
        ),
        "GET /system/telemetry": ok(
          baseTelemetry({
            status: "degraded",
            stream_connected: false,
            stream_last_tick_at: null,
            stream_last_tick_age_ms: null,
            feed_source_state: "POLLING_FALLBACK",
            feed_health_state: "DEGRADED",
            entry_eligible: false,
            entry_block_reason: "polling_fallback",
          }),
        ),
        "GET /control-plane/summary": ok(
          baseControlPlaneSummary({
            feed_source_state: "POLLING_FALLBACK",
            feed_health_state: "DEGRADED",
            entry_eligible: false,
            entry_block_reason: "polling_fallback",
          }),
        ),
        "GET /health/stream": ok(
          baseStreamHealth({
            connected: false,
            dependency_ready: false,
            last_tick_at: null,
            last_status: "Polling fallback active",
            last_error: "Streaming dependency unavailable; polling fallback is active.",
          }),
        ),
        "GET /market-data/feed-state": ok({
          generated_at: TIMESTAMP,
          instruments: [
            {
              instrument: "CS.D.EURUSD.MINI.IP",
              stream_status: "POLLING_FALLBACK",
              stream_connected: false,
              stream_enabled: true,
              streaming_now: false,
              desired: true,
              capped: false,
              last_tick_at: null,
              last_tick_age_ms: null,
              spread: null,
              price_source: "FALLBACK",
              stream_reason: {
                code: "polling_fallback",
                label: "Polling fallback",
                operator_action: "Live stream is unavailable; fallback polling is active.",
              },
              market_status: null,
              market_error: null,
              entry_eligibility: "BLOCKED",
              entry_eligibility_reason: {
                code: "polling_fallback",
                label: "Polling fallback",
                operator_action: "Entry is blocked while fallback polling is active.",
              },
              strategies_may_evaluate: false,
              active_strategy_runtime_count: 1,
              watchlist_entry: null,
            },
          ],
        }),
      });
    case "markets-unavailable-truth":
      return mergeRoutes({
        "GET /markets/overview": ok({
          generatedAt: TIMESTAMP,
          summary: {
            category: "forex",
            label: "Forex",
            description: "Market overview backend data is unavailable.",
            status: "UNAVAILABLE",
            headline: "Backend unavailable",
            detail: "Market overview could not be loaded. Counts are unavailable, not zero market truth.",
            nextTransitionAt: TIMESTAMP,
            nextTransitionLabel: "Unavailable",
            tradableCount: 0,
            activeCount: 0,
            totalCount: 0,
          },
          instruments: [],
        }),
        "GET /markets/catalogue": unavailable("Catalogue unavailable."),
        "GET /strategy-watchlist": unavailable("Strategy watchlist unavailable."),
      });
    case "dashboard-disconnected-truth":
      return mergeRoutes({
        "GET /control-plane/summary": ok(
          baseControlPlaneSummary({
            feed_source_state: "DISCONNECTED",
            feed_health_state: "FAILED",
            entry_eligible: false,
            entry_block_reason: "stream_disconnected",
          }),
        ),
        "GET /health/stream": ok(
          baseStreamHealth({
            connected: false,
            dependency_ready: false,
            last_tick_at: null,
            last_status: "Disconnected",
            last_error: "Live stream is unavailable.",
          }),
        ),
        "GET /coverage/summary": ok(
          baseCoverageSummary({
            streaming: {
              active_instruments: [],
              desired_instruments: ["CS.D.EURUSD.MINI.IP"],
              pinned_instruments: [],
              capped_instruments: [],
              asset_class_usage: {},
              execution_readiness: [
                {
                  instrument: "CS.D.EURUSD.MINI.IP",
                  is_ok: false,
                  market_open: true,
                  tradable: true,
                  quote_fresh: false,
                  spread_ok: true,
                  session_valid: false,
                  dealing_allowed: false,
                  last_price_age_ms: null,
                  spread: null,
                  reason: "stream_disconnected",
                },
              ],
            },
          }),
        ),
      });
    case "dashboard-recovered-truth":
      return mergeRoutes({
        "GET /control-plane/summary": ok(
          baseControlPlaneSummary({
            feed_source_state: "LIVE",
            feed_health_state: "HEALTHY",
            entry_eligible: true,
          }),
        ),
        "GET /health/stream": ok(
          baseStreamHealth({
            connected: true,
            last_tick_at: TIMESTAMP,
            last_status: "Recovered after stream disconnect",
          }),
        ),
      });
    case "markets-watchlist-provenance":
      return mergeRoutes({
        "GET /markets/catalogue": ok({
          generated_at: TIMESTAMP,
          instruments: [
            {
              id: "CS.D.EURUSD.MINI.IP",
              instrument: "CS.D.EURUSD.MINI.IP",
              name: "EUR/USD",
              symbol: "EUR/USD",
              asset_class: "FOREX",
              category: "Forex",
              currency: "USD",
              base_currency: "EUR",
              quote_currency: "USD",
              forex_major: true,
              tradable: true,
              shortlisted: true,
              in_strategy_watchlist: true,
              streaming_now: false,
              activity_level: "HIGH",
              strategy_compatibility: ["Breakout"],
              reference_price: 1.08,
              shortlisted_at: null,
              note: null,
            },
          ],
          summary: {
            total_count: 1,
            shortlisted_count: 1,
            strategy_watchlist_count: 1,
            streaming_count: 0,
          },
        }),
        "GET /strategy-watchlist": ok({
          generated_at: TIMESTAMP,
          limit: 10,
          active_count: 1,
          normal_count: 1,
          streaming_count: 0,
          protective_count: 0,
          cap_exceeded_by_protective_coverage: false,
          instruments: [
            {
              instrument: "CS.D.EURUSD.MINI.IP",
              tier: "TIER1",
              status: "ACTIVE",
              asset_class: "FOREX",
              pinned: false,
              reason: "strategy_watchlist",
              reason_detail: {
                code: "strategy_watchlist",
                label: "Strategy watchlist",
                operator_action: "Watchlisted for evaluation only; entry still depends on governance, risk, broker, and market-data gates.",
              },
              protective: false,
              priority_score: 1,
              requested_frequency: "1s",
              promotion_expires_at: null,
              last_streamed_at: null,
              last_refreshed_at: TIMESTAMP,
              streamed: false,
            },
          ],
        }),
      });
    case "markets-shortlist-failure-retry":
      return mergeRoutes({
        "GET /markets/catalogue": [
          ok({
            generated_at: TIMESTAMP,
            instruments: [baseMarketCatalogueRow()],
            summary: {
              total_count: 1,
              shortlisted_count: 0,
              strategy_watchlist_count: 0,
              streaming_count: 0,
            },
          }),
          ok({
            generated_at: TIMESTAMP,
            instruments: [
              baseMarketCatalogueRow({
                shortlisted: true,
              }),
            ],
            summary: {
              total_count: 1,
              shortlisted_count: 1,
              strategy_watchlist_count: 0,
              streaming_count: 0,
            },
          }),
        ],
        "GET /strategy-watchlist": [
          ok({
            generated_at: TIMESTAMP,
            limit: 8,
            active_count: 0,
            normal_count: 0,
            streaming_count: 0,
            protective_count: 0,
            cap_exceeded_by_protective_coverage: false,
            instruments: [],
          }),
          ok({
            generated_at: TIMESTAMP,
            limit: 8,
            active_count: 0,
            normal_count: 0,
            streaming_count: 0,
            protective_count: 0,
            cap_exceeded_by_protective_coverage: false,
            instruments: [],
          }),
        ],
        "GET /markets/overview": [
          ok({
            generatedAt: TIMESTAMP,
            summary: {
              category: "forex",
              label: "Forex",
              description: "Major FX instruments.",
              status: "OPEN",
              headline: "Forex open",
              detail: "Market overview available.",
              nextTransitionAt: "2026-05-17T17:00:00.000Z",
              nextTransitionLabel: "Close",
              tradableCount: 1,
              activeCount: 0,
              totalCount: 1,
            },
            instruments: [],
          }),
          ok({
            generatedAt: TIMESTAMP,
            summary: {
              category: "forex",
              label: "Forex",
              description: "Major FX instruments.",
              status: "OPEN",
              headline: "Forex open",
              detail: "Market overview available.",
              nextTransitionAt: "2026-05-17T17:00:00.000Z",
              nextTransitionLabel: "Close",
              tradableCount: 1,
              activeCount: 0,
              totalCount: 1,
            },
            instruments: [],
          }),
        ],
        "POST /watchlist/shortlist/CS.D.EURUSD.MINI.IP": [
          delayed(
            response(503, {
              detail: "shortlist write failed because operator audit persistence is unavailable",
            }),
            400,
          ),
          delayed(
            ok({
              status: "shortlisted",
              instrument: "CS.D.EURUSD.MINI.IP",
            }),
            400,
          ),
        ],
      });
    case "markets-shortlist-remove-failure-retry":
      return mergeRoutes({
        "GET /markets/catalogue": [
          ok({
            generated_at: TIMESTAMP,
            instruments: [
              baseMarketCatalogueRow({
                shortlisted: true,
              }),
            ],
            summary: {
              total_count: 1,
              shortlisted_count: 1,
              strategy_watchlist_count: 0,
              streaming_count: 0,
            },
          }),
          ok({
            generated_at: TIMESTAMP,
            instruments: [baseMarketCatalogueRow()],
            summary: {
              total_count: 1,
              shortlisted_count: 0,
              strategy_watchlist_count: 0,
              streaming_count: 0,
            },
          }),
        ],
        "GET /strategy-watchlist": [
          ok({
            generated_at: TIMESTAMP,
            limit: 8,
            active_count: 0,
            normal_count: 0,
            streaming_count: 0,
            protective_count: 0,
            cap_exceeded_by_protective_coverage: false,
            instruments: [],
          }),
          ok({
            generated_at: TIMESTAMP,
            limit: 8,
            active_count: 0,
            normal_count: 0,
            streaming_count: 0,
            protective_count: 0,
            cap_exceeded_by_protective_coverage: false,
            instruments: [],
          }),
        ],
        "GET /markets/overview": [
          ok({
            generatedAt: TIMESTAMP,
            summary: {
              category: "forex",
              label: "Forex",
              description: "Major FX instruments.",
              status: "OPEN",
              headline: "Forex open",
              detail: "Market overview available.",
              nextTransitionAt: "2026-05-17T17:00:00.000Z",
              nextTransitionLabel: "Close",
              tradableCount: 1,
              activeCount: 0,
              totalCount: 1,
            },
            instruments: [],
          }),
          ok({
            generatedAt: TIMESTAMP,
            summary: {
              category: "forex",
              label: "Forex",
              description: "Major FX instruments.",
              status: "OPEN",
              headline: "Forex open",
              detail: "Market overview available.",
              nextTransitionAt: "2026-05-17T17:00:00.000Z",
              nextTransitionLabel: "Close",
              tradableCount: 1,
              activeCount: 0,
              totalCount: 1,
            },
            instruments: [],
          }),
        ],
        "DELETE /watchlist/shortlist/CS.D.EURUSD.MINI.IP": [
          delayed(
            response(503, {
              detail: "shortlist removal failed because operator audit persistence is unavailable",
            }),
            400,
          ),
          delayed(
            ok({
              status: "removed",
              instrument: "CS.D.EURUSD.MINI.IP",
            }),
            400,
          ),
        ],
      });
    case "markets-watchlist-add-refresh-failure":
      return mergeRoutes({
        "GET /markets/catalogue": [
          ok({
            generated_at: TIMESTAMP,
            instruments: [
              baseMarketCatalogueRow({
                shortlisted: true,
              }),
            ],
            summary: {
              total_count: 1,
              shortlisted_count: 1,
              strategy_watchlist_count: 0,
              streaming_count: 0,
            },
          }),
          ok({
            generated_at: TIMESTAMP,
            instruments: [
              baseMarketCatalogueRow({
                shortlisted: true,
                in_strategy_watchlist: true,
              }),
            ],
            summary: {
              total_count: 1,
              shortlisted_count: 1,
              strategy_watchlist_count: 1,
              streaming_count: 0,
            },
          }),
        ],
        "GET /strategy-watchlist": [
          ok({
            generated_at: TIMESTAMP,
            limit: 8,
            active_count: 0,
            normal_count: 0,
            streaming_count: 0,
            protective_count: 0,
            cap_exceeded_by_protective_coverage: false,
            instruments: [],
          }),
          unavailable("strategy watchlist refresh failed after mutation"),
        ],
        "GET /markets/overview": [
          ok({
            generatedAt: TIMESTAMP,
            summary: {
              category: "forex",
              label: "Forex",
              description: "Major FX instruments.",
              status: "OPEN",
              headline: "Forex open",
              detail: "Market overview available.",
              nextTransitionAt: "2026-05-17T17:00:00.000Z",
              nextTransitionLabel: "Close",
              tradableCount: 1,
              activeCount: 0,
              totalCount: 1,
            },
            instruments: [],
          }),
          ok({
            generatedAt: TIMESTAMP,
            summary: {
              category: "forex",
              label: "Forex",
              description: "Major FX instruments.",
              status: "OPEN",
              headline: "Forex open",
              detail: "Market overview available.",
              nextTransitionAt: "2026-05-17T17:00:00.000Z",
              nextTransitionLabel: "Close",
              tradableCount: 1,
              activeCount: 0,
              totalCount: 1,
            },
            instruments: [],
          }),
        ],
        "POST /strategy-watchlist/bulk": delayed(
          ok({
            added: [
              {
                instrument: "CS.D.EURUSD.MINI.IP",
                reason: "shortlist",
                reason_detail: {
                  code: "shortlist",
                  label: "Shortlist",
                  operator_action: "Moved from operator shortlist into evaluation watchlist only.",
                },
              },
            ],
            skipped: [],
            limit: 8,
          }),
          400,
        ),
      });
    case "markets-watchlist-remove-confirmed":
      return mergeRoutes({
        "GET /markets/catalogue": [
          ok({
            generated_at: TIMESTAMP,
            instruments: [
              baseMarketCatalogueRow({
                shortlisted: true,
                in_strategy_watchlist: true,
              }),
            ],
            summary: {
              total_count: 1,
              shortlisted_count: 1,
              strategy_watchlist_count: 1,
              streaming_count: 0,
            },
          }),
          ok({
            generated_at: TIMESTAMP,
            instruments: [
              baseMarketCatalogueRow({
                shortlisted: true,
                in_strategy_watchlist: false,
              }),
            ],
            summary: {
              total_count: 1,
              shortlisted_count: 1,
              strategy_watchlist_count: 0,
              streaming_count: 0,
            },
          }),
        ],
        "GET /strategy-watchlist": [
          ok({
            generated_at: TIMESTAMP,
            limit: 8,
            active_count: 1,
            normal_count: 1,
            streaming_count: 0,
            protective_count: 0,
            cap_exceeded_by_protective_coverage: false,
            instruments: [
              {
                instrument: "CS.D.EURUSD.MINI.IP",
                tier: "TIER1",
                status: "ACTIVE",
                asset_class: "FOREX",
                pinned: false,
                reason: "strategy_watchlist",
                reason_detail: {
                  code: "strategy_watchlist",
                  label: "Strategy watchlist",
                  operator_action: "Watchlisted for evaluation only; entry still depends on governance, risk, broker, and market-data gates.",
                },
                protective: false,
                priority_score: 1,
                requested_frequency: "1s",
                promotion_expires_at: null,
                last_streamed_at: null,
                last_refreshed_at: TIMESTAMP,
                streamed: false,
              },
            ],
          }),
          ok({
            generated_at: TIMESTAMP,
            limit: 8,
            active_count: 0,
            normal_count: 0,
            streaming_count: 0,
            protective_count: 0,
            cap_exceeded_by_protective_coverage: false,
            instruments: [],
          }),
        ],
        "GET /markets/overview": [
          ok({
            generatedAt: TIMESTAMP,
            summary: {
              category: "forex",
              label: "Forex",
              description: "Major FX instruments.",
              status: "OPEN",
              headline: "Forex open",
              detail: "Market overview available.",
              nextTransitionAt: "2026-05-17T17:00:00.000Z",
              nextTransitionLabel: "Close",
              tradableCount: 1,
              activeCount: 0,
              totalCount: 1,
            },
            instruments: [],
          }),
          ok({
            generatedAt: TIMESTAMP,
            summary: {
              category: "forex",
              label: "Forex",
              description: "Major FX instruments.",
              status: "OPEN",
              headline: "Forex open",
              detail: "Market overview available.",
              nextTransitionAt: "2026-05-17T17:00:00.000Z",
              nextTransitionLabel: "Close",
              tradableCount: 1,
              activeCount: 0,
              totalCount: 1,
            },
            instruments: [],
          }),
        ],
        "DELETE /strategy-watchlist/CS.D.EURUSD.MINI.IP": delayed(
          ok({
            status: "removed",
            instrument: "CS.D.EURUSD.MINI.IP",
          }),
          400,
        ),
      });
    case "markets-watchlist-remove-failure-retry":
      return mergeRoutes({
        "GET /markets/catalogue": [
          ok({
            generated_at: TIMESTAMP,
            instruments: [
              baseMarketCatalogueRow({
                shortlisted: true,
                in_strategy_watchlist: true,
              }),
            ],
            summary: {
              total_count: 1,
              shortlisted_count: 1,
              strategy_watchlist_count: 1,
              streaming_count: 0,
            },
          }),
          ok({
            generated_at: TIMESTAMP,
            instruments: [
              baseMarketCatalogueRow({
                shortlisted: true,
                in_strategy_watchlist: false,
              }),
            ],
            summary: {
              total_count: 1,
              shortlisted_count: 1,
              strategy_watchlist_count: 0,
              streaming_count: 0,
            },
          }),
        ],
        "GET /strategy-watchlist": [
          ok({
            generated_at: TIMESTAMP,
            limit: 8,
            active_count: 1,
            normal_count: 1,
            streaming_count: 0,
            protective_count: 0,
            cap_exceeded_by_protective_coverage: false,
            instruments: [
              {
                instrument: "CS.D.EURUSD.MINI.IP",
                tier: "TIER1",
                status: "ACTIVE",
                asset_class: "FOREX",
                pinned: false,
                reason: "strategy_watchlist",
                reason_detail: {
                  code: "strategy_watchlist",
                  label: "Strategy watchlist",
                  operator_action: "Watchlisted for evaluation only; entry still depends on governance, risk, broker, and market-data gates.",
                },
                protective: false,
                priority_score: 1,
                requested_frequency: "1s",
                promotion_expires_at: null,
                last_streamed_at: null,
                last_refreshed_at: TIMESTAMP,
                streamed: false,
              },
            ],
          }),
          ok({
            generated_at: TIMESTAMP,
            limit: 8,
            active_count: 0,
            normal_count: 0,
            streaming_count: 0,
            protective_count: 0,
            cap_exceeded_by_protective_coverage: false,
            instruments: [],
          }),
        ],
        "GET /markets/overview": [
          ok({
            generatedAt: TIMESTAMP,
            summary: {
              category: "forex",
              label: "Forex",
              description: "Major FX instruments.",
              status: "OPEN",
              headline: "Forex open",
              detail: "Market overview available.",
              nextTransitionAt: "2026-05-17T17:00:00.000Z",
              nextTransitionLabel: "Close",
              tradableCount: 1,
              activeCount: 0,
              totalCount: 1,
            },
            instruments: [],
          }),
          ok({
            generatedAt: TIMESTAMP,
            summary: {
              category: "forex",
              label: "Forex",
              description: "Major FX instruments.",
              status: "OPEN",
              headline: "Forex open",
              detail: "Market overview available.",
              nextTransitionAt: "2026-05-17T17:00:00.000Z",
              nextTransitionLabel: "Close",
              tradableCount: 1,
              activeCount: 0,
              totalCount: 1,
            },
            instruments: [],
          }),
        ],
        "DELETE /strategy-watchlist/CS.D.EURUSD.MINI.IP": [
          delayed(
            response(503, {
              detail: "strategy watchlist removal failed because operator audit persistence is unavailable",
            }),
            400,
          ),
          delayed(
            ok({
              status: "removed",
              instrument: "CS.D.EURUSD.MINI.IP",
            }),
            400,
          ),
        ],
      });
    case "control-plane-mutation-refresh-failure":
      return mergeRoutes({
        "GET /control-plane/summary": [
          ok(baseControlPlaneSummary()),
          ok(baseControlPlaneSummary()),
          ok(baseControlPlaneSummary()),
          unavailable("control-plane refresh failed after operator control mutation"),
        ],
        "PUT /control-plane/operator-state": delayed(
          ok({
            configured_autonomous_control_enabled: true,
            effective_autonomous_control_enabled: false,
            override_active: true,
            override_value: false,
            override_reason: "Operator paused governed autonomy from the control plane.",
            updated_at: TIMESTAMP,
          }),
          400,
        ),
      });
    case "control-plane-arm-success":
      return mergeRoutes({
        "GET /control-plane/summary": [
          ok(
            baseControlPlaneSummary({
              autonomous_control_enabled: false,
              configured_autonomous_control_enabled: false,
              effective_autonomous_control_enabled: false,
            }),
          ),
          ok(
            baseControlPlaneSummary({
              autonomous_control_enabled: false,
              configured_autonomous_control_enabled: false,
              effective_autonomous_control_enabled: false,
            }),
          ),
          ok(
            baseControlPlaneSummary({
              autonomous_control_enabled: false,
              configured_autonomous_control_enabled: false,
              effective_autonomous_control_enabled: false,
            }),
          ),
          ok(baseControlPlaneSummary()),
        ],
        "PUT /control-plane/operator-state": delayed(
          ok({
            configured_autonomous_control_enabled: true,
            effective_autonomous_control_enabled: true,
            override_active: false,
            override_value: null,
            override_reason: null,
            updated_at: TIMESTAMP,
          }),
          400,
        ),
      });
    case "control-plane-arm-failure":
      return mergeRoutes({
        "GET /control-plane/summary": [
          ok(
            baseControlPlaneSummary({
              autonomous_control_enabled: false,
              configured_autonomous_control_enabled: false,
              effective_autonomous_control_enabled: false,
            }),
          ),
          ok(
            baseControlPlaneSummary({
              autonomous_control_enabled: false,
              configured_autonomous_control_enabled: false,
              effective_autonomous_control_enabled: false,
            }),
          ),
        ],
        "PUT /control-plane/operator-state": delayed(
          response(503, {
            detail: "operator control mutation audit persistence failed while arming governed autonomy",
          }),
          400,
        ),
      });
    case "control-plane-pause-success":
      return mergeRoutes({
        "GET /control-plane/summary": [
          ok(baseControlPlaneSummary()),
          ok(baseControlPlaneSummary()),
          ok(baseControlPlaneSummary()),
          ok(
            baseControlPlaneSummary({
              effective_autonomous_control_enabled: false,
              autonomy_override_active: true,
              autonomy_override_value: false,
              autonomy_override_reason: "Operator paused governed autonomy from the control plane.",
            }),
          ),
        ],
        "PUT /control-plane/operator-state": delayed(
          ok({
            configured_autonomous_control_enabled: true,
            effective_autonomous_control_enabled: false,
            override_active: true,
            override_value: false,
            override_reason: "Operator paused governed autonomy from the control plane.",
            updated_at: TIMESTAMP,
          }),
          400,
        ),
      });
    case "events-audit-degraded":
      return mergeRoutes({
        "GET /events": ok([
          baseEvent({
            id: 71,
            event_type: "health.audit_write_degraded",
            severity: "error",
            title: "Audit trail degraded",
            message: "Required audit writes are failing; operator evidence is degraded until persistence recovers.",
            source: "audit",
            correlation_id: "audit-71",
            runtime_id: "runtime-breakout-1",
            payload_json: {
              degradation_reasons: ["audit_write_degraded"],
              audit_write_failures_last_5m: 3,
            },
          }),
          baseEvent({
            id: 72,
            event_type: "execution.position_closed",
            category: "execution",
            severity: "warning",
            title: "Simulated local close kept distinct from broker-confirmed truth",
            message: "Local simulation recorded a close while broker confirmation remained unavailable.",
            strategy_name: "Breakout",
            instrument: "CS.D.EURUSD.MINI.IP",
            correlation_id: "close-sim-72",
            execution_id: 72,
            trade_id: 12,
            payload_json: {
              close_execution_source: "SIMULATED_LOCAL_CLOSE",
            },
          }),
          baseEvent({
            id: 73,
            event_type: "execution.position_closed",
            category: "execution",
            severity: "info",
            title: "Broker confirmed close",
            message: "Broker confirmation completed for the closing trade.",
            strategy_name: "Breakout",
            instrument: "CS.D.GBPUSD.MINI.IP",
            correlation_id: "close-broker-73",
            execution_id: 73,
            trade_id: 13,
            payload_json: {
              close_execution_source: "BROKER_CONFIRMED",
            },
          }),
        ]),
      });
    case "live-telemetry-degradations":
      return mergeRoutes({
        "GET /system/telemetry": ok(
          baseTelemetry({
            status: "degraded",
            last_audit_write_failure: "2026-05-17T09:58:30.000Z",
            last_audit_write_failure_age_ms: 90000,
            stream_connected: true,
            stream_last_tick_at: "2026-05-17T09:58:00.000Z",
            stream_last_tick_age_ms: 120000,
            feed_source_state: "STALE",
            feed_health_state: "DEGRADED",
            entry_eligible: false,
            entry_block_reason: "polling_fallback",
            audit_write_degraded: true,
            polling_fallback_active: true,
            polling_fallback_active_instrument_count: 2,
            stale_stream_instrument_count: 1,
            stream_degraded: true,
            runtime_degraded: true,
            degradation_reasons: [
              "audit_write_degraded",
              "polling_fallback_active",
              "stream_stale",
              "stream_degraded",
              "runtime_price_stale",
            ],
            stale_runtime_count: 1,
            stale_price_runtime_count: 1,
            audit_write_failures_last_5m: 3,
          }),
        ),
        "GET /health/stream": ok(
          baseStreamHealth({
            connected: true,
            last_tick_at: "2026-05-17T09:58:00.000Z",
            last_status: "Stale",
          }),
        ),
      });
    case "control-plane-governance-mutation-failure":
      return mergeRoutes({
        "PUT /control-plane/governance/Breakout": delayed(
          response(503, {
            detail: "governance mutation audit persistence failed for Breakout",
          }),
          400,
        ),
      });
    case "control-plane-governance-allow-success":
      return mergeRoutes({
        "GET /control-plane/summary": [
          ok(
            baseControlPlaneSummary({
              families: [
                baseFamily({
                  governance: {
                    ...baseFamily().governance,
                    autonomous_operation_allowed: false,
                  },
                }),
              ],
            }),
          ),
          ok(
            baseControlPlaneSummary({
              families: [
                baseFamily({
                  governance: {
                    ...baseFamily().governance,
                    autonomous_operation_allowed: false,
                  },
                }),
              ],
            }),
          ),
          ok(
            baseControlPlaneSummary({
              families: [
                baseFamily({
                  governance: {
                    ...baseFamily().governance,
                    autonomous_operation_allowed: false,
                  },
                }),
              ],
            }),
          ),
          ok(baseControlPlaneSummary()),
        ],
        "PUT /control-plane/governance/Breakout": delayed(
          ok({
            strategy_name: "Breakout",
            approval_state: "APPROVED",
            autonomous_operation_allowed: true,
            emergency_stop: false,
            approved_asset_classes: ["FOREX"],
            approved_instruments: ["CS.D.EURUSD.MINI.IP"],
            approved_profile_names: ["default"],
            max_concurrent_deployments: 1,
            notes: null,
            updated_at: TIMESTAMP,
          }),
          400,
        ),
      });
    case "control-plane-governance-allow-failure":
      return mergeRoutes({
        "GET /control-plane/summary": [
          ok(
            baseControlPlaneSummary({
              families: [
                baseFamily({
                  governance: {
                    ...baseFamily().governance,
                    autonomous_operation_allowed: false,
                  },
                }),
              ],
            }),
          ),
          ok(
            baseControlPlaneSummary({
              families: [
                baseFamily({
                  governance: {
                    ...baseFamily().governance,
                    autonomous_operation_allowed: false,
                  },
                }),
              ],
            }),
          ),
        ],
        "PUT /control-plane/governance/Breakout": delayed(
          response(503, {
            detail: "governance mutation audit persistence failed while allowing Breakout auto deploy",
          }),
          400,
        ),
      });
    case "control-plane-governance-disallow-success":
      return mergeRoutes({
        "GET /control-plane/summary": [
          ok(baseControlPlaneSummary()),
          ok(baseControlPlaneSummary()),
          ok(baseControlPlaneSummary()),
          ok(
            baseControlPlaneSummary({
              families: [
                baseFamily({
                  governance: {
                    ...baseFamily().governance,
                    autonomous_operation_allowed: false,
                  },
                }),
              ],
            }),
          ),
        ],
        "PUT /control-plane/governance/Breakout": delayed(
          ok({
            strategy_name: "Breakout",
            approval_state: "APPROVED",
            autonomous_operation_allowed: false,
            emergency_stop: false,
            approved_asset_classes: ["FOREX"],
            approved_instruments: ["CS.D.EURUSD.MINI.IP"],
            approved_profile_names: ["default"],
            max_concurrent_deployments: 1,
            notes: null,
            updated_at: TIMESTAMP,
          }),
          400,
        ),
      });
    case "strategies-entry-blocked-truth":
      return mergeRoutes({
        "GET /strategies": ok([
          baseStrategy({
            active_runtimes: [],
            open_positions: [],
          }),
        ]),
        "GET /executions": ok([
          baseExecution({
            id: 81,
            status: "RISK_REJECTED",
            broker_reference: null,
            reason: "stale_market_data blocked a new order attempt.",
            error_message: "stale_market_data blocked a new order attempt.",
            details: {
              direction: "BUY",
            },
          }),
          baseExecution({
            id: 82,
            status: "SUBMISSION_PENDING",
            broker_reference: null,
            reason: "Entry request is still pending broker submission.",
            details: {
              direction: "BUY",
            },
          }),
        ]),
      });
    case "coverage-stale-stream":
      return mergeRoutes({
        "GET /coverage/summary": ok(
          baseCoverageSummary({
            streaming: {
              active_instruments: [
                {
                  instrument: "CS.D.EURUSD.MINI.IP",
                  tier: "TIER1",
                  status: "ACTIVE",
                  asset_class: "FOREX",
                  pinned: false,
                  reason: "strategy_watchlist",
                  reason_detail: null,
                  protective: false,
                  priority_score: 1,
                  requested_frequency: "1s",
                  promotion_expires_at: null,
                  last_streamed_at: TIMESTAMP,
                  last_refreshed_at: TIMESTAMP,
                  streamed: true,
                },
              ],
              execution_readiness: [
                {
                  instrument: "CS.D.EURUSD.MINI.IP",
                  is_ok: false,
                  market_open: true,
                  tradable: true,
                  quote_fresh: false,
                  spread_ok: true,
                  session_valid: true,
                  dealing_allowed: true,
                  last_price_age_ms: 92000,
                  spread: null,
                  reason: "stale_market_data",
                },
              ],
              desired_instruments: ["CS.D.EURUSD.MINI.IP"],
              pinned_instruments: [],
              capped_instruments: [],
              asset_class_usage: {},
            },
          }),
        ),
        "GET /system/telemetry": ok(
          baseTelemetry({
            status: "degraded",
            stream_connected: true,
            stream_last_tick_at: "2026-05-17T09:58:00.000Z",
            stream_last_tick_age_ms: 92000,
            feed_source_state: "STALE",
            feed_health_state: "DEGRADED",
            entry_eligible: false,
            entry_block_reason: "stale_market_data",
            stale_stream_instrument_count: 1,
            stream_degraded: true,
            degradation_reasons: ["stream_stale", "stream_degraded"],
          }),
        ),
        "GET /control-plane/summary": ok(
          baseControlPlaneSummary({
            feed_source_state: "STALE",
            feed_health_state: "DEGRADED",
            entry_eligible: false,
            entry_block_reason: "stale_market_data",
          }),
        ),
        "GET /health/stream": ok(
          baseStreamHealth({
            connected: true,
            last_tick_at: "2026-05-17T09:58:00.000Z",
            last_status: "Stale",
          }),
        ),
        "GET /market-data/feed-state": ok({
          generated_at: TIMESTAMP,
          instruments: [
            {
              instrument: "CS.D.EURUSD.MINI.IP",
              stream_status: "STALE",
              stream_connected: true,
              stream_enabled: true,
              streaming_now: true,
              desired: true,
              capped: false,
              last_tick_at: "2026-05-17T09:58:00.000Z",
              last_tick_age_ms: 92000,
              spread: null,
              price_source: "STREAM",
              stream_reason: {
                code: "stale_market_data",
                label: "Stale",
                operator_action: "The latest live tick is stale and should not be treated as fresh stream truth.",
              },
              market_status: null,
              market_error: null,
              entry_eligibility: "BLOCKED",
              entry_eligibility_reason: {
                code: "stale_market_data",
                label: "Stale market data",
                operator_action: "Entry is blocked until fresh live ticks return.",
              },
              strategies_may_evaluate: false,
              active_strategy_runtime_count: 1,
              watchlist_entry: null,
            },
          ],
        }),
      });
    case "coverage-disconnected-stream":
      return mergeRoutes({
        "GET /coverage/summary": ok(
          baseCoverageSummary({
            streaming: {
              active_instruments: [
                {
                  instrument: "CS.D.EURUSD.MINI.IP",
                  tier: "TIER1",
                  status: "ACTIVE",
                  asset_class: "FOREX",
                  pinned: false,
                  reason: "strategy_watchlist",
                  reason_detail: null,
                  protective: false,
                  priority_score: 1,
                  requested_frequency: "1s",
                  promotion_expires_at: null,
                  last_streamed_at: TIMESTAMP,
                  last_refreshed_at: TIMESTAMP,
                  streamed: true,
                },
              ],
              execution_readiness: [
                {
                  instrument: "CS.D.EURUSD.MINI.IP",
                  is_ok: false,
                  market_open: true,
                  tradable: true,
                  quote_fresh: false,
                  spread_ok: true,
                  session_valid: false,
                  dealing_allowed: false,
                  last_price_age_ms: null,
                  spread: null,
                  reason: "stream_disconnected",
                },
              ],
              desired_instruments: ["CS.D.EURUSD.MINI.IP"],
              pinned_instruments: [],
              capped_instruments: [],
              asset_class_usage: {},
            },
          }),
        ),
        "GET /system/telemetry": ok(
          baseTelemetry({
            status: "degraded",
            stream_connected: false,
            stream_last_tick_at: null,
            stream_last_tick_age_ms: null,
            feed_source_state: "DISCONNECTED",
            feed_health_state: "FAILED",
            entry_eligible: false,
            entry_block_reason: "stream_disconnected",
            stale_stream_instrument_count: 0,
            stream_degraded: true,
            degradation_reasons: ["stream_disconnected"],
          }),
        ),
        "GET /control-plane/summary": ok(
          baseControlPlaneSummary({
            feed_source_state: "DISCONNECTED",
            feed_health_state: "FAILED",
            entry_eligible: false,
            entry_block_reason: "stream_disconnected",
          }),
        ),
        "GET /health/stream": ok(
          baseStreamHealth({
            connected: false,
            dependency_ready: false,
            last_tick_at: null,
            last_status: "Disconnected",
            last_error: "stream unavailable",
          }),
        ),
        "GET /market-data/feed-state": ok({
          generated_at: TIMESTAMP,
          instruments: [
            {
              instrument: "CS.D.EURUSD.MINI.IP",
              stream_status: "DISCONNECTED",
              stream_connected: false,
              stream_enabled: true,
              streaming_now: false,
              desired: true,
              capped: false,
              last_tick_at: null,
              last_tick_age_ms: null,
              spread: null,
              price_source: "UNAVAILABLE",
              stream_reason: {
                code: "stream_disconnected",
                label: "Disconnected",
                operator_action: "Live stream is disconnected or unavailable for this instrument.",
              },
              market_status: null,
              market_error: "stream unavailable",
              entry_eligibility: "BLOCKED",
              entry_eligibility_reason: {
                code: "stream_disconnected",
                label: "Disconnected",
                operator_action: "Entry is blocked until stream connectivity returns.",
              },
              strategies_may_evaluate: false,
              active_strategy_runtime_count: 1,
              watchlist_entry: null,
            },
          ],
        }),
      });
    case "coverage-stream-recovered":
      return mergeRoutes({
        "GET /coverage/summary": ok(
          baseCoverageSummary({
            streaming: {
              active_instruments: [
                {
                  instrument: "CS.D.EURUSD.MINI.IP",
                  tier: "TIER1",
                  status: "ACTIVE",
                  asset_class: "FOREX",
                  pinned: false,
                  reason: "strategy_watchlist",
                  reason_detail: null,
                  protective: false,
                  priority_score: 1,
                  requested_frequency: "1s",
                  promotion_expires_at: null,
                  last_streamed_at: TIMESTAMP,
                  last_refreshed_at: TIMESTAMP,
                  streamed: true,
                },
              ],
              execution_readiness: [
                {
                  instrument: "CS.D.EURUSD.MINI.IP",
                  is_ok: true,
                  market_open: true,
                  tradable: true,
                  quote_fresh: true,
                  spread_ok: true,
                  session_valid: true,
                  dealing_allowed: true,
                  last_price_age_ms: 1400,
                  spread: 0.8,
                  reason: null,
                },
              ],
              desired_instruments: ["CS.D.EURUSD.MINI.IP"],
              pinned_instruments: [],
              capped_instruments: [],
              asset_class_usage: {},
            },
          }),
        ),
        "GET /system/telemetry": ok(
          baseTelemetry({
            status: "ok",
            stream_connected: true,
            stream_last_tick_at: TIMESTAMP,
            stream_last_tick_age_ms: 1400,
            feed_source_state: "LIVE",
            feed_health_state: "HEALTHY",
            degradation_reasons: [],
          }),
        ),
        "GET /health/stream": ok(
          baseStreamHealth({
            connected: true,
            last_tick_at: TIMESTAMP,
            last_status: "Recovered after stream disconnect",
          }),
        ),
        "GET /market-data/feed-state": ok({
          generated_at: TIMESTAMP,
          instruments: [
            {
              instrument: "CS.D.EURUSD.MINI.IP",
              stream_status: "CONNECTED",
              stream_connected: true,
              stream_enabled: true,
              streaming_now: true,
              desired: true,
              capped: false,
              last_tick_at: TIMESTAMP,
              last_tick_age_ms: 1400,
              spread: 0.8,
              price_source: "STREAM",
              stream_reason: {
                code: "stream_recovered",
                label: "Recovered",
                operator_action: "Live stream recovered after degradation; confirm fresh ticks continue before treating the path as stable.",
              },
              market_status: null,
              market_error: null,
              entry_eligibility: "OK",
              entry_eligibility_reason: {
                code: "recovered_stream",
                label: "Recovered",
                operator_action: "Stream truth recovered, but continue watching freshness and spread stability.",
              },
              strategies_may_evaluate: true,
              active_strategy_runtime_count: 1,
              watchlist_entry: null,
            },
          ],
        }),
      });
    case "coverage-unknown-freshness":
      return mergeRoutes({
        "GET /coverage/summary": ok(
          baseCoverageSummary({
            streaming: {
              active_instruments: [
                {
                  instrument: "CS.D.EURUSD.MINI.IP",
                  tier: "TIER1",
                  status: "ACTIVE",
                  asset_class: "FOREX",
                  pinned: false,
                  reason: "strategy_watchlist",
                  reason_detail: null,
                  protective: false,
                  priority_score: 1,
                  requested_frequency: "1s",
                  promotion_expires_at: null,
                  last_streamed_at: null,
                  last_refreshed_at: TIMESTAMP,
                  streamed: true,
                },
              ],
              execution_readiness: [
                {
                  instrument: "CS.D.EURUSD.MINI.IP",
                  is_ok: false,
                  market_open: true,
                  tradable: true,
                  quote_fresh: false,
                  spread_ok: true,
                  session_valid: true,
                  dealing_allowed: true,
                  last_price_age_ms: 0,
                  spread: null,
                  reason: "unknown_tick_time",
                },
              ],
              desired_instruments: ["CS.D.EURUSD.MINI.IP"],
              pinned_instruments: [],
              capped_instruments: [],
              asset_class_usage: {},
            },
          }),
        ),
        "GET /health/stream": ok(
          baseStreamHealth({
            connected: true,
            last_tick_at: null,
            last_status: "Tick timestamp unavailable",
          }),
        ),
        "GET /market-data/feed-state": ok({
          generated_at: TIMESTAMP,
          instruments: [
            {
              instrument: "CS.D.EURUSD.MINI.IP",
              stream_status: "streaming",
              stream_reason: {
                code: "unknown_tick_time",
                label: "Stream state unknown",
                operator_action: "Stream coverage exists, but the latest tick timestamp is unavailable.",
              },
              stream_connected: true,
              stream_enabled: true,
              streaming_now: true,
              desired: true,
              capped: false,
              last_tick_at: null,
              last_tick_age_ms: null,
              spread: 1.1,
              price_source: "STREAM",
              market_status: null,
              market_error: null,
              entry_eligibility: "UNKNOWN",
              entry_eligibility_reason: {
                code: "unknown_tick_time",
                label: "Unknown freshness",
                operator_action: "Freshness is unknown; do not treat this instrument as healthy live stream truth.",
              },
              strategies_may_evaluate: false,
              active_strategy_runtime_count: 0,
              watchlist_entry: null,
            },
          ],
        }),
      });
    case "dashboard-positions-sync-unknown":
      return mergeRoutes({
        "GET /trades/positions": ok([
          basePosition({
            id: 301,
            broker_reference: null,
            broker_sync_status: "UNAVAILABLE",
            reason: "Broker reference is unavailable and sync truth is degraded.",
          }),
          basePosition({
            id: 302,
            instrument: "CS.D.GBPUSD.MINI.IP",
            broker_reference: safeIdentifier("BRK…UNK-302", "fp-unk-302"),
            broker_sync_status: "UNKNOWN",
            risk_truth_confidence: "UNKNOWN",
            reason: "Broker sync truth is unknown and still requires operator correlation.",
          }),
        ]),
      });
    case "dashboard-activity-simulated-close":
      return mergeRoutes({
        "GET /executions": ok([
          baseExecution({
            id: 311,
            phase: "CLOSE",
            status: "CLOSE_CONFIRMED",
            broker_reference: safeIdentifier("CLS…SIM-311", "fp-sim-close-311"),
            reason: "Local simulated close remains distinct from broker-confirmed close truth.",
            details: {
              close_execution_source: "SIMULATED_LOCAL_CLOSE",
            },
          }),
          baseExecution({
            id: 312,
            phase: "CLOSE",
            status: "CLOSE_CONFIRMED",
            broker_reference: safeIdentifier("CLS…BRK-312", "fp-brk-close-312"),
            reason: "Broker-confirmed close is preserved separately.",
            details: {
              close_execution_source: "BROKER_CONFIRMED",
            },
          }),
        ]),
      });
    case "strategies-partial-close-open-risk":
      return mergeRoutes({
        "GET /strategies": ok([
          baseStrategy({
            status: "STOPPED",
            current_pnl: 0,
            last_price: 1.09,
            price_status: "POSITION",
            active_instruments: [],
            active_runtime_count: 0,
            open_position_count: 1,
            active_runtimes: [],
            open_positions: [
              {
                broker_reference: safeIdentifier("BRK…PCL-21", "fp-pcl-21"),
                instrument: "CS.D.EURUSD.MINI.IP",
                direction: "BUY",
                size: 0.4,
                open_price: 1.08,
                current_price: 1.09,
                unrealized_pnl: 14,
                risk_percent: 0.45,
              },
            ],
            persisted_runtimes: [
              {
                runtime_id: safeIdentifier("run…partial-21", "fp-run-partial-21"),
                instrument: "CS.D.EURUSD.MINI.IP",
                status: "STOPPED",
                recovery_state: "PAUSED",
                recovery_reason: "Partial close left remaining broker risk live until reconciliation completes.",
                control_mode: "MANUAL",
                runtime_mode: "STOPPED",
                parameters: {},
              },
            ],
          }),
        ]),
        "GET /executions": ok([
          baseExecution({
            id: 321,
            phase: "CLOSE",
            status: "FILL_PARTIAL",
            requires_manual_review: true,
            broker_reference: safeIdentifier("CLS…PCL-21", "fp-close-partial-21"),
            reason: "Close partially filled; remaining open risk stays live until broker reconciliation completes.",
            error_message: "Close partially filled; remaining open risk stays live until broker reconciliation completes.",
            details: {
              close_execution_source: "BROKER_CONFIRMED",
            },
          }),
        ]),
      });
    case "events-lifecycle-provenance":
      return mergeRoutes({
        "GET /events": ok([
          baseEvent({
            id: 401,
            event_type: "reconciliation.position_corrected",
            category: "risk",
            severity: "warning",
            title: "Recovered position attached",
            message: "Recovered broker-confirmed open risk was reattached during startup recovery.",
            source: "runtime_recovery",
            strategy_name: "Breakout",
            instrument: "CS.D.EURUSD.MINI.IP",
            correlation_id: safeIdentifier("corr…rcv-401", "fp-corr-401"),
            runtime_id: safeIdentifier("run…rcv-401", "fp-runtime-401"),
            position_id: 71,
            trade_id: 71,
            execution_id: 171,
            payload_json: {
              previous_state: "SUBMITTED",
              new_state: "RECOVERED_POSITION_ATTACHED",
              execution_source: "BROKER_CONFIRMED",
              open_risk_management_state: "MANAGED",
              broker_reference: safeIdentifier("BRK…RCV-401", "fp-broker-401"),
              client_request_id: safeIdentifier("req…RCV-401", "fp-request-401"),
              account_id: safeIdentifier("acct…401", "fp-account-401"),
              reason: "Recovered broker-confirmed open risk remains live after restart.",
            },
          }),
          baseEvent({
            id: 402,
            event_type: "reconciliation.unmatched_remote_position",
            category: "risk",
            severity: "warning",
            title: "External position adopted",
            message: "Adopted external broker position remains open until local lifecycle catches up.",
            source: "reconciliation",
            strategy_name: "Breakout",
            instrument: "CS.D.GBPUSD.MINI.IP",
            correlation_id: safeIdentifier("corr…adp-402", "fp-corr-402"),
            runtime_id: safeIdentifier("run…adp-402", "fp-runtime-402"),
            position_id: 72,
            trade_id: 72,
            execution_id: 172,
            payload_json: {
              previous_state: "APPROVED",
              new_state: "EXTERNAL_POSITION_ADOPTED",
              open_risk_management_state: "UNMANAGED_OPEN_RISK",
              broker_reference: safeIdentifier("BRK…ADP-402", "fp-broker-402"),
              client_request_id: safeIdentifier("req…ADP-402", "fp-request-402"),
              account_id: safeIdentifier("acct…402", "fp-account-402"),
              reason: "Broker position was adopted during reconciliation rather than opened by normal strategy entry.",
            },
          }),
        ]),
      });
    case "events-close-open-risk-truth":
      return mergeRoutes({
        "GET /events": ok([
          baseEvent({
            id: 411,
            event_type: "execution.fill_received",
            category: "execution",
            severity: "warning",
            title: "Partial close keeps remaining open risk live",
            message: "Close partially filled; remaining open risk stays live until broker reconciliation completes.",
            source: "execution",
            strategy_name: "Breakout",
            instrument: "CS.D.EURUSD.MINI.IP",
            correlation_id: safeIdentifier("corr…pcl-411", "fp-corr-411"),
            runtime_id: safeIdentifier("run…pcl-411", "fp-runtime-411"),
            position_id: 21,
            trade_id: 21,
            execution_id: 321,
            payload_json: {
              previous_state: "CLOSE_REQUESTED",
              new_state: "FILL_PARTIAL",
              close_execution_source: "BROKER_CONFIRMED",
              open_risk_management_state: "EXITS_ONLY",
              close_broker_reference: safeIdentifier("CLS…PCL-411", "fp-close-411"),
              client_request_id: safeIdentifier("req…PCL-411", "fp-request-411"),
              error_message: "Close partially filled; remaining open risk stays live until broker reconciliation completes.",
            },
          }),
          baseEvent({
            id: 412,
            event_type: "execution.order_rejected",
            category: "execution",
            severity: "error",
            title: "Failed close left open risk live",
            message: "Close rejected by broker; position remains open and requires manual review.",
            source: "execution",
            strategy_name: "Breakout",
            instrument: "CS.D.EURUSD.MINI.IP",
            correlation_id: safeIdentifier("corr…fcl-412", "fp-corr-412"),
            runtime_id: safeIdentifier("run…fcl-412", "fp-runtime-412"),
            position_id: 22,
            trade_id: 22,
            execution_id: 322,
            payload_json: {
              previous_state: "CLOSE_REQUESTED",
              new_state: "FAILED",
              close_execution_source: "BROKER_CONFIRMED",
              open_risk_management_state: "UNMANAGED_OPEN_RISK",
              close_broker_reference: safeIdentifier("CLS…FCL-412", "fp-close-412"),
              client_request_id: safeIdentifier("req…FCL-412", "fp-request-412"),
              error_message: "Close rejected by broker; position remains open and requires manual review.",
            },
          }),
          baseEvent({
            id: 413,
            event_type: "execution.retry_suppressed",
            category: "execution",
            severity: "warning",
            title: "Ambiguous close requires manual review",
            message: "Broker close confirmation timed out; close remains ambiguous and requires manual review.",
            source: "execution",
            strategy_name: "Breakout",
            instrument: "CS.D.EURUSD.MINI.IP",
            correlation_id: safeIdentifier("corr…mrv-413", "fp-corr-413"),
            runtime_id: safeIdentifier("run…mrv-413", "fp-runtime-413"),
            position_id: 23,
            trade_id: 23,
            execution_id: 323,
            payload_json: {
              previous_state: "ORDER_SUBMITTED",
              new_state: "NEEDS_MANUAL_REVIEW",
              close_execution_source: "BROKER_CONFIRMED",
              open_risk_management_state: "UNMANAGED_OPEN_RISK",
              close_broker_reference: safeIdentifier("CLS…MRV-413", "fp-close-413"),
              client_request_id: safeIdentifier("req…MRV-413", "fp-request-413"),
              error_message: "Broker close confirmation timed out; close remains ambiguous and requires manual review.",
            },
          }),
        ]),
      });
    case "events-runtime-stopped-open-risk":
      return mergeRoutes({
        "GET /events": ok([
          baseEvent({
            id: 421,
            event_type: "strategy.runtime_stopped",
            category: "strategy",
            severity: "warning",
            title: "Runtime stopped while open risk remained live",
            message: "Stopping this runtime does not close broker-confirmed open risk.",
            source: "operator",
            strategy_name: "Breakout",
            instrument: "CS.D.EURUSD.MINI.IP",
            correlation_id: safeIdentifier("corr…stp-421", "fp-corr-421"),
            runtime_id: safeIdentifier("run…stp-421", "fp-runtime-421"),
            position_id: 24,
            payload_json: {
              control_mode: "MANUAL",
              new_runtime_mode: "STOPPED",
              new_open_risk_management_state: "EXITS_ONLY",
              broker_reference: safeIdentifier("BRK…STP-421", "fp-broker-421"),
              stop_context: {
                detail: "Operator requested runtime stop while broker-confirmed open risk remained live.",
              },
            },
          }),
        ]),
      });
    case "live-unsupported-feed-state":
      return mergeRoutes({
        "GET /control-plane/summary": ok(
          baseControlPlaneSummary({
            feed_source_state: "BROKER_MAGIC",
            feed_health_state: "DEGRADED",
            entry_eligible: false,
            entry_block_reason: "unsupported_feed_state",
          }),
        ),
        "GET /system/telemetry": ok(
          baseTelemetry({
            status: "degraded",
            feed_source_state: "BROKER_MAGIC",
            feed_health_state: "DEGRADED",
            entry_eligible: false,
            entry_block_reason: "unsupported_feed_state",
          }),
        ),
        "GET /health/stream": ok(
          baseStreamHealth({
            connected: true,
            last_tick_at: TIMESTAMP,
            last_status: "Backend returned unsupported feed state",
          }),
        ),
      });
    case "strategies-close-failed-open-risk":
      return mergeRoutes({
        "GET /strategies": ok([
          baseStrategy({
            status: "STOPPED",
            current_pnl: 0,
            last_price: 1.09,
            price_status: "POSITION",
            active_instruments: [],
            active_runtime_count: 0,
            open_position_count: 1,
            active_runtimes: [],
            open_positions: [
              {
                broker_reference: safeIdentifier("BRK…FCL-22", "fp-fcl-22"),
                instrument: "CS.D.EURUSD.MINI.IP",
                direction: "BUY",
                size: 1,
                open_price: 1.08,
                current_price: 1.09,
                unrealized_pnl: 12,
                risk_percent: 1.05,
              },
            ],
            persisted_runtimes: [
              {
                runtime_id: safeIdentifier("run…failed-22", "fp-run-failed-22"),
                instrument: "CS.D.EURUSD.MINI.IP",
                status: "STOPPED",
                recovery_state: "PAUSED",
                recovery_reason: "Failed close left broker-confirmed open risk live and awaiting manual review.",
                control_mode: "MANUAL",
                runtime_mode: "STOPPED",
                parameters: {},
              },
            ],
          }),
        ]),
        "GET /executions": ok([
          baseExecution({
            id: 322,
            phase: "CLOSE",
            status: "FAILED",
            requires_manual_review: true,
            broker_reference: safeIdentifier("CLS…FAIL-22", "fp-close-fail-22"),
            reason: "Close rejected by broker; position remains open and requires manual review.",
            error_message: "Close rejected by broker; position remains open and requires manual review.",
            details: {
              close_execution_source: "BROKER_CONFIRMED",
            },
          }),
        ]),
      });
    case "risk-alert-acknowledge-confirmed":
      return mergeRoutes({
        "GET /allocation/alerts": [
          ok([baseAlert()]),
          ok([baseAlert()]),
          ok([
            baseAlert({
              state: "ACKNOWLEDGED",
              acknowledged_at: TIMESTAMP,
            }),
          ]),
        ],
        "POST /allocation/alerts/5/acknowledge": delayed(
          ok({
            id: 5,
            state: "ACKNOWLEDGED",
            acknowledged_at: TIMESTAMP,
          }),
          400,
        ),
      });
    default:
      return mergeRoutes({});
  }
}
