// One logical-run token budget: fallback candidates share a single guard, so
// spend from an earlier candidate counts against every later candidate.
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { makeIsolatedAgentParamsFixture } from "./job-fixtures.js";
import {
  clearFastTestEnv,
  isCliProviderMock,
  loadRunCronIsolatedAgentTurn,
  logWarnMock,
  makeCronSession,
  makeCronSessionEntry,
  mockRunCronFallbackPassthrough,
  resolveAllowedModelRefMock,
  resolveConfiguredModelRefMock,
  resolveCronSessionMock,
  resetRunCronIsolatedAgentTurnHarness,
  runCliAgentMock,
  runEmbeddedAgentMock,
  runWithModelFallbackMock,
} from "./run.test-harness.js";

const runCronIsolatedAgentTurn = await loadRunCronIsolatedAgentTurn();

function makeJob() {
  return {
    id: "cron-budget-carry-job",
    name: "Budget Carry Test",
    schedule: { kind: "cron", expr: "0 * * * *", tz: "UTC" },
    sessionTarget: "isolated",
    payload: {
      kind: "agentTurn",
      message: "run task",
      tokenBudget: 200,
    },
  } as never;
}

function makeParams() {
  return {
    cfg: {},
    deps: {} as never,
    job: makeJob(),
    message: "run task",
    sessionKey: "cron:budget-carry",
  };
}

describe("runCronIsolatedAgentTurn — token budget carries across candidates", () => {
  let previousFastTestEnv: string | undefined;

  beforeEach(async () => {
    previousFastTestEnv = clearFastTestEnv();
    resetRunCronIsolatedAgentTurnHarness();

    resolveConfiguredModelRefMock.mockReturnValue({
      provider: "anthropic",
      model: "claude-opus-4-6",
    });
    resolveAllowedModelRefMock.mockImplementation(({ raw }: { raw: string }) => {
      const [provider, model] = raw.split("/");
      return { ref: { provider, model } };
    });
    resolveCronSessionMock.mockReturnValue(
      makeCronSession({
        sessionEntry: makeCronSessionEntry({
          model: undefined,
          modelProvider: undefined,
        }),
        isNewSession: true,
      }),
    );
    logWarnMock.mockReturnValue(undefined);
  });

  afterEach(() => {
    if (previousFastTestEnv !== undefined) {
      process.env.OPENCLAW_TEST_FAST = previousFastTestEnv;
    } else {
      delete process.env.OPENCLAW_TEST_FAST;
    }
  });

  it("aborts later candidates once earlier candidates exhausted the budget", async () => {
    const entries: Array<{ abortedAtEntry: boolean; abortedAfterUsage: boolean }> = [];
    runWithModelFallbackMock.mockImplementation(
      async ({ run }: { run: (p: string, m: string) => Promise<unknown> }) => {
        await run("anthropic", "model-a");
        const second = await run("anthropic", "model-b");
        return {
          result: second,
          provider: "anthropic",
          model: "model-b",
          attempts: [],
        };
      },
    );
    runEmbeddedAgentMock.mockImplementation(
      async (call: {
        abortSignal?: AbortSignal;
        onRunUsageTotals?: (usage: { total: number }) => void;
      }) => {
        const signal = call.abortSignal;
        const abortedAtEntry = signal?.aborted ?? false;
        call.onRunUsageTotals?.({ total: 150 });
        entries.push({ abortedAtEntry, abortedAfterUsage: signal?.aborted ?? false });
        return {
          payloads: [{ text: "partial" }],
          meta: {
            agentMeta: { provider: "anthropic", model: "model-a", usage: { total: 150 } },
          },
        };
      },
    );

    const result = await runCronIsolatedAgentTurn(makeParams());

    expect(entries.length).toBe(2);
    // First candidate spent 150 of 200: no trip at entry or after its usage.
    expect(entries[0]).toEqual({ abortedAtEntry: false, abortedAfterUsage: false });
    // Second candidate inherits the carry: 150 + 150 >= 200 trips the shared
    // logical-run guard when its usage reports, instead of starting fresh.
    expect(entries[1]).toEqual({ abortedAtEntry: false, abortedAfterUsage: true });
    expect(result.status).toBeDefined();
  });

  it("stops fallback selection when the first candidate exhausts the budget", async () => {
    const coordinatorSignals: Array<AbortSignal | undefined> = [];
    const candidateRuns: Array<{ abortedAtEntry: boolean }> = [];
    runWithModelFallbackMock.mockImplementation(
      async ({
        abortSignal,
        run,
      }: {
        abortSignal?: AbortSignal;
        run: (p: string, m: string) => Promise<unknown>;
      }) => {
        coordinatorSignals.push(abortSignal);
        // Mirror the shared coordinator admission guard: a later candidate
        // must not be prepared or executed once the supplied signal aborted.
        abortSignal?.throwIfAborted();
        const first = await run("anthropic", "model-a");
        abortSignal?.throwIfAborted();
        const second = await run("anthropic", "model-b");
        return { result: second ?? first, provider: "anthropic", model: "model-b", attempts: [] };
      },
    );
    runEmbeddedAgentMock.mockImplementation(
      async (call: {
        abortSignal?: AbortSignal;
        onRunUsageTotals?: (usage: { total: number }) => void;
      }) => {
        candidateRuns.push({ abortedAtEntry: call.abortSignal?.aborted ?? false });
        call.onRunUsageTotals?.({ total: 200 });
        return {
          payloads: [{ text: "partial" }],
          meta: {
            agentMeta: { provider: "anthropic", model: "model-a", usage: { total: 200 } },
          },
        };
      },
    );

    const result = await runCronIsolatedAgentTurn(makeParams());

    // The coordinator received the budget-armed composite signal, which tripped
    // when the first candidate reported the full 200-token spend.
    expect(coordinatorSignals).toHaveLength(1);
    expect(coordinatorSignals[0]?.aborted).toBe(true);
    // The second candidate was never prepared or executed.
    expect(candidateRuns).toEqual([{ abortedAtEntry: false }]);
    // The persisted terminal outcome names the budget, not a generic abort.
    expect(result.status).toBe("error");
    expect(result.error).toContain("Token budget exhausted");
    expect(result.error).toContain("200");
  });

  it("fails a CLI candidate whose returned usage reaches the budget cap", async () => {
    // CLI usage only surfaces after runCliAgent resolves: a successful result
    // must still fail the run when its final usage meets the cap, instead of
    // persisting a success that exceeded the budget.
    isCliProviderMock.mockImplementation((provider: string) => provider === "claude-cli");
    runCliAgentMock.mockImplementation(async () => ({
      payloads: [{ text: "over cap" }],
      meta: { agentMeta: { usage: { total: 250 } } },
    }));
    mockRunCronFallbackPassthrough();

    const result = await runCronIsolatedAgentTurn(
      makeIsolatedAgentParamsFixture({
        job: {
          id: "cron-budget-cli-job",
          name: "Budget CLI Cap",
          schedule: { kind: "cron", expr: "0 * * * *", tz: "UTC" },
          sessionTarget: "isolated",
          payload: { kind: "agentTurn", message: "run task", tokenBudget: 200 },
        },
        cfg: {
          agents: {
            defaults: {
              model: "anthropic/claude-opus-4-6",
              models: {
                "anthropic/claude-opus-4-6": { agentRuntime: { id: "claude-cli" } },
              },
            },
          },
        },
      }),
    );

    expect(runCliAgentMock).toHaveBeenCalledOnce();
    expect(result.status).toBe("error");
    expect(result.error).toContain("Token budget exhausted");
    expect(result.error).toContain("200");
  });
});
