"use client";

import { useEffect, useState } from "react";

import { AutonomyOverview } from "@/components/dashboard/autonomy-overview";
import { CoverageControlPanel } from "@/components/dashboard/coverage-control-panel";
import { CoverageSnapshot } from "@/components/dashboard/coverage-snapshot";
import { ControlPlaneStrip } from "@/components/dashboard/control-plane-strip";
import { EquityPanel } from "@/components/dashboard/equity-panel";
import { KpiBar } from "@/components/dashboard/kpi-bar";
import { NotificationCenter } from "@/components/dashboard/notification-center";
import { OpenPositionsTable } from "@/components/dashboard/open-positions-table";
import { RecentTradesTable } from "@/components/dashboard/recent-trades-table";
import { RiskPanel } from "@/components/dashboard/risk-panel";
import { StrategyTapePanel } from "@/components/dashboard/strategy-tape-panel";
import { ModeIndicator } from "@/components/ui/mode-indicator";
import { Card } from "@/components/ui/card";
import { getBrokerAuthStatus, getControlPlaneSummary, getCoverageSummary, getDashboardSnapshot, getExecutions, getOpenPositions, getStreamHealth, getSystemOperatingLimits, getTrades } from "@/lib/api";
import { BrokerAuthStatus, ControlPlaneSummary, CoverageSummary, DashboardSnapshot, Execution, Position, StreamHealthStatus, SystemOperatingLimits, Trade } from "@/lib/types";

type DashboardLiveProps = {
  initialPositions: Position[];
  initialTrades: Trade[];
  initialExecutions: Execution[];
  initialBrokerAuth: BrokerAuthStatus;
  initialDashboard: DashboardSnapshot;
  initialStreamHealth: StreamHealthStatus;
  initialCoverage: CoverageSummary;
  initialControlPlane: ControlPlaneSummary;
  initialOperatingLimits: SystemOperatingLimits;
};

