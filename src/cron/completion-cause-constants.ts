/** Exact legacy error string and canonical cause mapping for restart-interrupted runs. */

/** Exact legacy error string produced by the gateway restart interrupt path. */
export const CRON_STARTUP_INTERRUPTED_ERROR = "cron: job interrupted by gateway restart";

/**
 * Maps the exact legacy error string to its canonical completion cause
 * (a `CronCompletionCause` union member). Inlined literal to keep this leaf
 * module import-free. No prefix-matching, trimming, or fuzzy logic.
 */
export function resolveLegacyGatewayRestartCause(error: unknown): "gateway-restart" | undefined {
  if (error === CRON_STARTUP_INTERRUPTED_ERROR) {
    return "gateway-restart";
  }
  return undefined;
}
