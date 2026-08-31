import { describe, expect, it } from "vitest";
import {
  cronRunOriginLabels,
  formatCronRunOriginLabel,
  resolveCronRunOrigin,
} from "./run-origin.js";

describe("resolveCronRunOrigin", () => {
  it.each([["scheduled"], ["manual"], ["trigger-script"], ["on-exit"], ["stream"]] as const)(
    "maps known trigger %s to itself",
    (trigger) => {
      expect(resolveCronRunOrigin(trigger)).toBe(trigger);
    },
  );

  it("maps missing trigger to legacy-unknown", () => {
    expect(resolveCronRunOrigin(undefined)).toBe("legacy-unknown");
  });

  it("maps unrecognized trigger strings to legacy-unknown without inventing history", () => {
    expect(resolveCronRunOrigin("automatic" as unknown as "scheduled")).toBe("legacy-unknown");
    expect(resolveCronRunOrigin("" as unknown as "scheduled")).toBe("legacy-unknown");
    expect(resolveCronRunOrigin(null as unknown as "scheduled")).toBe("legacy-unknown");
  });
});

describe("formatCronRunOriginLabel", () => {
  it("returns the canonical label for each enum value", () => {
    expect(formatCronRunOriginLabel("scheduled")).toBe("Scheduled — cron fire");
    expect(formatCronRunOriginLabel("manual")).toBe("Manual run");
    expect(formatCronRunOriginLabel("trigger-script")).toBe("Trigger script fired");
    expect(formatCronRunOriginLabel("on-exit")).toBe("On-exit watcher");
    expect(formatCronRunOriginLabel("stream")).toBe("Stream batch");
  });

  it("returns the legacy-unknown label for missing trigger", () => {
    expect(formatCronRunOriginLabel(undefined)).toBe("Unknown (legacy)");
  });

  it("returns the legacy-unknown label for unrecognized trigger values", () => {
    expect(formatCronRunOriginLabel("automatic" as unknown as "scheduled")).toBe(
      "Unknown (legacy)",
    );
  });

  it("exposes a complete label map covering the closed origin set", () => {
    const labels = cronRunOriginLabels();
    expect(Object.keys(labels).sort()).toEqual(
      ["legacy-unknown", "manual", "on-exit", "scheduled", "stream", "trigger-script"].sort(),
    );
    expect(labels["legacy-unknown"]).toBe("Unknown (legacy)");
  });
});
