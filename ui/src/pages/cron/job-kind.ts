/**
 * Pure display formatter for cron job payload kinds.
 *
 * Job kind (what executes) is orthogonal to run origin (what initiated the run).
 * Never collapse these two dimensions.
 */
import type { CronPayload } from "../../api/types.ts";

/** Closed set of job kinds this formatter handles. */
export type CronJobKind = CronPayload["kind"];

/** Display label for each known job kind. */
const JOB_KIND_LABELS: Record<CronJobKind, string> = {
  agentTurn: "Agent",
  command: "Command",
  systemEvent: "System event",
  heartbeat: "Heartbeat",
  skillCollectionReview: "Skill review",
  script: "Script",
};

/**
 * Resolves a job's payload kind to a display label. Missing or unrecognized
 * kinds fall back to the capitalized raw value so future additions render
 * legibly rather than vanishing silently.
 */
export function formatCronJobKind(kind: CronJobKind | string): string {
  return JOB_KIND_LABELS[kind as CronJobKind] ?? capitalize(String(kind));
}

/** Stable display label map for callers that want the closed set directly. */
export function cronJobKindLabels(): Readonly<Record<CronJobKind, string>> {
  return JOB_KIND_LABELS;
}

function capitalize(value: string): string {
  if (value.length === 0) {
    return value;
  }
  return value[0]!.toUpperCase() + value.slice(1);
}
