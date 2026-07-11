import fs from 'node:fs/promises';

const path = process.argv[2] ?? 'data/onga_unified_spec_v480_candidate_r2.json';
const text = await fs.readFile(path, 'utf8');
const spec = JSON.parse(text);

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(spec.version === 'v4.8.0-candidate-r2', 'version mismatch');
const domain = spec.waterDomain;
assert(Number.isInteger(domain.width) && domain.width > 0, 'invalid width');
assert(Number.isInteger(domain.height) && domain.height > 0, 'invalid height');
assert(Array.isArray(domain.rows) && domain.rows.length === domain.height, 'row count mismatch');

let pixelCount = 0;
let previousEnd = -1;
for (let y = 0; y < domain.rows.length; y += 1) {
  const runs = domain.rows[y];
  assert(Array.isArray(runs) && runs.length % 2 === 0, `invalid runs at row ${y}`);
  previousEnd = -1;
  for (let i = 0; i < runs.length; i += 2) {
    const x0 = runs[i];
    const x1 = runs[i + 1];
    assert(Number.isInteger(x0) && Number.isInteger(x1), `non-integer run at row ${y}`);
    assert(0 <= x0 && x0 <= x1 && x1 < domain.width, `out-of-range run at row ${y}`);
    assert(x0 > previousEnd, `overlapping or unsorted run at row ${y}`);
    pixelCount += x1 - x0 + 1;
    previousEnd = x1;
  }
}

assert(pixelCount === domain.pixelCount, `pixel count mismatch: ${pixelCount} != ${domain.pixelCount}`);
assert(pixelCount === 679791, `approved water pixel count mismatch: ${pixelCount}`);
assert(spec.acceptanceCriteria?.runtimeDomainDifferenceCells === 0, 'runtime difference criterion is not zero');
assert(spec.acceptanceCriteria?.controlPointSemanticMismatchCount === 0, 'control-point mismatch criterion is not zero');
assert(spec.acceptanceCriteria?.fishwayInsideWater === true, 'fishway must be inside water');

console.log(JSON.stringify({
  ok: true,
  version: spec.version,
  width: domain.width,
  height: domain.height,
  pixelCount,
  rows: domain.rows.length,
}, null, 2));