export function formatCurrency(value: number) {
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatPercent(value: number, digits = 1) {
  return `${value.toFixed(digits)}%`;
}

export function formatSignedCurrency(value: number) {
  return `${value >= 0 ? "+" : "-"}${formatCurrency(Math.abs(value))}`;
}

export function formatSignedPercent(value: number, digits = 1) {
  return `${value >= 0 ? "+" : "-"}${Math.abs(value).toFixed(digits)}%`;
}

export function formatInstrumentLabel(instrument: string) {
  return instrument.replace("IX.D.", "").replace(".DAILY.IP", "");
}

export function formatRelativeDuration(fromIso: string, toDate = new Date()) {
  const from = new Date(fromIso);
  const deltaMs = Math.max(0, toDate.getTime() - from.getTime());
  const totalMinutes = Math.floor(deltaMs / 60000);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
}

