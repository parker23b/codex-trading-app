import { formatInstrumentLabel, formatPrice } from "./format";
import type { Execution } from "./types";

function getExecutionDetailValue(details: Record<string, unknown>, key: string) {
  const value = details[key];
  return typeof value === "string" && value.length ? value : null;
}

function getBrokerResultStatus(details: Record<string, unknown>) {
  const brokerResult = details.broker_result;
  if (!brokerResult || typeof brokerResult !== "object" || Array.isArray(brokerResult)) {
    return null;
  }
  const status = (brokerResult as Record<string, unknown>).status;
  return typeof status === "string" && status.length ? status : null;
}

export function buildExecutionDetail(execution: Execution) {
  const size = execution.filled_size ?? execution.requested_size;
  const price = execution.average_fill_price ?? execution.requested_price;
  const brokerResultStatus = getBrokerResultStatus(execution.details);
  const reconciledBrokerReference = getExecutionDetailValue(execution.details, "reconciled_broker_reference");
  const parts = [
    execution.strategy_name,
    formatInstrumentLabel(execution.instrument),
    typeof size === "number" ? `size ${size}` : null,
    typeof price === "number" ? `px ${formatPrice(price, execution.instrument)}` : null,
    execution.client_request_id ? `request ${execution.client_request_id}` : null,
    execution.broker_reference ? `broker ${execution.broker_reference}` : null,
    brokerResultStatus ? `broker result ${brokerResultStatus.replaceAll("_", " ")}` : null,
    reconciledBrokerReference ? `reconciled broker ${reconciledBrokerReference}` : null,
    execution.critical_execution_drift
      ? "critical risk drift detected"
      : execution.material_execution_drift
        ? "material risk drift detected"
        : null,
    execution.requires_manual_review ? "manual review required" : null,
  ].filter(Boolean);

  if (execution.error_message) {
    parts.push(execution.error_message);
  } else if (execution.reason) {
    parts.push(execution.reason);
  }

  return parts.join(" • ");
}
