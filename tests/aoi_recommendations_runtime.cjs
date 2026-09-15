const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const { parseDatasetRecommendations: parse, selectedApplicableRows: select, sourceUrl } = require(process.argv[2]);
const original = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const fresh = () => structuredClone(original);

test('Python response yields separate recommended datasets and exact files', () => {
  const r=parse(fresh()); assert.deepEqual(r.recommended_dataset_ids,['A','B']);
  assert.deepEqual(select(r,['A']).map(r=>r.row_id),['A:0']);
  assert.deepEqual(select(r,['A','B']).map(r=>r.row_id),['A:0','B:0']);
  assert.equal(select(r,['A'])[0],r.plan.assets[0]);
});
test('no automatic source selection', () => assert.deepEqual(select(parse(fresh()),[]),[]));
test('response is not rewritten', () => { const r=fresh(), copy=structuredClone(r); parse(r); select(r,['B']); assert.deepEqual(r,copy); });
for (const [name, mutate] of [
  ['orphan row ID', r=>r.datasets[0].applicable_file_row_ids.push('missing')],
  ['cross-dataset row substitution',r=>r.datasets[0].applicable_file_row_ids=['B:0']],
  ['file omission', r=>r.datasets[0].all_row_ids.pop()],
  ['duplicate summary', r=>r.datasets.push(structuredClone(r.datasets[0]))],
  ['dataset omission', r=>r.datasets.pop()],
  ['unknown recommended dataset', r=>r.recommended_dataset_ids.push('D')],
  ['wrong unresolved list', r=>r.unresolved_dataset_ids.push('A')],
  ['wrong processing-only list', r=>r.processing_only_dataset_ids.push('A')],
  ['count mismatch', r=>r.datasets[0].counts.applicable_files++],
  ['bad estimate', r=>r.datasets[0].known_applicable_bytes++],
  ['bad unknown size count', r=>r.datasets[0].unknown_applicable_sizes++],
  ['false equivalence', r=>r.source_equivalence='PASS'],
  ['fetch capability', r=>r.fetch_enabled=true],
  ['wrong AOI binding', r=>r.aoi_sha256='0'.repeat(64)],
  ['wrong registry binding', r=>r.registry_sha256='0'.repeat(64)],
  ['unsafe source URL', r=>r.plan.assets[0].source_url='javascript:alert(1)'],
  ['empty recommendation promotion', r=>{r.datasets[2].recommended=true;r.recommended_dataset_ids.push('C');}],
  ['false complete list', r=>r.datasets[0].file_resolution_state='UNRESOLVED'],
  ['duplicate catalog', r=>r.plan.catalogs.push(structuredClone(r.plan.catalogs[0]))],
  ['catalog count mismatch', r=>r.plan.catalogs[0].records++],
  ['summary hash mismatch', r=>r.datasets[0].catalog_sha256='0'.repeat(64)],
  ['nonarea file required', r=>r.plan.assets[0].processing_relation='TOUCH_ONLY'],
  ['state partition mismatch', r=>r.counts.dataset_states.RECOMMENDED++],
  ['global count mismatch', r=>r.counts.file_rows_examined++],
]) test(name, () => { const r=fresh(); mutate(r); assert.throws(()=>parse(r)); });
for (const ids of [['D'],['C'],['A','A']]) test(`reject stale/nonrecommended selection ${ids}`,()=>assert.throws(()=>select(parse(fresh()),ids)));
test('source URL rejects embedded credentials',()=>assert.equal(sourceUrl({source_url:'https://user:pass@example.invalid/a.tif'}),null));
test('source URL preserves published string',()=>assert.equal(sourceUrl({source_url:'https://example.invalid/A/a.tif'}),'https://example.invalid/A/a.tif'));
