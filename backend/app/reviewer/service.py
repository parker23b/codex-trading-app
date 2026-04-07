from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from statistics import mean
from typing import Any

from sqlmodel import Session, desc, select

from app.core.config import get_settings
from app.models.review import GeneratedReviewRecord
from app.models.trade import Execution, ExecutionStatus, ReconciliationEvent, Trade
from app.reviewer.llm import ReviewLLMRequest, get_review_llm_client
from app.reviewer.models import (
    AIReviewProvenance,
    AIReviewSummary,
    DailyReviewFacts,
    DailyReviewResponse,
    ExposureFact,
    ObservationMetric,
    OperationalQuestionFacts,
    OperationalQuestionReviewResponse,
    OperatorSummaryFacts,
    OperatorSummaryReview,
    PersistedReviewRecord,
    PossibleContributor,
    ReviewMetadata,
    ReviewObservation,
    ReviewRecordSummary,
    ReviewSourceCoverage,
    ReviewWarning,
    RuntimeHealthFacts,
    RuntimeHealthReviewResponse,
    RuntimeIssueFact,
    StrategyHealthFact,
    StrategyReviewFacts,
    StrategyReviewResponse,
    SupportingMetric,
    TradeClusterPattern,
    TradePostMortemFacts,
    TradePostMortemReviewResponse,
    ReviewType,
)
from app.reviewer.prompts import PROMPT_VERSION, build_review_prompts
from app.services.dashboard_service import DashboardService
from app.services.ig_streaming_service import get_ig_streaming_service
from app.services.runtime_state_service import RuntimeStateService
from app.services.trade_service import TradeService


