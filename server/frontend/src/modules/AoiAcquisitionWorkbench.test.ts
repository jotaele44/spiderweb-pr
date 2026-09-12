import { describe, expect, it } from "vitest";
import { auditPlanArithmetic } from "./AoiAcquisitionWorkbench";

describe("auditPlanArithmetic", () => {
  it("passes when discovery and required-asset arithmetic both close", () => {
    expect(auditPlanArithmetic({
      discovered: 20,
      retained: 12,
      excluded: 6,
      unresolved: 2,
      required: 12,
      cacheValid: 7,
      fetchRequired: 4,
      blockedRequired: 1,
    })).toEqual({ discoveredClosed: true, requiredClosed: true, pass: true });
  });

  it("fails closed when discovery arithmetic loses a row", () => {
    const audit = auditPlanArithmetic({
      discovered: 20,
      retained: 12,
      excluded: 5,
      unresolved: 2,
      required: 12,
      cacheValid: 7,
      fetchRequired: 4,
      blockedRequired: 1,
    });
    expect(audit.discoveredClosed).toBe(false);
    expect(audit.pass).toBe(false);
  });

  it("fails closed when required-asset arithmetic does not close", () => {
    const audit = auditPlanArithmetic({
      discovered: 20,
      retained: 12,
      excluded: 6,
      unresolved: 2,
      required: 12,
      cacheValid: 7,
      fetchRequired: 4,
      blockedRequired: 0,
    });
    expect(audit.requiredClosed).toBe(false);
    expect(audit.pass).toBe(false);
  });
});
