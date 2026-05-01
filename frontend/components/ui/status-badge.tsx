type StatusTone = "positive" | "negative" | "warning" | "neutral" | "live";

type StatusBadgeProps = {
  label: string;
  tone: StatusTone;
};

export function StatusBadge({ label, tone }: StatusBadgeProps) {
  return <span className={`status-badge ${tone}`}>{label}</span>;
}
