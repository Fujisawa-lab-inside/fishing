import fs from 'node:fs/promises';
import path from 'node:path';

const inputPath = process.argv[2] ?? 'data/onga_unified_water_manifest_r3.json';
const EARTH_CIRCUMFERENCE_M = 40075016.68557849;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function readJson(filePath) {
  return JSON.parse(await fs.readFile(filePath, 'utf8'));
}

async function loadSpec(filePath) {
  const root = await readJson(filePath);
  if (root.waterDomain?.rows) return root;

  assert(root.schema === 'onga-unified-water-runtime-v2', 'manifest schema mismatch');
  assert(Array.isArray(root.chunks) && root.chunks.length > 0, 'manifest chunks missing');
  assert(root.coordinateSystem?.geographic, 'manifest geographic coordinate system missing');
  assert(root.fishway, 'manifest fishway missing');

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
    coordinateSystem: root.coordinateSystem,
    fishway: root.fishway,
    openBoundaries: root.openBoundaries,
    acceptanceCriteria: root.acceptanceCriteria,
    geometryCorrection: root.geometryCorrection,
    waterDomain: {
      width: root.width,
      height: root.height,
      pixelCount: root.pixelCount,
      rows,
    },
  };
}

function barycentric(point, point0, point1, point2) {
  const [x, y] = point;
  const [x0, y0] = point0;
  const [x1, y1] = point1;
  const [x2, y2] = point2;
  const denominator = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2);
  if (Math.abs(denominator) < 1e-12) return null;
  const weight0 = ((y1 - y2) * (x - x2) + (x2 - x1) * (y - y2)) / denominator;
  const weight1 = ((y2 - y0) * (x - x2) + (x0 - x2) * (y - y2)) / denominator;
  return [weight0, weight1, 1 - weight0 - weight1];
}

function meshMap(point, mesh, sourceField, targetField) {
  for (const triangle of mesh.triangles) {
    const source = triangle.map(index => mesh.anchors[index][sourceField]);
    const weights = barycentric(point, source[0], source[1], source[2]);
    if (!weights) continue;
    if (weights.every(weight => weight >= -1e-7 && weight <= 1 + 1e-7)) {
      const target = triangle.map(index => mesh.anchors[index][targetField]);
      return [
        weights[0] * target[0][0] + weights[1] * target[1][0] + weights[2] * target[2][0],
        weights[0] * target[0][1] + weights[1] * target[1][1] + weights[2] * target[2][1],
      ];
    }
  }
  return [...point];
}

function webMercator(lat, lng) {
  const clamped = Math.max(-85.05112878, Math.min(85.05112878, Number(lat)));
  const sinLat = Math.sin(clamped * Math.PI / 180);
  return [
    (Number(lng) + 180) / 360 * EARTH_CIRCUMFERENCE_M,
    (0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI)) * EARTH_CIRCUMFERENCE_M,
  ];
}

function createLatLngToImagePixel(coordinateSystem) {
  const geographic = coordinateSystem?.geographic;
  const transform = geographic?.transform;
  const mesh = geographic?.controlMesh;
  assert(geographic?.crs === 'EPSG:4326', 'unexpected geographic CRS');
  assert(transform && [transform.a, transform.b, transform.tx, transform.ty].every(Number.isFinite), 'invalid geographic transform');
  assert(Array.isArray(mesh?.anchors) && Array.isArray(mesh?.triangles), 'invalid control mesh');
  const determinant = transform.a * transform.a + transform.b * transform.b;
  assert(determinant > 0, 'zero transform determinant');

  return (lat, lng) => {
    const [worldX, worldY] = webMercator(lat, lng);
    const dx = worldX - transform.tx;
    const dy = worldY - transform.ty;
    const basePixel = [
      (transform.a * dx + transform.b * dy) / determinant,
      (-transform.b * dx + transform.a * dy) / determinant,
    ];
    const [x, y] = meshMap(basePixel, mesh, 'sourceBasePixel', 'targetImagePixel');
    return { x, y };
  };
}

function countComponents(mask, width, height) {
  const visited = new Uint8Array(mask.length);
  const queue = new Int32Array(mask.length);
  let components = 0;
  for (let seed = 0; seed < mask.length; seed += 1) {
    if (!mask[seed] || visited[seed]) continue;
    components += 1;
    let head = 0;
    let tail = 0;
    queue[tail++] = seed;
    visited[seed] = 1;
    while (head < tail) {
      const index = queue[head++];
      const x = index % width;
      const y = Math.floor(index / width);
      const neighbours = [
        x > 0 ? index - 1 : -1,
        x + 1 < width ? index + 1 : -1,
        y > 0 ? index - width : -1,
        y + 1 < height ? index + width : -1,
      ];
      for (const neighbour of neighbours) {
        if (neighbour >= 0 && mask[neighbour] && !visited[neighbour]) {
          visited[neighbour] = 1;
          queue[tail++] = neighbour;
        }
      }
    }
  }
  return components;
}

