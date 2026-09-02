/**
 * Display formatter for cron job payload kinds.
 *
 * Job kind (what executes) is orthogonal to run origin (what initiated the run).
 * Never collapse these two dimensions.
 *
 * Labels resolve through the locale catalog so non-English sessions translate.
 */
import type { CronPayload } from "../../api/types.ts";
import { t } from "../../i18n/index.ts";

/** Closed set of job kinds this formatter handles. */
export type CronJobKind = CronPayload["kind"];

/** Locale key for each known job kind. */
const JOB_KIND_LABEL_KEYS: Record<CronJobKind, string> = {
  agentTurn: "cron.jobKind.agentTurn",
  command: "cron.jobKind.command",
  systemEvent: "cron.jobKind.systemEvent",
  heartbeat: "cron.jobKind.heartbeat",
  skillCollectionReview: "cron.jobKind.skillCollectionReview",
  script: "cron.jobKind.script",
};

/**
 * Resolves a job's payload kind to a display label. Missing or unrecognized
 * kinds fall back to the capitalized raw value so future additions render
 * legibly rather than vanishing silently.
 */
export function formatCronJobKind(kind: CronJobKind | string): string {
  const key = JOB_KIND_LABEL_KEYS[kind as CronJobKind];
  if (key) {
    return t(key);
  }
  return capitalize(String(kind));
}

/** Stable locale-key map for callers that want the closed set directly. */
export function cronJobKindLabelKeys(): Readonly<Record<CronJobKind, string>> {
  return JOB_KIND_LABEL_KEYS;
}

function capitalize(value: string): string {
  if (value.length === 0) {
    return value;
  }
  return value[0]!.toUpperCase() + value.slice(1);
}
