import fs from 'node:fs/promises';
import path from 'node:path';

const inputPath = process.argv[2] ?? 'data/onga_unified_water_manifest_r2.json';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function readJson(filePath) {
  return JSON.parse(await fs.readFile(filePath, 'utf8'));
}

async function loadSpec(filePath) {
  const root = await readJson(filePath);
  if (root.waterDomain?.rows) return root;

  assert(root.schema === 'onga-unified-water-runtime-v1', 'manifest schema mismatch');
  assert(Array.isArray(root.chunks) && root.chunks.length > 0, 'manifest chunks missing');

  const rows = Array.from({ length: root.height }, () => null);
  const baseDir = path.dirname(filePath);
  for (const relativeUrl of root.chunks) {
    const chunkPath = path.resolve(baseDir, relativeUrl.replace(/^\.\/data\//, ''));
    const chunk = await readJson(chunkPath);
    assert(Number.isInteger(chunk.startRow), `invalid startRow in ${chunkPath}`);
    assert(Array.isArray(chunk.rows), `invalid rows in ${chunkPath}`);
    chunk.rows.forEach((runs, offset) => {
      const y = chunk.startRow + offset;
      assert(y >= 0 && y < rows.length, `row ${y} outside manifest height`);
      assert(rows[y] === null, `row ${y} is duplicated`);
      rows[y] = runs;
    });
  }
  assert(rows.every(Array.isArray), 'one or more rows are missing');

  return {
    version: root.version,
    acceptanceCriteria: root.acceptanceCriteria,
    waterDomain: {
      width: root.width,
      height: root.height,
      pixelCount: root.pixelCount,
      rows,
    },
  };
}

const spec = await loadSpec(inputPath);
assert(spec.version === 'v4.8.0-candidate-r2', 'version mismatch');
const domain = spec.waterDomain;
assert(Number.isInteger(domain.width) && domain.width > 0, 'invalid width');
assert(Number.isInteger(domain.height) && domain.height > 0, 'invalid height');
assert(Array.isArray(domain.rows) && domain.rows.length === domain.height, 'row count mismatch');

let pixelCount = 0;
for (let y = 0; y < domain.rows.length; y += 1) {
  const runs = domain.rows[y];
  assert(Array.isArray(runs) && runs.length % 2 === 0, `invalid runs at row ${y}`);
  let previousEnd = -1;
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
assert(spec.acceptanceCriteria?.waterConnectedComponents === 1, 'water domain must be one connected component');

console.log(JSON.stringify({
  ok: true,
  version: spec.version,
  width: domain.width,
  height: domain.height,
  pixelCount,
  rows: domain.rows.length,
}, null, 2));