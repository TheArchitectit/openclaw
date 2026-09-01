/** Exact completion cause literals for type-level contracts and runtime matching. */
export const CRON_COMPLETION_CAUSES = [
  "gateway-restart",
  "owner-unavailable",
  "budget-exhausted",
] as const;

export type CronCompletionCause = (typeof CRON_COMPLETION_CAUSES)[number];

/** Returns true iff the value is a known CronCompletionCause. */
export function isCronCompletionCause(value: unknown): value is CronCompletionCause {
  return (
    typeof value === "string" &&
    (value === "gateway-restart" || value === "owner-unavailable" || value === "budget-exhausted")
  );
}

/** Exact legacy error string produced by the gateway restart interrupt path. */
export const CRON_STARTUP_INTERRUPTED_ERROR = "cron: job interrupted by gateway restart";

/**
 * Maps the exact legacy error string to its canonical completion cause.
 * No prefix-matching, whitespace trimming, or fuzzy logic — exact equality only.
 */
export function resolveLegacyGatewayRestartCause(error: unknown): CronCompletionCause | undefined {
  if (error === CRON_STARTUP_INTERRUPTED_ERROR) {
    return "gateway-restart";
  }
  return undefined;
}
