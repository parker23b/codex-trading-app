import { EquityPanel } from "@/components/dashboard/equity-panel";
import { KpiBar } from "@/components/dashboard/kpi-bar";
import { OpenPositionsTable } from "@/components/dashboard/open-positions-table";
import { RecentTradesTable } from "@/components/dashboard/recent-trades-table";
import { RiskAllocationPanel } from "@/components/dashboard/risk-allocation-panel";
import { RiskPanel } from "@/components/dashboard/risk-panel";
import { ModeIndicator } from "@/components/ui/mode-indicator";
import { Card } from "@/components/ui/card";
import { getBackendMode, getOpenPositions, getTrades } from "@/lib/api";

export default async function DashboardPage() {
  const [positions, trades, backendMode] = await Promise.all([
    getOpenPositions(),
    getTrades(),
    getBackendMode(),
  ]);

  const sortedTrades = trades
    .slice()
    .sort((left, right) => new Date(right.close_time).getTime() - new Date(left.close_time).getTime());

  const closedPnl = sortedTrades.reduce((sum, trade) => sum + trade.pnl, 0);
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
  const riskRewardRatio = averageLoss === 0 ? averageWin : averageWin / averageLoss;
  const accountValue = 100000 + closedPnl;
  const dailyPnl = latestSessionKey
    ? trailingTrades
        .filter((trade) => trade.close_time.slice(0, 10) === latestSessionKey)
        .reduce((sum, trade) => sum + trade.pnl, 0)
    : 0;
  const dailyPnlPercent = (dailyPnl / 100000) * 100;
  const accountChangePercent = (closedPnl / 100000) * 100;
  const openRiskPercent = positions.reduce((sum, position) => sum + (position.risk_percent ?? 0), 0);
  const largestPosition = positions.length
    ? Math.max(...positions.map((position) => ((position.open_price * position.size) / accountValue) * 100))
    : 0;

  const equityCurve = trailingTrades
    .slice()
    .reverse()
    .reduce<{ label: string; value: number; drawdown: number }[]>((series, trade, index) => {
      const previous = series[index - 1]?.value ?? 100000;
      const nextValue = Number((previous + trade.pnl).toFixed(2));
      const peak = Math.max(...series.map((point) => point.value), 100000, nextValue);
      series.push({
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

  return (
    <main className="dashboard-layout">
      <section className="top-command-bar">
        <ModeIndicator mode={mode} />
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
      </section>
      <section className="command-grid">
        <div className="command-grid__main">
          <EquityPanel
            points={equityCurve.length ? equityCurve : [{ label: "T1", value: 100000, drawdown: 0 }]}
            latestValue={accountValue}
            delta={dailyPnl}
          />
        </div>
        <div className="command-grid__side">
          <RiskPanel
            capitalAtRisk={openRiskPercent}
            largestPosition={largestPosition}
            concentration={riskConcentration}
            drawdown={drawdownPercent}
          />
        </div>
      </section>
      <section className="command-grid">
        <div className="command-grid__main">
          <Card title="Open Positions" subtitle="Current exposure and controls.">
            <div className="status-note">Demo actions only. Close and override changes stay in the UI and do not send orders.</div>
            <OpenPositionsTable positions={positions} />
            {backendMode === "dev-fallback" ? (
              <div className="status-note">Displaying sample positions because the backend is offline.</div>
            ) : null}
          </Card>
        </div>
        <div className="command-grid__side">
          <RiskAllocationPanel
            longExposure={longExposure}
            shortExposure={shortExposure}
            allocations={exposureByInstrument}
          />
        </div>
      </section>
      <section className="page-grid">
        <Card title="Recent Trades" subtitle="Latest closed trades.">
          <RecentTradesTable trades={sortedTrades.slice(0, 10)} />
          {backendMode === "dev-fallback" ? (
            <div className="status-note">Displaying sample trades because the backend is offline.</div>
          ) : null}
        </Card>
      </section>
    </main>
  );
}