class AIReviewerService:
    def __init__(self, session: Session):
        self.session = session
        self.settings = get_settings()
        self.trade_service = TradeService(session)
        self.runtime_state_service = RuntimeStateService(session)
        self.dashboard_service = DashboardService(self.trade_service)
        self.stream_service = get_ig_streaming_service()
        self.llm_client = get_review_llm_client()

    def get_operator_summary(self) -> OperatorSummaryReview:
        now = self._utc_datetime(datetime.now(UTC))
        since = now - timedelta(hours=24)
        trades = self.trade_service.list_trades(date_from=since)
        positions = self.trade_service.list_positions()
        executions = self.trade_service.list_executions(limit=250)
        runtimes = self.runtime_state_service.list_runtimes()
        recon_events = self.trade_service.list_reconciliation_events(date_from=since)
        stream_health = self.stream_service.get_health()
        dashboard = self.dashboard_service.get_dashboard()
        previous = self._latest_review_record("operator_summary")

        total_open_risk = sum(position.risk_percent or 0.0 for position in positions)
        ranked_positions = sorted(positions, key=lambda position: position.risk_percent or 0.0, reverse=True)
        top_risk_exposures = [
            ExposureFact(
                strategy_name=position.strategy_name,
                instrument=position.instrument,
                direction=position.direction,
                risk_percent=round(position.risk_percent or 0.0, 2),
                unrealized_pnl=round(position.unrealized_pnl or 0.0, 2),
                notional_estimate=round((position.current_price or position.open_price) * position.size, 2),
                share_of_open_risk_percent=round(((position.risk_percent or 0.0) / total_open_risk) * 100, 2) if total_open_risk else 0.0,
            )
            for position in ranked_positions[:3]
        ]
        stale_runtimes = self._stale_runtimes(runtimes, now)
        baseline_open_risk = self._previous_fact(previous, "open_risk_percent")
        baseline_largest_share = self._previous_fact(previous, "largest_risk_share_percent")
        baseline_trade_count = self._rolling_trade_count_baseline(now, windows=5, window_days=1)
        baseline_win_rate = self._rolling_win_rate_baseline(now, windows=5, window_days=1)
        strategy_trade_groups = self._group_trades_by_strategy(trades)
        largest_share = top_risk_exposures[0].share_of_open_risk_percent if top_risk_exposures else 0.0

        facts = OperatorSummaryFacts(
            account_value=self._float_or_none(dashboard.get("accountValue")),
            account_value_change_percent=self._float_or_none(dashboard.get("accountValuePercent")),
            daily_pnl=float(dashboard.get("dailyPnl", 0.0)),
            daily_pnl_percent=self._float_or_none(dashboard.get("dailyPnlPercent")),
            open_risk_percent=float(dashboard.get("openRisk", 0.0)),
            open_positions_count=len(positions),
            active_runtimes=len([runtime for runtime in runtimes if runtime.status == "RUNNING"]),
            main_open_risk=top_risk_exposures[0] if top_risk_exposures else None,
            largest_risk_share_percent=round(largest_share, 2),
            top_risk_exposures=top_risk_exposures,
            strategy_health=[
                StrategyHealthFact(
                    strategy_name=strategy_name,
                    status="RUNNING" if any(runtime.strategy_name == strategy_name and runtime.status == "RUNNING" for runtime in runtimes) else "STOPPED",
                    active_runtime_count=len([runtime for runtime in runtimes if runtime.strategy_name == strategy_name and runtime.status == "RUNNING"]),
                    open_position_count=len([position for position in positions if position.strategy_name == strategy_name]),
                    trade_count_24h=len(strategy_trades),
                    pnl_24h=round(sum(trade.pnl for trade in strategy_trades), 2),
                    win_rate_24h=self._win_rate(strategy_trades),
                    stale_runtime_count=len([runtime for runtime in stale_runtimes if runtime.strategy_name == strategy_name]),
                )
                for strategy_name, strategy_trades in sorted(strategy_trade_groups.items())
            ],
            risk_rejections_24h=len([execution for execution in executions if self._is_since(execution.last_transition_at, since) and execution.status == ExecutionStatus.RISK_REJECTED.value]),
            execution_failures_24h=len([execution for execution in executions if self._is_since(execution.last_transition_at, since) and execution.status in {ExecutionStatus.FAILED.value, ExecutionStatus.NEEDS_MANUAL_REVIEW.value}]),
            reconciliation_issues_24h=len(self._reconciliation_issues(recon_events)),
            stale_runtimes=len(stale_runtimes),
            stream_connected=stream_health.connected if stream_health.enabled else None,
            stream_last_tick_at=stream_health.last_tick_at,
            baseline_open_risk_percent=baseline_open_risk,
            baseline_largest_risk_share_percent=baseline_largest_share,
            baseline_trade_count_24h=baseline_trade_count,
            baseline_win_rate_24h=baseline_win_rate,
        )

        supporting_metrics = [
            self._metric("daily_pnl", "Daily PnL", facts.daily_pnl, unit="ccy"),
            self._metric("open_risk_percent", "Open Risk", facts.open_risk_percent, unit="pct", baseline=facts.baseline_open_risk_percent),
            self._metric("largest_risk_share_percent", "Largest Risk Share", facts.largest_risk_share_percent, unit="pct", baseline=facts.baseline_largest_risk_share_percent),
            self._metric("trade_count_24h", "Trade Count (24h)", len(trades), baseline=facts.baseline_trade_count_24h),
            self._metric("win_rate_24h", "Win Rate (24h)", self._win_rate(trades), unit="pct", baseline=facts.baseline_win_rate_24h),
            self._metric("stale_runtimes", "Stale Runtimes", facts.stale_runtimes),
        ]
        derived_observations = self._operator_observations(facts, trades, executions, recon_events, stale_runtimes, now)
        possible_contributors = self._operator_contributors(facts, executions, stale_runtimes, stream_health)
        warnings = self._default_warnings(stream_health=stream_health, stale_runtimes=len(stale_runtimes))

        response = OperatorSummaryReview(
            metadata=self._metadata("operator_summary", now, since, now, {"window": "24h"}),
            facts=facts,
            derived_observations=derived_observations,
            possible_contributors=possible_contributors,
            warnings=warnings,
            supporting_metrics=supporting_metrics,
        )
        return self._finalize_review(response)

    def get_daily_review(self, review_date: date) -> DailyReviewResponse:
        start = self._utc_datetime(datetime.combine(review_date, time.min, tzinfo=UTC))
        end = self._utc_datetime(datetime.combine(review_date, time.max, tzinfo=UTC))
        previous_start = start - timedelta(days=5)
        previous_end = start - timedelta(seconds=1)
        trades = self.trade_service.list_trades(date_from=start, date_to=end)
        baseline_trades = self.trade_service.list_trades(date_from=previous_start, date_to=previous_end)
        positions = self.trade_service.list_positions()
        executions = self.trade_service.list_executions(limit=500)
        runtimes = self.runtime_state_service.list_runtimes()
        recon_events = self.trade_service.list_reconciliation_events(date_from=start, date_to=end)
        risk_rejections = [execution for execution in executions if self._in_period(execution.last_transition_at, start, end) and execution.status == ExecutionStatus.RISK_REJECTED.value]
        failures = [execution for execution in executions if self._in_period(execution.last_transition_at, start, end) and execution.status in {ExecutionStatus.FAILED.value, ExecutionStatus.NEEDS_MANUAL_REVIEW.value}]
        runtime_issues = [runtime for runtime in self._stale_runtimes(runtimes, end) if self._in_period(runtime.updated_at, start, end)]
        facts = DailyReviewFacts(
            review_date=review_date,
            strategies_ran=sorted({trade.strategy_name for trade in trades} | {runtime.strategy_name for runtime in runtimes if self._in_period(runtime.updated_at, start, end)}),
            active_instruments=sorted({trade.instrument for trade in trades} | {runtime.instrument for runtime in runtimes if self._in_period(runtime.updated_at, start, end)}),
            trade_count=len(trades),
            win_count=len([trade for trade in trades if trade.pnl > 0]),
            loss_count=len([trade for trade in trades if trade.pnl < 0]),
            realised_pnl=round(sum(trade.pnl for trade in trades), 2),
            unrealised_pnl=round(sum(position.unrealized_pnl or 0.0 for position in positions), 2),
            risk_rejections=len(risk_rejections),
            risk_rejections_by_rule=self._risk_rejection_breakdown(risk_rejections),
            execution_failures=len(failures),
            runtime_health_issues=len(runtime_issues),
            reconciliation_issues=len(self._reconciliation_issues(recon_events)),
            baseline_trade_count=round(len(baseline_trades) / 5, 2) if baseline_trades else None,
            baseline_realised_pnl=round(sum(trade.pnl for trade in baseline_trades) / 5, 2) if baseline_trades else None,
            baseline_win_rate=self._win_rate(baseline_trades),
        )
        response = DailyReviewResponse(
            metadata=self._metadata("daily_review", end, start, end, {"date": review_date.isoformat()}, requested_date=review_date),
            facts=facts,
            derived_observations=self._daily_observations(facts, failures, recon_events),
            possible_contributors=self._daily_contributors(facts, failures, risk_rejections, runtime_issues),
            warnings=self._default_warnings(stream_health=self.stream_service.get_health(), stale_runtimes=len(runtime_issues)),
            supporting_metrics=[
                self._metric("trade_count", "Trades", facts.trade_count, baseline=facts.baseline_trade_count),
                self._metric("realised_pnl", "Realised PnL", facts.realised_pnl, unit="ccy", baseline=facts.baseline_realised_pnl),
                self._metric("win_rate", "Win Rate", self._win_rate(trades), unit="pct", baseline=facts.baseline_win_rate),
                self._metric("risk_rejections", "Risk Rejections", facts.risk_rejections),
            ],
        )
        return self._finalize_review(response)

    def get_strategy_review(self, strategy_name: str, period_days: int = 7) -> StrategyReviewResponse:
        now = self._utc_datetime(datetime.now(UTC))
        start = now - timedelta(days=period_days)
        previous_start = start - timedelta(days=period_days)
        previous_end = start
        trades = [trade for trade in self.trade_service.list_trades(strategy_name=strategy_name, date_from=previous_start) if trade.strategy_name == strategy_name]
        current_trades = [trade for trade in trades if self._utc_datetime(trade.close_time) >= start]
        previous_trades = [trade for trade in trades if previous_start <= self._utc_datetime(trade.close_time) < previous_end]
        positions = [position for position in self.trade_service.list_positions() if position.strategy_name == strategy_name]
        executions = [execution for execution in self.trade_service.list_executions(limit=500) if execution.strategy_name == strategy_name and self._is_since(execution.last_transition_at, start)]
        runtimes = [runtime for runtime in self.runtime_state_service.list_runtimes() if runtime.strategy_name == strategy_name]
        stale_runtimes = self._stale_runtimes(runtimes, now)
        facts = StrategyReviewFacts(
            strategy_name=strategy_name,
            period_days=period_days,
            status="RUNNING" if any(runtime.status == "RUNNING" for runtime in runtimes) else "STOPPED",
            active_runtime_count=len([runtime for runtime in runtimes if runtime.status == "RUNNING"]),
            active_instruments=sorted({runtime.instrument for runtime in runtimes if runtime.status == "RUNNING"}),
            open_position_count=len(positions),
            trade_count=len(current_trades),
            win_count=len([trade for trade in current_trades if trade.pnl > 0]),
            loss_count=len([trade for trade in current_trades if trade.pnl < 0]),
            realised_pnl=round(sum(trade.pnl for trade in current_trades), 2),
            unrealised_pnl=round(sum(position.unrealized_pnl or 0.0 for position in positions), 2),
            win_rate=self._win_rate(current_trades),
            baseline_trade_count=float(len(previous_trades)) if previous_trades else None,
            baseline_win_rate=self._win_rate(previous_trades),
            stale_price_events=len(stale_runtimes),
            risk_rejections=len([execution for execution in executions if execution.status == ExecutionStatus.RISK_REJECTED.value]),
            execution_failures=len([execution for execution in executions if execution.status in {ExecutionStatus.FAILED.value, ExecutionStatus.NEEDS_MANUAL_REVIEW.value}]),
        )
        response = StrategyReviewResponse(
            metadata=self._metadata("strategy_review", now, start, now, {"strategy_name": strategy_name, "period_days": period_days}),
            facts=facts,
            derived_observations=self._strategy_observations(facts),
            possible_contributors=self._strategy_contributors(facts, executions, stale_runtimes),
            warnings=self._default_warnings(stream_health=self.stream_service.get_health(), stale_runtimes=len(stale_runtimes)),
            supporting_metrics=[
                self._metric("trade_count", "Trades", facts.trade_count, baseline=facts.baseline_trade_count),
                self._metric("win_rate", "Win Rate", facts.win_rate, unit="pct", baseline=facts.baseline_win_rate),
                self._metric("realised_pnl", "Realised PnL", facts.realised_pnl, unit="ccy"),
                self._metric("execution_failures", "Execution Failures", facts.execution_failures),
            ],
        )
        return self._finalize_review(response)

    def get_runtime_health_review(self, period_hours: int = 24) -> RuntimeHealthReviewResponse:
        now = self._utc_datetime(datetime.now(UTC))
        start = now - timedelta(hours=period_hours)
        runtimes = self.runtime_state_service.list_runtimes()
        recon_events = self.trade_service.list_reconciliation_events(date_from=start)
        executions = [execution for execution in self.trade_service.list_executions(limit=500) if self._is_since(execution.last_transition_at, start)]
        stream_health = self.stream_service.get_health()
        stale_runtimes = self._stale_runtimes(runtimes, now)
        heartbeat_issues = [
            runtime
            for runtime in runtimes
            if runtime.status == "RUNNING"
            and (
                runtime.last_heartbeat_at is None
                or (now - self._utc_datetime(runtime.last_heartbeat_at)).total_seconds() > 90
            )
        ]
        issues = [
            RuntimeIssueFact(
                strategy_name=runtime.strategy_name,
                instrument=runtime.instrument,
                issue_type="stale_price",
                detail="Runtime is active but the latest price snapshot is stale.",
                last_seen_at=self._utc_datetime(runtime.last_price_seen_at) if runtime.last_price_seen_at is not None else None,
            )
            for runtime in stale_runtimes
        ] + [
            RuntimeIssueFact(
                strategy_name=runtime.strategy_name,
                instrument=runtime.instrument,
                issue_type="heartbeat_gap",
                detail="Runtime heartbeat is missing or delayed.",
                last_seen_at=self._utc_datetime(runtime.last_heartbeat_at) if runtime.last_heartbeat_at is not None else None,
            )
            for runtime in heartbeat_issues
        ]
        facts = RuntimeHealthFacts(
            active_runtime_count=len([runtime for runtime in runtimes if runtime.status == "RUNNING"]),
            stale_price_count=len(stale_runtimes),
            heartbeat_issue_count=len(heartbeat_issues),
            disconnected_stream=stream_health.enabled and not stream_health.connected,
            polling_fallback_suspected=stream_health.enabled and not stream_health.connected and len(stale_runtimes) == 0,
            reconciliation_issue_count=len(self._reconciliation_issues(recon_events)),
            execution_failure_count=len([execution for execution in executions if execution.status in {ExecutionStatus.FAILED.value, ExecutionStatus.NEEDS_MANUAL_REVIEW.value}]),
            risk_rejection_count=len([execution for execution in executions if execution.status == ExecutionStatus.RISK_REJECTED.value]),
            issues=issues,
        )
        response = RuntimeHealthReviewResponse(
            metadata=self._metadata("runtime_health_review", now, start, now, {"period_hours": period_hours}),
            facts=facts,
            derived_observations=self._runtime_observations(facts),
            possible_contributors=self._runtime_contributors(facts),
            warnings=self._default_warnings(stream_health=stream_health, stale_runtimes=len(stale_runtimes)),
            supporting_metrics=[
                self._metric("stale_price_count", "Stale Prices", facts.stale_price_count),
                self._metric("heartbeat_issue_count", "Heartbeat Gaps", facts.heartbeat_issue_count),
                self._metric("reconciliation_issue_count", "Reconciliation Issues", facts.reconciliation_issue_count),
                self._metric("execution_failure_count", "Execution Failures", facts.execution_failure_count),
            ],
        )
        return self._finalize_review(response)

    def get_trade_postmortem(self, trade_id: int) -> TradePostMortemReviewResponse:
        trade = self.trade_service.get_trade(trade_id)
        if trade is None:
            raise ValueError(f"Trade '{trade_id}' was not found.")
        recent_trades = self.trade_service.list_trades(strategy_name=trade.strategy_name)[:50]
        strategy_losses = [item for item in recent_trades if item.pnl < 0]
        instrument_losses = [item for item in recent_trades if item.instrument == trade.instrument and item.pnl < 0]
        open_time = self._utc_datetime(trade.open_time)
        close_time = self._utc_datetime(trade.close_time)
        execution_window_start = open_time - timedelta(minutes=10)
        execution_window_end = close_time + timedelta(minutes=10)
        executions = [
            execution
            for execution in self.trade_service.list_executions(limit=500)
            if execution.strategy_name == trade.strategy_name
            and execution.instrument == trade.instrument
            and execution_window_start <= self._utc_datetime(execution.last_transition_at) <= execution_window_end
        ]
        facts = TradePostMortemFacts(
            trade_id=trade.id or trade_id,
            strategy_name=trade.strategy_name,
            instrument=trade.instrument,
            direction=trade.direction,
            entry_time=open_time,
            exit_time=close_time,
            holding_minutes=round((close_time - open_time).total_seconds() / 60, 1),
            pnl=round(trade.pnl, 2),
            outcome=trade.outcome or ("win" if trade.pnl > 0 else "loss"),
            recent_loss_count_same_strategy=len(strategy_losses[:10]),
            recent_loss_count_same_instrument=len(instrument_losses[:10]),
            matched_normal_trade_size=self._matched_normal_size(trade, recent_trades),
            execution_warning_count=len(self._execution_warning_messages(executions)),
            clustered_patterns=self._loss_cluster_patterns(strategy_losses[:10]),
        )
        response = TradePostMortemReviewResponse(
            metadata=self._metadata("trade_postmortem", self._utc_datetime(datetime.now(UTC)), open_time, close_time, {"trade_id": trade_id}),
            facts=facts,
            derived_observations=self._postmortem_observations(facts),
            possible_contributors=self._postmortem_contributors(trade, executions, strategy_losses),
            warnings=self._default_warnings(stream_health=self.stream_service.get_health(), stale_runtimes=0),
            supporting_metrics=[
                self._metric("pnl", "PnL", facts.pnl, unit="ccy"),
                self._metric("holding_minutes", "Holding Time", facts.holding_minutes, unit="min"),
                self._metric("recent_loss_count_same_strategy", "Recent Strategy Losses", facts.recent_loss_count_same_strategy),
            ],
        )
        return self._finalize_review(response)

    def answer_operational_question(self, question: str, strategy_name: str | None = None) -> OperationalQuestionReviewResponse:
        normalized = question.lower()
        inferred_strategy_name = strategy_name or self._infer_strategy_name(normalized)
        if "risk" in normalized and "blocked" in normalized:
            supporting = self.get_daily_review(datetime.now(UTC).date())
            answer_type = "risk_blockers"
        elif "operational" in normalized or "runtime" in normalized or "stale" in normalized:
            supporting = self.get_runtime_health_review()
            answer_type = "runtime_health"
        elif inferred_strategy_name is not None:
            supporting = self.get_strategy_review(inferred_strategy_name)
            answer_type = "strategy_review"
        elif "today" in normalized or "daily" in normalized or "pnl" in normalized:
            supporting = self.get_daily_review(datetime.now(UTC).date())
            answer_type = "daily_review"
        else:
            supporting = self.get_operator_summary()
            answer_type = "operator_summary"
        response = OperationalQuestionReviewResponse(
            metadata=self._metadata("operational_question", self._utc_datetime(datetime.now(UTC)), supporting.metadata.period_start, supporting.metadata.period_end, {"question": question, "strategy_name": inferred_strategy_name}),
            facts=OperationalQuestionFacts(
                question=question,
                answer_type=answer_type,
                routed_review_type=supporting.metadata.review_type,
                routed_scope=supporting.metadata.scope,
                supporting_review=supporting.model_dump(mode="json"),
            ),
            derived_observations=supporting.derived_observations,
            possible_contributors=supporting.possible_contributors,
            warnings=supporting.warnings,
            supporting_metrics=supporting.supporting_metrics,
            ai_summary=supporting.ai_summary,
            provenance=supporting.provenance,
        )
        return self._finalize_review(response, request_text=question)

    def list_review_history(self, review_type: str | None = None, limit: int = 20) -> list[ReviewRecordSummary]:
        statement = select(GeneratedReviewRecord).order_by(desc(GeneratedReviewRecord.generated_at)).limit(limit)
        if review_type:
            statement = statement.where(GeneratedReviewRecord.review_type == review_type)
        records = list(self.session.exec(statement).all())
        return [
            ReviewRecordSummary(
                review_id=record.id or 0,
                review_type=record.review_type,  # type: ignore[arg-type]
                generated_at=self._utc_datetime(record.generated_at),
                scope=record.scope,
                generation_mode=record.generation_mode,  # type: ignore[arg-type]
                provider=record.provider,
                model=record.model,
            )
            for record in records
        ]

    def get_review_record(self, review_id: int) -> PersistedReviewRecord:
        record = self.session.get(GeneratedReviewRecord, review_id)
        if record is None:
            raise ValueError(f"Review '{review_id}' was not found.")
        return PersistedReviewRecord(
            review_id=record.id or review_id,
            review_type=record.review_type,  # type: ignore[arg-type]
            scope=record.scope,
            generated_at=self._utc_datetime(record.generated_at),
            facts=record.facts_payload,
            derived_observations=record.derived_observations,
            possible_contributors=record.possible_contributors,
            warnings=record.warnings,
            supporting_metrics=record.supporting_metrics,
            ai_summary=record.ai_summary,
            prompt_version=record.prompt_version,
            provider=record.provider,
            model=record.model,
            raw_model_response=record.raw_model_response,
            generation_mode=record.generation_mode,  # type: ignore[arg-type]
        )

    def _finalize_review(self, response: Any, request_text: str | None = None) -> Any:
        facts_payload = response.facts.model_dump(mode="json") if hasattr(response.facts, "model_dump") else response.facts
        review_payload = {
            "facts": facts_payload,
            "derived_observations": [item.model_dump(mode="json") for item in response.derived_observations],
            "possible_contributors": [item.model_dump(mode="json") for item in response.possible_contributors],
            "warnings": [item.model_dump(mode="json") for item in response.warnings],
            "supporting_metrics": [item.model_dump(mode="json") for item in response.supporting_metrics],
            "metadata": {
                "review_type": response.metadata.review_type,
                "scope": response.metadata.scope,
                "period_start": response.metadata.period_start,
                "period_end": response.metadata.period_end,
            },
        }
        system_prompt, user_prompt = build_review_prompts(response.metadata.review_type, review_payload, request_text=request_text)
        llm_response = self.llm_client.generate(ReviewLLMRequest(system_prompt=system_prompt, user_prompt=user_prompt))
        response.metadata.generation_mode = "deterministic_plus_llm" if llm_response is not None else "deterministic_only"
        response.provenance = AIReviewProvenance(
            llm_attempted=llm_response is not None,
            llm_provider=llm_response.provider if llm_response is not None else None,
            llm_model=llm_response.model if llm_response is not None else None,
            prompt_version=PROMPT_VERSION,
            generated_at=self._utc_datetime(datetime.now(UTC)) if llm_response is not None else None,
            prompt_facts=review_payload,
            raw_response=llm_response.content if llm_response is not None else None,
        )
        if llm_response is not None:
            response.ai_summary = AIReviewSummary(summary=llm_response.content)
        self._persist_review(response)
        return response

    def _persist_review(self, response: Any) -> None:
        record = GeneratedReviewRecord(
            review_type=response.metadata.review_type,
            scope=response.metadata.scope,
            generated_at=self._utc_datetime(response.metadata.generated_at),
            facts_payload=response.facts.model_dump(mode="json"),
            derived_observations=[item.model_dump(mode="json") for item in response.derived_observations],
            possible_contributors=[item.model_dump(mode="json") for item in response.possible_contributors],
            warnings=[item.model_dump(mode="json") for item in response.warnings],
            supporting_metrics=[item.model_dump(mode="json") for item in response.supporting_metrics],
            ai_summary=response.ai_summary.model_dump(mode="json") if response.ai_summary is not None else None,
            prompt_version=response.provenance.prompt_version if response.provenance is not None else PROMPT_VERSION,
            provider=response.provenance.llm_provider if response.provenance is not None else None,
            model=response.provenance.llm_model if response.provenance is not None else None,
            raw_model_response=response.provenance.raw_response if response.provenance is not None else None,
            generation_mode=response.metadata.generation_mode,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        response.metadata.review_id = record.id

    def _metadata(
        self,
        review_type: ReviewType,
        as_of: datetime,
        period_start: datetime | None,
        period_end: datetime | None,
        scope: dict[str, Any],
        *,
        requested_date: date | None = None,
    ) -> ReviewMetadata:
        return ReviewMetadata(
            review_type=review_type,
            generated_at=self._utc_datetime(datetime.now(UTC)),
            as_of=self._utc_datetime(as_of),
            period_start=self._utc_datetime(period_start) if period_start is not None else None,
            period_end=self._utc_datetime(period_end) if period_end is not None else None,
            requested_date=requested_date,
            scope=scope,
            source_coverage=ReviewSourceCoverage(
                broker_summary_available=False,
                stream_health_available=True,
                coverage_notes=self._coverage_notes(),
            ),
        )

    def _coverage_notes(self) -> list[str]:
        notes = ["Reviews are grounded in persisted trades, open positions, executions, runtime state, reconciliation events, and stream health."]
        if not self.settings.ai_reviewer_llm_enabled:
            notes.append("LLM explanation is disabled; reviews remain deterministic and audit-ready.")
        return notes

    def _default_warnings(self, *, stream_health: Any, stale_runtimes: int) -> list[ReviewWarning]:
        warnings: list[ReviewWarning] = []
        if not self.settings.ai_reviewer_llm_enabled:
            warnings.append(ReviewWarning(code="llm_disabled", severity="info", message="AI explanation is disabled; deterministic summaries remain authoritative."))
        if stream_health.enabled and not stream_health.connected:
            warnings.append(ReviewWarning(code="stream_degraded", severity="warning", message="Streaming is enabled but disconnected, so freshness and execution context may rely on polled or cached data."))
        if stale_runtimes > 0:
            warnings.append(ReviewWarning(code="price_freshness_degraded", severity="warning", message=f"{stale_runtimes} runtime(s) have stale price timestamps, which weakens some operational interpretations."))
        return warnings

    def _operator_observations(
        self,
        facts: OperatorSummaryFacts,
        trades: list[Trade],
        executions: list[Execution],
        recon_events: list[ReconciliationEvent],
        stale_runtimes: list[Any],
        now: datetime,
    ) -> list[ReviewObservation]:
        observations: list[ReviewObservation] = []
        risk_delta = self._delta_value(facts.open_risk_percent, facts.baseline_open_risk_percent)
        largest_share_delta = self._delta_value(facts.largest_risk_share_percent, facts.baseline_largest_risk_share_percent)
        trade_count_delta = self._delta_value(float(len(trades)), facts.baseline_trade_count_24h)
        win_rate_delta = self._delta_value(self._win_rate(trades), facts.baseline_win_rate_24h)
        if facts.main_open_risk is not None:
            observations.append(self._obs(
                code="risk_concentration_change",
                severity="critical" if facts.largest_risk_share_percent >= 50 or (largest_share_delta is not None and largest_share_delta >= 15) else "warning",
                label="Risk concentration has tightened",
                detail=f"{facts.main_open_risk.strategy_name} on {facts.main_open_risk.instrument} now represents {facts.largest_risk_share_percent:.1f}% of open risk.",
                confidence=0.92,
                time_scope="current book vs prior operator snapshot",
                metrics=[
                    self._obs_metric("largest_risk_share_percent", "Largest Risk Share", facts.largest_risk_share_percent, unit="pct", baseline=facts.baseline_largest_risk_share_percent),
                    self._obs_metric("open_risk_percent", "Open Risk", facts.open_risk_percent, unit="pct", baseline=facts.baseline_open_risk_percent),
                ],
                entity_type="position",
                entity_id=f"{facts.main_open_risk.strategy_name}:{facts.main_open_risk.instrument}",
            ))
        if trade_count_delta is not None and abs(trade_count_delta) >= 30:
            observations.append(self._obs(
                code="trade_frequency_shift",
                severity="warning",
                label="Trade frequency shifted from rolling baseline",
                detail=f"Trade count over the last 24 hours moved {trade_count_delta:.1f}% versus the rolling baseline.",
                confidence=0.84,
                time_scope="last 24h vs rolling 5-day baseline",
                metrics=[self._obs_metric("trade_count_24h", "Trade Count", len(trades), baseline=facts.baseline_trade_count_24h)],
            ))
        if win_rate_delta is not None and abs(win_rate_delta) >= 20:
            observations.append(self._obs(
                code="win_rate_shift",
                severity="warning" if win_rate_delta < 0 else "info",
                label="Win rate shifted from rolling baseline",
                detail=f"Win rate moved {win_rate_delta:.1f}% versus the rolling baseline.",
                confidence=0.8,
                time_scope="last 24h vs rolling 5-day baseline",
                metrics=[self._obs_metric("win_rate_24h", "Win Rate", self._win_rate(trades), unit="pct", baseline=facts.baseline_win_rate_24h)],
            ))
        if stale_runtimes:
            stale_severity = "critical" if len(stale_runtimes) >= max(1, facts.active_runtimes // 2) else "warning"
            observations.append(self._obs(
                code="stale_price_severity",
                severity=stale_severity,  # type: ignore[arg-type]
                label="Price freshness degraded",
                detail=f"{len(stale_runtimes)} active runtime(s) are not receiving fresh prices within the stale threshold.",
                confidence=0.95,
                time_scope="current runtime state",
                metrics=[self._obs_metric("stale_runtimes", "Stale Runtimes", len(stale_runtimes)), self._obs_metric("active_runtimes", "Active Runtimes", facts.active_runtimes)],
            ))
        recon_patterns = self._reconciliation_pattern_counts(recon_events)
        if recon_patterns:
            top_pattern, top_count = sorted(recon_patterns.items(), key=lambda item: item[1], reverse=True)[0]
            observations.append(self._obs(
                code="reconciliation_issue_pattern",
                severity="warning",
                label="Reconciliation issues cluster around one pattern",
                detail=f"The most common reconciliation issue pattern in the last 24 hours was {top_pattern} ({top_count} event(s)).",
                confidence=0.88,
                time_scope="last 24h",
                metrics=[self._obs_metric("reconciliation_issues_24h", "Reconciliation Issues", facts.reconciliation_issues_24h)],
            ))
        failure_clusters = self._execution_failure_clusters(executions)
        if failure_clusters:
            top_cluster, top_count = sorted(failure_clusters.items(), key=lambda item: item[1], reverse=True)[0]
            observations.append(self._obs(
                code="execution_failure_cluster",
                severity="warning",
                label="Execution failures cluster around one runtime",
                detail=f"The heaviest failure cluster in the last 24 hours was {top_cluster} with {top_count} failure event(s).",
                confidence=0.86,
                time_scope="last 24h",
                metrics=[self._obs_metric("execution_failures_24h", "Execution Failures", facts.execution_failures_24h)],
            ))
        if risk_delta is not None and risk_delta >= 20:
            observations.append(self._obs(
                code="open_risk_delta_up",
                severity="warning",
                label="Open risk increased vs baseline",
                detail=f"Open risk is {risk_delta:.1f}% above the previous operator baseline.",
                confidence=0.83,
                time_scope="current book vs prior operator snapshot",
                metrics=[self._obs_metric("open_risk_percent", "Open Risk", facts.open_risk_percent, unit="pct", baseline=facts.baseline_open_risk_percent)],
            ))
        return self._rank_observations(observations)

    def _operator_contributors(self, facts: OperatorSummaryFacts, executions: list[Execution], stale_runtimes: list[Any], stream_health: Any) -> list[PossibleContributor]:
        contributors: list[PossibleContributor] = []
        if facts.risk_rejections_24h > 0:
            contributors.append(PossibleContributor(
                code="risk_gating_activity",
                label="Risk gating was active",
                detail=f"{facts.risk_rejections_24h} entry attempts were blocked by risk rules in the last 24 hours.",
                confidence=0.82,
                time_scope="last 24h",
                related_observation_codes=["trade_frequency_shift"],
                supporting_metrics=[self._obs_metric("risk_rejections_24h", "Risk Rejections", facts.risk_rejections_24h)],
            ))
        if stream_health.enabled and not stream_health.connected:
            contributors.append(PossibleContributor(
                code="stream_disconnect",
                label="Streaming degradation may be affecting platform behaviour",
                detail="Streaming is enabled but disconnected, which can increase reliance on polled data and weaken freshness.",
                confidence=0.9,
                time_scope="current platform state",
                related_observation_codes=["stale_price_severity"],
            ))
        if stale_runtimes:
            contributors.append(PossibleContributor(
                code="stale_runtime_pressure",
                label="Stale runtimes may be reducing signal quality",
                detail="Several runtimes are active without fresh prices, which can suppress normal strategy behaviour or distort health interpretation.",
                confidence=0.87,
                time_scope="current platform state",
                related_observation_codes=["stale_price_severity", "trade_frequency_shift"],
                supporting_metrics=[self._obs_metric("stale_runtimes", "Stale Runtimes", len(stale_runtimes))],
            ))
        if any(execution.status in {ExecutionStatus.FAILED.value, ExecutionStatus.NEEDS_MANUAL_REVIEW.value} for execution in executions):
            contributors.append(PossibleContributor(
                code="execution_friction",
                label="Execution friction is present",
                detail="Failed or manual-review execution events were recorded and may be contributing to abnormal behaviour.",
                confidence=0.79,
                time_scope="last 24h",
                related_observation_codes=["execution_failure_cluster"],
            ))
        return contributors

    def _daily_observations(self, facts: DailyReviewFacts, failures: list[Execution], recon_events: list[ReconciliationEvent]) -> list[ReviewObservation]:
        observations: list[ReviewObservation] = []
        trade_delta = self._delta_value(float(facts.trade_count), facts.baseline_trade_count)
        pnl_delta = self._delta_value(facts.realised_pnl, facts.baseline_realised_pnl)
        win_rate = (facts.win_count / facts.trade_count) * 100 if facts.trade_count else None
        win_rate_delta = self._delta_value(win_rate, facts.baseline_win_rate)
        if trade_delta is not None and abs(trade_delta) >= 30:
            observations.append(self._obs("trade_frequency_shift", "warning", "Trade frequency shifted", f"Trade count moved {trade_delta:.1f}% versus the rolling daily baseline.", 0.82, "review day vs prior 5-day baseline", [self._obs_metric("trade_count", "Trades", facts.trade_count, baseline=facts.baseline_trade_count)]))
        if win_rate_delta is not None and abs(win_rate_delta) >= 20:
            observations.append(self._obs("win_rate_shift", "warning" if win_rate_delta < 0 else "info", "Win rate shifted", f"Win rate moved {win_rate_delta:.1f}% versus the rolling daily baseline.", 0.78, "review day vs prior 5-day baseline", [self._obs_metric("win_rate", "Win Rate", win_rate, unit="pct", baseline=facts.baseline_win_rate)]))
        if pnl_delta is not None and abs(pnl_delta) >= 25:
            observations.append(self._obs("pnl_delta", "warning" if facts.realised_pnl < 0 else "info", "Realised PnL deviated from baseline", f"Realised PnL moved {pnl_delta:.1f}% versus baseline.", 0.76, "review day vs prior 5-day baseline", [self._obs_metric("realised_pnl", "Realised PnL", facts.realised_pnl, unit="ccy", baseline=facts.baseline_realised_pnl)]))
        if failures:
            observations.append(self._obs("execution_failure_cluster", "warning", "Execution failures occurred", f"{len(failures)} failed or manual-review execution events were recorded during the review day.", 0.89, "review day", [self._obs_metric("execution_failures", "Execution Failures", facts.execution_failures)]))
        if self._reconciliation_issues(recon_events):
            observations.append(self._obs("reconciliation_issue_pattern", "warning", "Reconciliation issues were present", "Reconciliation events show operational drift during the review day.", 0.85, "review day", [self._obs_metric("reconciliation_issues", "Reconciliation Issues", facts.reconciliation_issues)]))
        return self._rank_observations(observations)

    def _daily_contributors(self, facts: DailyReviewFacts, failures: list[Execution], risk_rejections: list[Execution], runtime_issues: list[Any]) -> list[PossibleContributor]:
        contributors: list[PossibleContributor] = []
        if risk_rejections:
            contributors.append(PossibleContributor(code="risk_rule_pressure", label="Risk rules blocked flow", detail="Risk rejections likely reduced realised trade count.", confidence=0.8, time_scope="review day", related_observation_codes=["trade_frequency_shift"], supporting_metrics=[self._obs_metric("risk_rejections", "Risk Rejections", facts.risk_rejections)]))
        if runtime_issues:
            contributors.append(PossibleContributor(code="runtime_health_noise", label="Runtime health issues were present", detail="Stale runtime conditions may have reduced normal strategy participation.", confidence=0.77, time_scope="review day", related_observation_codes=["trade_frequency_shift"]))
        if failures:
            contributors.append(PossibleContributor(code="execution_friction", label="Execution friction likely affected realised outcomes", detail="Execution failures can reduce fills or create distorted day-level performance.", confidence=0.74, time_scope="review day", related_observation_codes=["execution_failure_cluster"]))
        return contributors

    def _strategy_observations(self, facts: StrategyReviewFacts) -> list[ReviewObservation]:
        observations: list[ReviewObservation] = []
        trade_delta = self._delta_value(float(facts.trade_count), facts.baseline_trade_count)
        win_rate_delta = self._delta_value(facts.win_rate, facts.baseline_win_rate)
        if trade_delta is not None and abs(trade_delta) >= 30:
            observations.append(self._obs("trade_frequency_shift", "warning", "Trade frequency shifted", f"Trade count moved {trade_delta:.1f}% versus the prior baseline window.", 0.83, f"last {facts.period_days}d vs previous {facts.period_days}d", [self._obs_metric("trade_count", "Trades", facts.trade_count, baseline=facts.baseline_trade_count)]))
        if win_rate_delta is not None and abs(win_rate_delta) >= 20:
            observations.append(self._obs("win_rate_shift", "warning" if win_rate_delta < 0 else "info", "Win rate shifted", f"Win rate moved {win_rate_delta:.1f}% versus the prior baseline window.", 0.8, f"last {facts.period_days}d vs previous {facts.period_days}d", [self._obs_metric("win_rate", "Win Rate", facts.win_rate, unit="pct", baseline=facts.baseline_win_rate)]))
        if facts.stale_price_events > 0:
            observations.append(self._obs("stale_price_severity", "warning", "Price freshness degraded", f"{facts.stale_price_events} stale runtime event(s) were present for this strategy.", 0.92, f"last {facts.period_days}d", [self._obs_metric("stale_price_events", "Stale Runtime Events", facts.stale_price_events)]))
        if facts.execution_failures > 0:
            observations.append(self._obs("execution_failure_cluster", "warning", "Execution issues affected the strategy", f"{facts.execution_failures} execution issue(s) were recorded in the selected period.", 0.86, f"last {facts.period_days}d", [self._obs_metric("execution_failures", "Execution Failures", facts.execution_failures)]))
        return self._rank_observations(observations)

    def _strategy_contributors(self, facts: StrategyReviewFacts, executions: list[Execution], stale_runtimes: list[Any]) -> list[PossibleContributor]:
        contributors: list[PossibleContributor] = []
        if stale_runtimes:
            contributors.append(PossibleContributor(code="stale_price_pressure", label="Stale pricing may be suppressing normal behaviour", detail="Price freshness degraded for active runtimes tied to the strategy.", confidence=0.85, time_scope=f"last {facts.period_days}d", related_observation_codes=["stale_price_severity"]))
        if any(execution.status == ExecutionStatus.RISK_REJECTED.value for execution in executions):
            contributors.append(PossibleContributor(code="risk_gating_activity", label="Risk gating blocked candidate entries", detail="Risk rejections may explain some reduction in strategy activity.", confidence=0.81, time_scope=f"last {facts.period_days}d", related_observation_codes=["trade_frequency_shift"]))
        if facts.execution_failures > 0:
            contributors.append(PossibleContributor(code="execution_friction", label="Execution issues may have affected realised outcomes", detail="Execution failures can distort both trade count and realised PnL.", confidence=0.76, time_scope=f"last {facts.period_days}d", related_observation_codes=["execution_failure_cluster"]))
        return contributors

    def _runtime_observations(self, facts: RuntimeHealthFacts) -> list[ReviewObservation]:
        observations: list[ReviewObservation] = []
        if facts.disconnected_stream:
            observations.append(self._obs("stream_disconnect", "critical", "Streaming is disconnected", "The market data stream is enabled but not connected.", 0.98, "current runtime state", [self._obs_metric("disconnected_stream", "Disconnected Stream", int(facts.disconnected_stream))]))
        if facts.stale_price_count > 0:
            observations.append(self._obs("stale_price_severity", "critical" if facts.stale_price_count >= max(1, facts.active_runtime_count // 2) else "warning", "Stale prices detected", f"{facts.stale_price_count} runtime(s) are active without fresh prices.", 0.95, "current runtime state", [self._obs_metric("stale_price_count", "Stale Prices", facts.stale_price_count), self._obs_metric("active_runtime_count", "Active Runtimes", facts.active_runtime_count)]))
        if facts.reconciliation_issue_count > 0:
            observations.append(self._obs("reconciliation_issue_pattern", "warning", "Reconciliation drift detected", f"{facts.reconciliation_issue_count} reconciliation issue(s) were recorded in the review window.", 0.88, "review window", [self._obs_metric("reconciliation_issue_count", "Reconciliation Issues", facts.reconciliation_issue_count)]))
        if facts.execution_failure_count > 0:
            observations.append(self._obs("execution_failure_cluster", "warning", "Execution failures recorded", f"{facts.execution_failure_count} execution failure event(s) were recorded in the review window.", 0.84, "review window", [self._obs_metric("execution_failure_count", "Execution Failures", facts.execution_failure_count)]))
        return self._rank_observations(observations)

    def _runtime_contributors(self, facts: RuntimeHealthFacts) -> list[PossibleContributor]:
        contributors: list[PossibleContributor] = []
        if facts.polling_fallback_suspected:
            contributors.append(PossibleContributor(code="polling_fallback", label="Polling fallback is suspected", detail="Streaming is disconnected while stale counts remain low, which suggests recent polling fallback rather than total data loss.", confidence=0.72, time_scope="review window", related_observation_codes=["stream_disconnect"]))
        if facts.heartbeat_issue_count > 0:
            contributors.append(PossibleContributor(code="heartbeat_gaps", label="Heartbeat gaps may be contributing to health noise", detail="Missing heartbeats can indicate runtime scheduling or loop issues.", confidence=0.8, time_scope="review window", related_observation_codes=["stale_price_severity"]))
        return contributors

    def _postmortem_observations(self, facts: TradePostMortemFacts) -> list[ReviewObservation]:
        observations: list[ReviewObservation] = []
        if facts.outcome == "loss":
            observations.append(self._obs("loss_trade", "warning", "Trade closed negative", f"The selected trade realised {facts.pnl:.2f}.", 0.99, "selected trade", [self._obs_metric("pnl", "PnL", facts.pnl, unit="ccy")]))
        if facts.execution_warning_count > 0:
            observations.append(self._obs("execution_failure_cluster", "warning", "Execution warnings surrounded the trade", f"{facts.execution_warning_count} execution warning(s) were recorded around the trade lifecycle.", 0.83, "selected trade lifecycle", [self._obs_metric("execution_warning_count", "Execution Warnings", facts.execution_warning_count)]))
        if facts.recent_loss_count_same_strategy >= 3:
            observations.append(self._obs("loss_cluster", "warning", "Losses cluster around the strategy", f"There are {facts.recent_loss_count_same_strategy} recent losses in the same strategy sample.", 0.79, "recent loss sample", [self._obs_metric("recent_loss_count_same_strategy", "Recent Strategy Losses", facts.recent_loss_count_same_strategy)]))
        return self._rank_observations(observations)

    def _postmortem_contributors(self, trade: Trade, executions: list[Execution], strategy_losses: list[Trade]) -> list[PossibleContributor]:
        contributors: list[PossibleContributor] = []
        if not self._matched_normal_size(trade, strategy_losses[:20]):
            contributors.append(PossibleContributor(code="size_outlier", label="Trade size was outside recent norm", detail="The selected trade size differs materially from the recent strategy average.", confidence=0.73, time_scope="selected trade", related_observation_codes=["loss_trade"]))
        if any(execution.status in {ExecutionStatus.FAILED.value, ExecutionStatus.NEEDS_MANUAL_REVIEW.value} for execution in executions):
            contributors.append(PossibleContributor(code="execution_friction", label="Execution friction was present", detail="Execution issues may have affected the entry or exit quality of the trade.", confidence=0.77, time_scope="selected trade lifecycle", related_observation_codes=["execution_failure_cluster"]))
        if len(strategy_losses[:10]) >= 3:
            contributors.append(PossibleContributor(code="loss_cluster", label="Trade may belong to a broader losing patch", detail="Several recent losses in the same strategy suggest regime mismatch or timing weakness rather than an isolated outlier.", confidence=0.75, time_scope="recent loss sample", related_observation_codes=["loss_cluster"]))
        return contributors

    def _rank_observations(self, observations: list[ReviewObservation]) -> list[ReviewObservation]:
        severity_score = {"critical": 3, "warning": 2, "info": 1}
        ordered = sorted(observations, key=lambda item: (severity_score[item.severity], item.confidence), reverse=True)
        for index, item in enumerate(ordered, start=1):
            item.rank = index
        return ordered

    def _metric(self, key: str, label: str, value: float | int | str | None, *, unit: str | None = None, baseline: float | int | str | None = None) -> SupportingMetric:
        delta_value = self._delta_value(value, baseline)
        return SupportingMetric(
            key=key,
            label=label,
            value=value,
            unit=unit,
            baseline_value=baseline,
            delta_value=round(delta_value, 2) if isinstance(delta_value, float) else delta_value,
            trend=self._trend(delta_value),
        )

    def _obs_metric(self, key: str, label: str, value: float | int | str | None, *, unit: str | None = None, baseline: float | int | str | None = None) -> ObservationMetric:
        delta_value = self._delta_value(value, baseline)
        return ObservationMetric(
            key=key,
            label=label,
            value=value,
            unit=unit,
            baseline_value=baseline,
            delta_value=round(delta_value, 2) if isinstance(delta_value, float) else delta_value,
        )

    def _obs(
        self,
        code: str,
        severity: str,
        label: str,
        detail: str,
        confidence: float,
        time_scope: str,
        metrics: list[ObservationMetric],
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> ReviewObservation:
        return ReviewObservation(
            code=code,
            severity=severity,  # type: ignore[arg-type]
            label=label,
            detail=detail,
            confidence=confidence,
            time_scope=time_scope,
            supporting_metrics=metrics,
            entity_type=entity_type,
            entity_id=entity_id,
        )

    def _previous_fact(self, record: GeneratedReviewRecord | None, key: str) -> float | None:
        if record is None:
            return None
        value = record.facts_payload.get(key)
        return self._float_or_none(value)

    def _latest_review_record(self, review_type: str) -> GeneratedReviewRecord | None:
        statement = (
            select(GeneratedReviewRecord)
            .where(GeneratedReviewRecord.review_type == review_type)
            .order_by(desc(GeneratedReviewRecord.generated_at))
            .limit(1)
        )
        return self.session.exec(statement).first()

    def _rolling_trade_count_baseline(self, now: datetime, *, windows: int, window_days: int) -> float | None:
        counts: list[int] = []
        for offset in range(1, windows + 1):
            end = now - timedelta(days=window_days * (offset - 1))
            start = end - timedelta(days=window_days)
            counts.append(len(self.trade_service.list_trades(date_from=start, date_to=end)))
        return round(mean(counts), 2) if counts else None

    def _rolling_win_rate_baseline(self, now: datetime, *, windows: int, window_days: int) -> float | None:
        win_rates: list[float] = []
        for offset in range(1, windows + 1):
            end = now - timedelta(days=window_days * (offset - 1))
            start = end - timedelta(days=window_days)
            window_trades = self.trade_service.list_trades(date_from=start, date_to=end)
            win_rate = self._win_rate(window_trades)
            if win_rate is not None:
                win_rates.append(win_rate)
        return round(mean(win_rates), 2) if win_rates else None

    def _group_trades_by_strategy(self, trades: list[Trade]) -> dict[str, list[Trade]]:
        grouped: dict[str, list[Trade]] = defaultdict(list)
        for trade in trades:
            grouped[trade.strategy_name].append(trade)
        return grouped

    def _stale_runtimes(self, runtimes: list[Any], now: datetime) -> list[Any]:
        stale_after = self.settings.runtime_price_stale_after_seconds * 2
        now_utc = self._utc_datetime(now)
        return [
            runtime
            for runtime in runtimes
            if runtime.status == "RUNNING"
            and (
                runtime.last_price_seen_at is None
                or (now_utc - self._utc_datetime(runtime.last_price_seen_at)).total_seconds() > stale_after
            )
        ]

    def _reconciliation_issues(self, events: list[ReconciliationEvent]) -> list[ReconciliationEvent]:
        return [event for event in events if event.event_type != "POSITION_SYNCED_FROM_BROKER"]

    def _reconciliation_pattern_counts(self, events: list[ReconciliationEvent]) -> dict[str, int]:
        patterns = Counter(event.event_type for event in self._reconciliation_issues(events))
        return dict(patterns)

    def _execution_failure_clusters(self, executions: list[Execution]) -> dict[str, int]:
        clusters = Counter(f"{execution.strategy_name}:{execution.instrument}" for execution in executions if execution.status in {ExecutionStatus.FAILED.value, ExecutionStatus.NEEDS_MANUAL_REVIEW.value})
        return dict(clusters)

    def _risk_rejection_breakdown(self, executions: list[Execution]) -> dict[str, int]:
        counter: Counter[str] = Counter()
        for execution in executions:
            rule = str(execution.details.get("risk_rule") or execution.error_code or execution.reason or "unspecified")
            counter[rule] += 1
        return dict(counter)

    def _execution_warning_messages(self, executions: list[Execution]) -> list[str]:
        warnings: list[str] = []
        for execution in executions:
            if execution.status == ExecutionStatus.RISK_REJECTED.value:
                warnings.append(f"Risk rejected: {execution.reason or execution.error_code or 'unspecified rule'}")
            if execution.status in {ExecutionStatus.FAILED.value, ExecutionStatus.NEEDS_MANUAL_REVIEW.value}:
                warnings.append(f"Execution issue: {execution.error_message or execution.reason or execution.status}")
        return warnings

    def _loss_cluster_patterns(self, losses: list[Trade]) -> list[TradeClusterPattern]:
        if not losses:
            return []
        session_counts = Counter(self._session_bucket(loss.open_time) for loss in losses)
        instrument_counts = Counter(loss.instrument for loss in losses)
        top_session, top_session_count = session_counts.most_common(1)[0]
        top_instrument, top_instrument_count = instrument_counts.most_common(1)[0]
        return [
            TradeClusterPattern(pattern="session_cluster", count=top_session_count, share_percent=round((top_session_count / len(losses)) * 100, 1), detail=f"Losses most often opened during the {top_session} session bucket."),
            TradeClusterPattern(pattern="instrument_cluster", count=top_instrument_count, share_percent=round((top_instrument_count / len(losses)) * 100, 1), detail=f"{top_instrument} is the most common instrument across the sampled losses."),
        ]

    def _matched_normal_size(self, trade: Trade, comparison_trades: list[Trade]) -> bool:
        sizes = [item.size for item in comparison_trades if item.id != trade.id]
        if not sizes:
            return True
        average_size = mean(sizes)
        return abs(trade.size - average_size) <= average_size * 0.5

    def _session_bucket(self, timestamp: datetime) -> str:
        hour = self._utc_datetime(timestamp).hour
        if 0 <= hour < 8:
            return "asia"
        if 8 <= hour < 16:
            return "london"
        return "us"

    def _infer_strategy_name(self, normalized_question: str) -> str | None:
        names = {runtime.strategy_name for runtime in self.runtime_state_service.list_runtimes()} | {trade.strategy_name for trade in self.trade_service.list_trades()[:100]}
        for name in sorted(names):
            lowered = name.lower()
            spaced = lowered.replace("_", " ")
            if lowered in normalized_question or spaced in normalized_question:
                return name
        return None

    def _delta_value(self, current: float | int | str | None, baseline: float | int | str | None) -> float | None:
        if current is None or baseline in {None, 0}:
            return None
        try:
            current_float = float(current)
            baseline_float = float(baseline)
        except (TypeError, ValueError):
            return None
        return ((current_float - baseline_float) / baseline_float) * 100

    def _trend(self, delta_value: float | int | str | None) -> str:
        if delta_value is None:
            return "unknown"
        try:
            delta = float(delta_value)
        except (TypeError, ValueError):
            return "unknown"
        if delta > 0:
            return "up"
        if delta < 0:
            return "down"
        return "flat"

    def _win_rate(self, trades: list[Trade]) -> float | None:
        if not trades:
            return None
        wins = len([trade for trade in trades if trade.pnl > 0])
        return round((wins / len(trades)) * 100, 2)

    def _in_period(self, timestamp: datetime | None, start: datetime, end: datetime) -> bool:
        return timestamp is not None and self._utc_datetime(start) <= self._utc_datetime(timestamp) <= self._utc_datetime(end)

    def _is_since(self, timestamp: datetime | None, since: datetime) -> bool:
        return timestamp is not None and self._utc_datetime(timestamp) >= self._utc_datetime(since)

    def _float_or_none(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _utc_datetime(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