export function DashboardLive({
  initialPositions,
  initialTrades,
  initialExecutions,
  initialBrokerAuth,
  initialDashboard,
  initialStreamHealth,
  initialCoverage,
  initialControlPlane,
  initialOperatingLimits,
}: DashboardLiveProps) {
  const [positions, setPositions] = useState(initialPositions);
  const [trades, setTrades] = useState(initialTrades);
  const [executions, setExecutions] = useState(initialExecutions);
  const [brokerAuth, setBrokerAuth] = useState(initialBrokerAuth);
  const [dashboard, setDashboard] = useState(initialDashboard);
  const [streamHealth, setStreamHealth] = useState(initialStreamHealth);
  const [coverage, setCoverage] = useState(initialCoverage);
  const [controlPlane, setControlPlane] = useState(initialControlPlane);
  const [operatingLimits, setOperatingLimits] = useState(initialOperatingLimits);

  useEffect(() => {
    setPositions(initialPositions);
    setTrades(initialTrades);
    setExecutions(initialExecutions);
    setBrokerAuth(initialBrokerAuth);
    setDashboard(initialDashboard);
    setStreamHealth(initialStreamHealth);
    setCoverage(initialCoverage);
    setControlPlane(initialControlPlane);
    setOperatingLimits(initialOperatingLimits);
  }, [initialPositions, initialTrades, initialExecutions, initialBrokerAuth, initialDashboard, initialStreamHealth, initialCoverage, initialControlPlane, initialOperatingLimits]);

  useEffect(() => {
    let cancelled = false;

    const refresh = async () => {
      try {
        const [nextPositions, nextTrades, nextExecutions, nextBrokerAuth, nextDashboard, nextStreamHealth, nextCoverage, nextControlPlane, nextOperatingLimits] = await Promise.all([
          getOpenPositions(),
          getTrades(),
          getExecutions(),
          getBrokerAuthStatus(),
          getDashboardSnapshot(),
          getStreamHealth(),
          getCoverageSummary(),
          getControlPlaneSummary(),
          getSystemOperatingLimits(),
        ]);
        if (cancelled) {
          return;
        }
        setPositions(nextPositions);
        setTrades(nextTrades);
        setExecutions(nextExecutions);
        setBrokerAuth(nextBrokerAuth);
        setDashboard(nextDashboard);
        setStreamHealth(nextStreamHealth);
        setCoverage(nextCoverage);
        setControlPlane(nextControlPlane);
        setOperatingLimits(nextOperatingLimits);
      } catch {
        // Keep the last successful snapshot visible if a refresh fails.
      }
    };

    const intervalId = window.setInterval(refresh, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  const sortedTrades = trades
    .slice()
    .sort((left, right) => new Date(right.close_time).getTime() - new Date(left.close_time).getTime());

  const longExposure = positions
    .filter((position) => position.direction === "BUY")
    .reduce((sum, position) => sum + position.open_price * position.size, 0);
  const shortExposure = positions
    .filter((position) => position.direction === "SELL")
    .reduce((sum, position) => sum + position.open_price * position.size, 0);
  const openExposure = longExposure + shortExposure;
  const trailingTrades = sortedTrades.slice(0, 30);
  const latestSessionKey = trailingTrades[0]?.close_time.slice(0, 10) ?? null;
  const winRate = trailingTrades.length
    ? (trailingTrades.filter((trade) => trade.pnl > 0).length / trailingTrades.length) * 100
    : 0;
  const averageWin =
    trailingTrades.filter((trade) => trade.pnl > 0).reduce((sum, trade) => sum + trade.pnl, 0) /
    Math.max(trailingTrades.filter((trade) => trade.pnl > 0).length, 1);
  const averageLoss =
    Math.abs(trailingTrades.filter((trade) => trade.pnl < 0).reduce((sum, trade) => sum + trade.pnl, 0)) /
    Math.max(trailingTrades.filter((trade) => trade.pnl < 0).length, 1);
  const riskRewardRatio = dashboard.riskReward || (averageLoss === 0 ? averageWin : averageWin / averageLoss);
  const accountValue = dashboard.accountValue;
  const dailyPnl = dashboard.dailyPnl;
  const dailyPnlPercent = dashboard.dailyPnlPercent;
  const accountChangePercent = dashboard.accountValuePercent;
  const openRiskPercent = dashboard.openRisk;
  const grossExposurePercent = accountValue > 0 ? (openExposure / accountValue) * 100 : 0;
  const netExposurePercent = accountValue > 0 ? ((longExposure - shortExposure) / accountValue) * 100 : 0;
  const averagePositionRiskPercent = positions.length
    ? positions.reduce((sum, position) => sum + (position.risk_percent ?? 0), 0) / positions.length
    : 0;
  const largestPosition = positions.length
    ? Math.max(...positions.map((position) => ((position.open_price * position.size) / accountValue) * 100))
    : 0;

  const equityCurve = trailingTrades
    .slice()
    .reverse()
    .reduce<{ timestamp: string; label: string; value: number; drawdown: number }[]>((series, trade, index) => {
      const previous = series[index - 1]?.value ?? 100000;
      const nextValue = Number((previous + trade.pnl).toFixed(2));
      const peak = Math.max(...series.map((point) => point.value), 100000, nextValue);
      series.push({
        timestamp: trade.close_time,
        label: new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" }).format(new Date(trade.close_time)),
        value: nextValue,
        drawdown: Number((((peak - nextValue) / peak) * 100).toFixed(2)),
      });
      return series;
    }, []);

  const exposureByInstrument = positions.map((position) => ({
    instrument: position.instrument,
    allocation: Number((((position.open_price * position.size) / Math.max(openExposure, 1)) * 100).toFixed(1)),
  }));
  const mode = positions[0]?.account_type ?? trades[0]?.account_type ?? "DEMO";
  const riskConcentration = exposureByInstrument.length ? Math.max(...exposureByInstrument.map((item) => item.allocation)) : 0;
  const drawdownPercent = equityCurve.length ? Math.max(...equityCurve.map((point) => point.drawdown)) : 0;
  const longLineCount = positions.filter((position) => position.direction === "BUY").length;
  const shortLineCount = positions.filter((position) => position.direction === "SELL").length;
  const activeStrategyCount = (dashboard.runningStrategies ?? []).length;

  return (
    <main className="dashboard-layout operate-board">
      <section className="operate-board__top">
        <div className="operate-board__mode">
          <ModeIndicator mode={mode} brokerAuth={brokerAuth} streamHealth={streamHealth} />
        </div>
        <div className="operate-board__autonomy">
          <AutonomyOverview
            summary={controlPlane}
            brokerAuth={brokerAuth}
            streamHealth={streamHealth}
            activeRuntimeCount={activeStrategyCount}
            positionCount={positions.length}
          />
        </div>
        <div className="operate-board__metrics">
          <KpiBar
            accountValue={accountValue}
            accountChangePercent={accountChangePercent}
            dailyPnl={dailyPnl}
            dailyPnlPercent={dailyPnlPercent}
            openRiskPercent={openRiskPercent}
            winRate={winRate}
            riskRewardRatio={riskRewardRatio}
            sampleSize={trailingTrades.length}
            sessionLabel={latestSessionKey ? new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" }).format(new Date(latestSessionKey)) : "Latest session"}
          />
        </div>
      </section>

      <section className="operate-board__workspace">
        <div className="operate-board__primary">
          <EquityPanel
            points={equityCurve.length ? equityCurve : [{ label: "T1", value: 100000, drawdown: 0 }]}
            latestValue={accountValue}
            delta={dailyPnl}
          />

          <ControlPlaneStrip summary={controlPlane} />

          <Card title="Open Positions" subtitle="Largest live exposures and execution state." className="card--table card--full-width board-surface board-surface--primary">
            <div className="status-note status-note--inline">
              Runtime-specific positions are shown with broker references so same-instrument exposure stays distinguishable.
            </div>
            <div className="status-note status-note--inline">
              This table is read-only until position close and manual override actions are backed by durable backend mutations.
            </div>
            <OpenPositionsTable positions={positions} />
          </Card>
        </div>

        <aside className="operate-board__secondary">
          <RiskPanel
            capitalAtRisk={openRiskPercent}
            largestPosition={largestPosition}
            concentration={riskConcentration}
            drawdown={drawdownPercent}
          />

          <CoverageSnapshot coverage={coverage} />

          <Card title="Book Snapshot" subtitle="Compact exposure summary, with deeper analysis left to secondary pages." className="card--compact board-surface board-surface--rail">
            <div className="summary-grid">
              <div className="summary-grid__item">
                <span className="eyebrow">Active Strategies</span>
                <strong>{activeStrategyCount}</strong>
              </div>
              <div className="summary-grid__item">
                <span className="eyebrow">Avg Line Risk</span>
                <strong>{averagePositionRiskPercent.toFixed(2)}%</strong>
              </div>
              <div className="summary-grid__item">
                <span className="eyebrow">Long / Short</span>
                <strong>{longLineCount} / {shortLineCount}</strong>
              </div>
              <div className="summary-grid__item">
                <span className="eyebrow">Gross Exposure</span>
                <strong>{grossExposurePercent.toFixed(1)}%</strong>
              </div>
              <div className="summary-grid__item">
                <span className="eyebrow">Net Exposure</span>
                <strong>{netExposurePercent.toFixed(1)}%</strong>
              </div>
              <div className="summary-grid__item">
                <span className="eyebrow">Largest Line</span>
                <strong>{largestPosition.toFixed(1)}%</strong>
              </div>
            </div>
            <div className="status-note status-note--inline">
              {openRiskPercent < 2
                ? "Risk is contained relative to current equity."
                : openRiskPercent < 4
                  ? "Risk is buildable, but new entries should stay selective."
                  : "Risk is elevated. Monitor autonomous deployment carefully before allowing fresh exposure to compound."}
            </div>
            <div className="status-note status-note--inline">
              Coverage, allocation detail, and deployment reasoning now live on their own pages so the homepage stays focused on system state.
            </div>
          </Card>

          <StrategyTapePanel rows={dashboard.runningStrategies ?? []} />
        </aside>
      </section>

      <NotificationCenter executions={executions} brokerAuth={brokerAuth} streamHealth={streamHealth} />

      <section className="operate-board__lower">
        <CoverageControlPanel coverage={coverage} operatingLimits={operatingLimits} />
        <Card title="Recent Trades" subtitle="Latest closed trades remain available here, but no longer define the homepage narrative." className="card--table board-surface board-surface--secondary">
          <RecentTradesTable trades={sortedTrades.slice(0, 8)} />
        </Card>
      </section>
    </main>
  );
}
