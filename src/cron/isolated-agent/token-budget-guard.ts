import type { NormalizedUsage } from "../../agents/usage.js";

export type TokenBudgetGuard = (usage: NormalizedUsage) => void;

/**
 * Arms a one-shot token-budget tripwire over run-cumulative usage snapshots.
 * The guard fires `onExceeded` once, at the first snapshot whose cumulative
 * total reaches the budget; usage snapshots without a total never trip it.
 * A guard armed with an already-aborted signal stays inert.
 */
export function createTokenBudgetGuard(params: {
  budget: number;
  onExceeded: (usage: NormalizedUsage) => void;
  signal?: AbortSignal;
}): TokenBudgetGuard {
  let tripped = false;
  return (usage) => {
    if (tripped || params.signal?.aborted) {
      return;
    }
    if (typeof usage.total !== "number") {
      return;
    }
    if (usage.total >= params.budget) {
      tripped = true;
      params.onExceeded(usage);
    }
  };
}
