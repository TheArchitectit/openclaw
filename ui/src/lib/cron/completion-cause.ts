/**
 * UI classification labels for the runs table and the jobs table failure column.
 *
 * Producer-authored `completionCause` wins over derived attribution. When no
 * cause is set, the label falls back to a derived state from the run entry +
 * the job's last run timestamp.
 */
import type { CronRunLogEntry } from "../../api/types.ts";

/** Distinct failure buckets the Automations pane surfaces. */
export type RunFailureLabel =
  | "active"
  | "autoDisabled"
  | "previous"
  | "historical"
  | "gatewayRestart"
  | "ownerUnavailable"
  | "budgetExhausted";

/**
 * Window (ms) inside which a "previous" failure is still treated as the
 * current actionable failure. Past it, the failure becomes historical.
 */
const ACTIVE_FAILURE_WINDOW_MS = 24 * 60 * 60 * 1000;

/**
 * Whether a run failed: the producer codec's completionStatus is authoritative
 * when present; legacy entries predate it and only carry the deprecated
 * status field.
 */
function isFailedRun(entry: Pick<CronRunLogEntry, "completionStatus" | "status">): boolean {
  if (entry.completionStatus === "failed") {
    return true;
  }
  if (entry.completionStatus === "succeeded") {
    return false;
  }
  return entry.status === "error";
}

/** Pick the producer-authoritative label, otherwise a derived state label. */
export function runFailureLabel(
  entry: Pick<CronRunLogEntry, "completionCause" | "completionStatus" | "status" | "ts"> & {
    lastRunAtMs?: number;
  },
  nowMs: number,
): RunFailureLabel | null {
  if (entry.completionCause === "gateway-restart") {
    return "gatewayRestart";
  }
  if (entry.completionCause === "owner-unavailable") {
    return "ownerUnavailable";
  }
  if (entry.completionCause === "budget-exhausted") {
    return "budgetExhausted";
  }
  if (!isFailedRun(entry)) {
    return null;
  }
  const lastMs = typeof entry.lastRunAtMs === "number" ? entry.lastRunAtMs : entry.ts;
  if (!Number.isFinite(lastMs)) {
    return "historical";
  }
  return nowMs - lastMs <= ACTIVE_FAILURE_WINDOW_MS ? "active" : "previous";
}
