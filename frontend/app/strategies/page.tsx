import { StrategyControlPanel } from "@/components/strategy/strategy-control-panel";
import { ModeIndicator } from "@/components/ui/mode-indicator";
import { Card } from "@/components/ui/card";
import { getBackendMode, getStrategies } from "@/lib/api";

export default async function StrategiesPage() {
  const [strategies, backendMode] = await Promise.all([getStrategies(), getBackendMode()]);
  const mode = strategies[0]?.account_type ?? "DEMO";

  return (
    <main className="page-grid">
      <section className="top-command-bar">
        <ModeIndicator mode={mode} backendMode={backendMode} />
      </section>
      <Card
        title="Strategy Control Panel"
        subtitle="Each card exposes run-state, current performance, and configuration so you can operate strategies like a control surface, not a list."
      >
        <StrategyControlPanel strategies={strategies} />
        {backendMode === "dev-fallback" ? (
          <div className="status-note">Strategy actions are simulated locally while the backend is unavailable.</div>
        ) : null}
      </Card>
    </main>
  );
}
