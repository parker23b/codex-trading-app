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

function baseTelemetry(overrides = {}) {
  return {
    status: "ok",
    last_heartbeat: TIMESTAMP,
    heartbeat_age_ms: 2000,
    last_price_update: TIMESTAMP,
    last_price_age_ms: 1200,
    last_reconciliation: TIMESTAMP,
    last_reconciliation_age_ms: 5400,
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
    broker_latency_ms: 48,
    runtime_count: 1,
    active_runtime_count: 1,
    stale_runtime_count: 0,
    stale_price_runtime_count: 0,
    reconciliation_mismatches: 0,
    order_failures_last_5m: 0,
    rejected_orders_last_5m: 0,
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
                broker_reference: "BROKER-OPEN-2",
                direction: "BUY",
                current_price: 1.09,
                unrealized_pnl: 35,
              },
            ],
            open_positions: [
              basePosition({
                broker_reference: "BROKER-OPEN-2",
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
                  status: "MISALIGNED",
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
    default:
      return mergeRoutes({});
  }
}