const spec = await loadSpec(inputPath);
assert(spec.version === 'v4.8.0-candidate-r3', 'version mismatch');
const domain = spec.waterDomain;
assert(Number.isInteger(domain.width) && domain.width > 0, 'invalid width');
assert(Number.isInteger(domain.height) && domain.height > 0, 'invalid height');
assert(Array.isArray(domain.rows) && domain.rows.length === domain.height, 'row count mismatch');

const mask = new Uint8Array(domain.width * domain.height);
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
    mask.fill(1, y * domain.width + x0, y * domain.width + x1 + 1);
    pixelCount += x1 - x0 + 1;
    previousEnd = x1;
  }
}

const contains = (x, y) => {
  const ix = Math.floor(x);
  const iy = Math.floor(y);
  return ix >= 0 && iy >= 0 && ix < domain.width && iy < domain.height
    ? mask[iy * domain.width + ix] === 1
    : false;
};
const latLngToImagePixel = createLatLngToImagePixel(spec.coordinateSystem);
let maxControlPointError = 0;
let controlPointSemanticMismatchCount = 0;
for (const point of spec.coordinateSystem.geographic.controlPoints) {
  const pixel = latLngToImagePixel(point.lat, point.lng);
  maxControlPointError = Math.max(
    maxControlPointError,
    Math.hypot(pixel.x - point.pixel[0], pixel.y - point.pixel[1]),
  );
  const expectedWater = point.semantic === 'water';
  if (contains(pixel.x, pixel.y) !== expectedWater) controlPointSemanticMismatchCount += 1;
}
const fishwayPixel = latLngToImagePixel(spec.fishway.lat, spec.fishway.lng);
const fishwayInsideWater = contains(fishwayPixel.x, fishwayPixel.y);
const waterConnectedComponents = countComponents(mask, domain.width, domain.height);

assert(pixelCount === domain.pixelCount, `pixel count mismatch: ${pixelCount} != ${domain.pixelCount}`);
assert(pixelCount === 680633, `approved water pixel count mismatch: ${pixelCount}`);
assert(JSON.stringify(domain.rows[0]) === JSON.stringify([57, 322]), 'r3 top row mismatch');
assert(JSON.stringify(domain.rows[1]) === JSON.stringify([57, 323]), 'r3 second row mismatch');
assert(spec.geometryCorrection?.id === 'ashiya_bridge_underpass_water_restore_v1',
  'r3 geometry-correction id mismatch');
assert(spec.geometryCorrection?.approvedDate === '2026-07-14', 'r3 approval date mismatch');
assert(spec.geometryCorrection?.sourceStatement === '進めてください', 'r3 approval statement mismatch');
assert(spec.geometryCorrection?.sourceVersion === 'v4.8.0-candidate-r2',
  'r3 geometry-correction source mismatch');
assert(spec.geometryCorrection?.addedPixelCount === 842, 'r3 added-pixel count mismatch');
assert(spec.geometryCorrection?.removedPixelCount === 0, 'r3 must not remove r2 water pixels');
assert(JSON.stringify(spec.geometryCorrection?.changedRowRangeInclusive) === JSON.stringify([0, 34]),
  'r3 changed-row range mismatch');
assert(maxControlPointError <= 0.05, `control-point georeference error: ${maxControlPointError}`);
assert(controlPointSemanticMismatchCount === 0, `control-point semantic mismatch: ${controlPointSemanticMismatchCount}`);
assert(fishwayInsideWater, 'fishway must be inside water');
assert(waterConnectedComponents === 1, `water component count: ${waterConnectedComponents}`);
assert(spec.acceptanceCriteria?.runtimeDomainDifferenceCells === 0, 'runtime difference criterion is not zero');
assert(spec.acceptanceCriteria?.controlPointSemanticMismatchCount === 0, 'control-point mismatch criterion is not zero');
assert(spec.acceptanceCriteria?.fishwayInsideWater === true, 'fishway acceptance criterion must be true');
assert(spec.acceptanceCriteria?.waterConnectedComponents === 1, 'water component acceptance criterion must be one');

console.log(JSON.stringify({
  ok: true,
  version: spec.version,
  width: domain.width,
  height: domain.height,
  pixelCount,
  rows: domain.rows.length,
  waterConnectedComponents,
  maxControlPointError,
  controlPointSemanticMismatchCount,
  fishwayPixel,
  fishwayInsideWater,
}, null, 2));
