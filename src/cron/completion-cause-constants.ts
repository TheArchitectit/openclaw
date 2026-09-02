/** Exact legacy error string and canonical cause mapping for restart-interrupted runs. */
import type { CronCompletionCause } from "./types.js";

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
