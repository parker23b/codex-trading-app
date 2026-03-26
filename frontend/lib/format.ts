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

function normalizeInstrumentKey(instrument?: string) {
  return (instrument ?? "").toUpperCase();
}

function isForexInstrument(instrument?: string) {
  const key = normalizeInstrumentKey(instrument);
  return key.startsWith("CS.D.") || /^[A-Z]{6}$/.test(key);
}

function isIndexInstrument(instrument?: string) {
  const key = normalizeInstrumentKey(instrument);
  return key.startsWith("IX.D.");
}

function isCommodityInstrument(instrument?: string) {
  const key = normalizeInstrumentKey(instrument);
  return key.startsWith("CC.D.") || ["XAUUSD", "XAGUSD", "WTI", "BRENT", "NG", "CL"].includes(key);
}

function isCryptoInstrument(instrument?: string) {
  const key = normalizeInstrumentKey(instrument);
  return key.startsWith("CR.D.") || key.endsWith("BTCUSD") || key.endsWith("ETHUSD") || key.endsWith("SOLUSD");
}

function quoteDigits(value: number, instrument?: string) {
  const key = normalizeInstrumentKey(instrument);
  if (isForexInstrument(key)) {
    return key.includes("JPY") ? 3 : 5;
  }
  if (isIndexInstrument(key)) {
    return 1;
  }
  if (isCommodityInstrument(key)) {
    return value >= 100 ? 2 : 3;
  }
  if (isCryptoInstrument(key)) {
    return value >= 1000 ? 2 : 4;
  }
  if (value >= 1000) {
    return 1;
  }
  if (value >= 100) {
    return 2;
  }
  return 4;
}

export function formatPrice(value: number, instrument?: string) {
  const digits = quoteDigits(value, instrument);
  return new Intl.NumberFormat("en-GB", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export function formatInstrumentLabel(instrument: string) {
  return instrument
    .replace("IX.D.", "")
    .replace("CS.D.", "")
    .replace(".DAILY.IP", "")
    .replace(".CFD.IP", "");
}

export function formatRelativeDuration(fromIso: string, toDate = new Date()) {
  const from = new Date(fromIso);
  const deltaMs = Math.max(0, toDate.getTime() - from.getTime());
  const totalMinutes = Math.floor(deltaMs / 60000);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
}
