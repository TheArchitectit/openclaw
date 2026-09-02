import { describe, expect, it } from "vitest";
import { cronJobKindLabelKeys, formatCronJobKind } from "./job-kind.ts";

describe("formatCronJobKind", () => {
  it.each([
    ["agentTurn", "Agent"],
    ["command", "Command"],
    ["systemEvent", "System event"],
    ["heartbeat", "Heartbeat"],
    ["skillCollectionReview", "Skill review"],
    ["script", "Script"],
  ] as const)("maps %s to canonical label %s", (kind, expected) => {
    expect(formatCronJobKind(kind)).toBe(expected);
  });

  it("capitalizes unknown future kinds so they read legibly", () => {
    expect(formatCronJobKind("weirdThing" as "agentTurn")).toBe("WeirdThing");
    expect(formatCronJobKind("NEW_kind" as "agentTurn")).toBe("NEW_kind");
  });

  it("falls back to empty string when given empty input", () => {
    expect(formatCronJobKind("")).toBe("");
  });

  it("exposes the closed locale-key map for direct callers", () => {
    const keys = cronJobKindLabelKeys();
    expect(Object.keys(keys).toSorted()).toEqual(
      [
        "agentTurn",
        "command",
        "heartbeat",
        "script",
        "skillCollectionReview",
        "systemEvent",
      ].toSorted(),
    );
    expect(Object.values(keys).every((key) => key.startsWith("cron.jobKind."))).toBe(true);
  });
});
