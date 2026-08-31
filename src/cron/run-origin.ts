/** Display formatter for the cron run-origin field. Pure: no React or DOM deps. */
import type { CronRunTriggerSource } from "./types.js";

/** Closed union of values a finished run row can carry on the `trigger` field. */
export type CronRunOrigin = CronRunTriggerSource | "legacy-unknown";

/** Canonical human-readable label for a run origin. Missing values map to legacy-unknown. */
const CRON_RUN_ORIGIN_LABELS: Record<CronRunOrigin, string> = {
  scheduled: "Scheduled — cron fire",
  manual: "Manual run",
  "trigger-script": "Trigger script fired",
  "on-exit": "On-exit watcher",
  stream: "Stream batch",
  "legacy-unknown": "Unknown (legacy)",
};

/**
 * Resolves a finished run row's trigger to a display origin. Missing or
 * unrecognized values surface as `legacy-unknown` so we never invent a
 * scheduled/manual history that the producer did not record.
 */
export function resolveCronRunOrigin(trigger: CronRunTriggerSource | undefined): CronRunOrigin {
  switch (trigger) {
    case "scheduled":
    case "manual":
    case "trigger-script":
    case "on-exit":
    case "stream":
      return trigger;
    default:
      return "legacy-unknown";
  }
}

/** Stable display label for a finished run origin. */
export function formatCronRunOriginLabel(trigger: CronRunTriggerSource | undefined): string {
  return CRON_RUN_ORIGIN_LABELS[resolveCronRunOrigin(trigger)];
}

/** Full label map for callers that want to render the closed set directly. */
export function cronRunOriginLabels(): Record<CronRunOrigin, string> {
  return { ...CRON_RUN_ORIGIN_LABELS };
}
