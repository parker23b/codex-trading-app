"use client";

import { useEffect, useState } from "react";

import { EquityPanel } from "@/components/dashboard/equity-panel";
import { KpiBar } from "@/components/dashboard/kpi-bar";
import { OpenPositionsTable } from "@/components/dashboard/open-positions-table";
import { RecentTradesTable } from "@/components/dashboard/recent-trades-table";
import { RiskAllocationPanel } from "@/components/dashboard/risk-allocation-panel";
import { RiskPanel } from "@/components/dashboard/risk-panel";
import { StrategyTapePanel } from "@/components/dashboard/strategy-tape-panel";
import { ModeIndicator } from "@/components/ui/mode-indicator";
import { Card } from "@/components/ui/card";
import { getBrokerAuthStatus, getDashboardSnapshot, getOpenPositions, getStreamHealth, getTrades } from "@/lib/api";
import { BrokerAuthStatus, DashboardSnapshot, Position, StreamHealthStatus, Trade } from "@/lib/types";

type DashboardLiveProps = {
  initialPositions: Position[];
  initialTrades: Trade[];
  initialBrokerAuth: BrokerAuthStatus;
  initialDashboard: DashboardSnapshot;
  initialStreamHealth: StreamHealthStatus;
};

export function DashboardLive({
  initialPositions,
  initialTrades,
  initialBrokerAuth,
  initialDashboard,
  initialStreamHealth,
}: DashboardLiveProps) {
  const [positions, setPositions] = useState(initialPositions);
  const [trades, setTrades] = useState(initialTrades);
  const [brokerAuth, setBrokerAuth] = useState(initialBrokerAuth);
  const [dashboard, setDashboard] = useState(initialDashboard);
  const [streamHealth, setStreamHealth] = useState(initialStreamHealth);

  useEffect(() => {
    setPositions(initialPositions);
    setTrades(initialTrades);
    setBrokerAuth(initialBrokerAuth);
    setDashboard(initialDashboard);
    setStreamHealth(initialStreamHealth);
  }, [initialPositions, initialTrades, initialBrokerAuth, initialDashboard, initialStreamHealth]);

  useEffect(() => {
    let cancelled = false;

    const refresh = async () => {
      try {
        const [nextPositions, nextTrades, nextBrokerAuth, nextDashboard, nextStreamHealth] = await Promise.all([
          getOpenPositions(),
          getTrades(),
          getBrokerAuthStatus(),
          getDashboardSnapshot(),
          getStreamHealth(),
        ]);
        if (cancelled) {
          return;
        }
        setPositions(nextPositions);
        setTrades(nextTrades);
        setBrokerAuth(nextBrokerAuth);
        setDashboard(nextDashboard);
        setStreamHealth(nextStreamHealth);
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
    <main className="dashboard-layout">
      <section className="top-command-bar">
        <div className="top-command-bar__mode">
          <ModeIndicator mode={mode} brokerAuth={brokerAuth} streamHealth={streamHealth} />
        </div>
        <div className="top-command-bar__snapshot">
          <Card title="Book Snapshot" subtitle="Quick read on current book quality." className="card--compact">
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
                <strong>{longLineCount} long / {shortLineCount} short</strong>
              </div>
            </div>
            <div className="status-note status-note--inline">
              {openRiskPercent < 2
                ? "Risk is contained relative to current equity."
                : openRiskPercent < 4
                  ? "Risk is buildable, but new entries should be selective."
                  : "Risk is elevated. Prioritise netting, trims, or tighter stops before adding."}
            </div>
            <div className="status-note status-note--inline">
              {(dashboard.runningStrategies ?? []).length > 0
                ? `${(dashboard.runningStrategies ?? []).filter((row) => row.hasOpenPosition).length} runtime${(dashboard.runningStrategies ?? []).filter((row) => row.hasOpenPosition).length === 1 ? "" : "s"} currently hold exposure; the rest are scanning only.`
                : "No active runtimes are publishing into the dashboard yet."}
            </div>
          </Card>
        </div>
        <div className="top-command-bar__metrics">
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
      <section className="hero-grid">
        <div className="hero-grid__main">
          <EquityPanel
            points={equityCurve.length ? equityCurve : [{ label: "T1", value: 100000, drawdown: 0 }]}
            latestValue={accountValue}
            delta={dailyPnl}
          />
        </div>
        <div className="hero-grid__side">
          <RiskPanel
            capitalAtRisk={openRiskPercent}
            largestPosition={largestPosition}
            concentration={riskConcentration}
            drawdown={drawdownPercent}
          />
        </div>
      </section>
      <section className="page-grid">
        <div className="insight-grid">
          <RiskAllocationPanel
            longExposure={longExposure}
            shortExposure={shortExposure}
            allocations={exposureByInstrument}
            grossExposurePercent={grossExposurePercent}
            netExposurePercent={netExposurePercent}
            positionCount={positions.length}
          />
          <StrategyTapePanel rows={dashboard.runningStrategies ?? []} />
        </div>
      </section>
      <section className="page-grid">
        <Card title="Open Positions" subtitle="Current exposure and execution state." className="card--table card--full-width">
          <div className="status-note status-note--inline">
            Runtime-specific positions are now shown with broker references so same-instrument exposure stays distinguishable.
          </div>
          <div className="status-note status-note--inline">
            This table is read-only until position close and manual override actions are backed by durable backend mutations.
          </div>
          <OpenPositionsTable positions={positions} />
        </Card>
      </section>
      <section className="page-grid">
        <Card title="Recent Trades" subtitle="Latest closed trades." className="card--table">
          <RecentTradesTable trades={sortedTrades.slice(0, 10)} />
        </Card>
      </section>
    </main>
  );
}
