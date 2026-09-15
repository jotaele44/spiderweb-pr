import { describe, expect, it } from "vitest";
import { auditPlanArithmetic, moveVertex, PlanRevisionGate, readGeometry } from "./aoiContract";
const closed = { discovered: 20, retained: 12, excluded: 6, unresolved: 2,
  required: 12, cache_valid: 7, fetch_required: 4, blocked_required: 1 };
describe("AOI dry-run invariants", () => {
  it("closes both arithmetic denominators without claiming readiness", () => {
    expect(auditPlanArithmetic(closed)).toEqual({discoveredClosed:true,requiredClosed:true,pass:true});
  });
  it("rejects lost rows", () => { expect(auditPlanArithmetic({...closed, excluded:5}).pass).toBe(false); });
  it("rejects required-asset mismatch", () => { expect(auditPlanArithmetic({...closed, blocked_required:0}).pass).toBe(false); });
  it("rejects negative counts that happen to add up", () => { expect(auditPlanArithmetic({...closed, cache_valid:-1,fetch_required:12}).pass).toBe(false); });
  it("invalidates responses after clear/edit", () => {
    const gate = new PlanRevisionGate(), token = gate.invalidate(); gate.invalidate(); expect(gate.current(token)).toBe(false);
  });
  it("preserves holes and closes the moved first vertex", () => {
    const geometry = readGeometry({type:"Polygon",coordinates:[[[0,0],[4,0],[4,4],[0,4],[0,0]],[[1,1],[2,1],[2,2],[1,2],[1,1]]]});
    const moved = moveVertex(geometry,0,0,0,[-1,0]);
    expect(moved.coordinates[1]).toEqual(geometry.coordinates[1]);
    expect(geometry.coordinates[0][0]).toEqual([0,0]);
  });
});
