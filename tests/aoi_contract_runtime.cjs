// Execute against the compiled production parser, not a duplicate implementation.
const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const contract = require(require('node:path').resolve(process.argv[2]));
const fixture = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const clone = () => structuredClone(fixture);
test('accepts the actual Python-produced wire response', () => {
  assert.equal(contract.parseFrozenPlan(clone()).planning_gate,'PASS');
});
test('rejects row loss even when displayed counts still add up', () => {
  const p=clone(); p.assets=[]; assert.throws(()=>contract.parseFrozenPlan(p));
});
test('rejects zero-required READY', () => {
  const p=clone(); p.assets=[]; for(const k in p.counts) p.counts[k]=0;
  assert.throws(()=>contract.parseFrozenPlan(p));
});
test('rejects negative and fractional counters', () => {
  for(const n of [-1,0.5,NaN,Infinity]) {
    const p=clone(); p.counts.discovered=n; assert.throws(()=>contract.parseFrozenPlan(p));
  }
});
test('rejects phantom cache promotion', () => {
  const p=clone();p.assets[0].cache_state='CACHE_HIT';assert.throws(()=>contract.parseFrozenPlan(p));
});
test('rejects unresolved residue presented as READY', () => {
  const p=clone();p.unresolved_reasons=['catalog unavailable'];assert.throws(()=>contract.parseFrozenPlan(p));
});
test('rejects touch-only inclusion', () => {
  const p=clone();p.assets[0].processing_relation='TOUCH_ONLY';assert.throws(()=>contract.parseFrozenPlan(p));
});
test('rejects undefined geometry promoted to positive-area required', () => {
  const p=clone();p.assets[0].processing_relation='UNRESOLVED';assert.throws(()=>contract.parseFrozenPlan(p));
});
test('rejects an enabled downloader or invented coverage', () => {
  for(const k of ['fetch','coverage']) {
    const p=clone();if(k==='fetch')p.capabilities.fetch=true;else p.coverage={percent:100};
    assert.throws(()=>contract.parseFrozenPlan(p));
  }
});
test('preserves multipart holes when editing another ring', () => {
  const g={type:'MultiPolygon',coordinates:[[[[0,0],[4,0],[4,4],[0,4],[0,0]],[[1,1],[2,1],[2,2],[1,2],[1,1]]],[[[5,5],[6,5],[6,6],[5,6],[5,5]]]]};
  const before=structuredClone(g);const moved=contract.moveVertex(g,1,0,0,[4.9,5]);
  assert.deepEqual(moved.coordinates[0],g.coordinates[0]);assert.deepEqual(g,before);
  assert.deepEqual(moved.coordinates[1][0][0],moved.coordinates[1][0].at(-1));
});
test('rejects implicit first feature and unknown CRS', () => {
  assert.throws(()=>contract.readGeometry({type:'FeatureCollection',features:[]}));
  const g=clone().normalized_aoi;g.crs={properties:{name:'EPSG:26920'}};
  assert.throws(()=>contract.readGeometry(g));
});
test('edit or clear invalidates an in-flight plan token', () => {
  const gate=new contract.PlanRevisionGate(), token=gate.invalidate();
  assert.equal(gate.current(token),true);gate.invalidate();assert.equal(gate.current(token),false);
});
test('rejects a plan for another AOI', () => {
  const p=clone(),g=structuredClone(p.normalized_aoi);g.coordinates[0][1][0]+=.01;
  assert.throws(()=>contract.assertPlanMatchesAoi(p,g));
});
