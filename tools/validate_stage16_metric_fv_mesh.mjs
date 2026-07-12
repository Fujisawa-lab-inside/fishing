import fs from 'node:fs/promises';
import { loadMetricFvMesh } from '../onga_stage16_metric_fv_mesh_loader.mjs';

const manifestPath = process.argv[2] || 'data/stage16/onga_fv_metric_mesh_compact_manifest_v1.json';
const sourcePath = process.argv[3] || 'data/onga_stage16_mesh_source_v1.json';
const outputPath = process.argv[4] || 'stage16-metric-mesh-validation.json';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

function at2(values, index) {
  return [values[2 * index], values[2 * index + 1]];
}

function triangleArea(vertices, triangles, cell) {
  const a = at2(vertices, triangles[3 * cell]);
  const b = at2(vertices, triangles[3 * cell + 1]);
  const c = at2(vertices, triangles[3 * cell + 2]);
  return 0.5 * Math.abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]));
}

function edgeLength(vertices, edgeVertices, edge) {
  const a = at2(vertices, edgeVertices[2 * edge]);
  const b = at2(vertices, edgeVertices[2 * edge + 1]);
  return Math.hypot(b[0] - a[0], b[1] - a[1]);
}

function buildCentroids(vertices, triangles, cellCount) {
  const result = new Float64Array(cellCount * 2);
  for (let cell = 0; cell < cellCount; cell += 1) {
    for (let corner = 0; corner < 3; corner += 1) {
      const vertex = triangles[3 * cell + corner];
      result[2 * cell] += vertices[2 * vertex] / 3;
      result[2 * cell + 1] += vertices[2 * vertex + 1] / 3;
    }
  }
  return result;
}

function componentLabels(cellCount, internalCells, removedFaceIds) {
  const removed = new Uint8Array(internalCells.length / 2);
  for (const face of removedFaceIds) removed[face] = 1;
  const adjacency = Array.from({ length: cellCount }, () => []);
  for (let face = 0; face < removed.length; face += 1) {
    if (removed[face]) continue;
    const left = internalCells[2 * face];
    const right = internalCells[2 * face + 1];
    adjacency[left].push(right);
    adjacency[right].push(left);
  }
  const labels = new Int32Array(cellCount);
  labels.fill(-1);
  let component = 0;
  for (let seed = 0; seed < cellCount; seed += 1) {
    if (labels[seed] >= 0) continue;
    labels[seed] = component;
    const queue = [seed];
    for (let head = 0; head < queue.length; head += 1) {
      for (const neighbour of adjacency[queue[head]]) {
        if (labels[neighbour] < 0) {
          labels[neighbour] = component;
          queue.push(neighbour);
        }
      }
    }
    component += 1;
  }
  return { labels, count: component };
}

const source = JSON.parse(await fs.readFile(sourcePath, 'utf8'));
const packageData = await loadMetricFvMesh({ manifestPath });
const manifest = packageData.manifest;
const qLocal = packageData.array('vertexLocalMillimetreXY').values;
const triangles = packageData.array('triangles').values;
const internalVertices = packageData.array('internalFaceVertexIds').values;
const internalCells = packageData.array('internalFaceCells').values;
const boundaryVertices = packageData.array('boundaryFaceVertexIds').values;
const boundaryCells = packageData.array('boundaryFaceCell').values;
const boundaryTags = packageData.array('boundaryFaceTag').values;
const barrageFaces = packageData.array('barrageFaceIds').values;
const gateIds = packageData.array('barrageGateId').values;
const fishwayCells = packageData.array('fishwayCells').values;
const fishwayComponents = packageData.array('fishwayComponents').values;
const metreScale = manifest.quantization.vertexLocalMillimetreXY.scaleToMetre;
const vertices = Float64Array.from(qLocal, value => value * metreScale);
const counts = manifest.counts;

assert(vertices.length === counts.vertices * 2, 'vertex array shape mismatch');
assert(triangles.length === counts.cells * 3, 'triangle array shape mismatch');
assert(internalVertices.length === counts.internalFaces * 2, 'internal face vertex shape mismatch');
assert(internalCells.length === counts.internalFaces * 2, 'internal face cell shape mismatch');
assert(boundaryVertices.length === counts.boundaryFaces * 2, 'boundary face vertex shape mismatch');
assert(boundaryCells.length === counts.boundaryFaces, 'boundary face cell shape mismatch');
assert(boundaryTags.length === counts.boundaryFaces, 'boundary tag shape mismatch');
assert(barrageFaces.length === counts.barrageFaces, 'barrage face shape mismatch');
assert(gateIds.length === counts.barrageFaces, 'gate id shape mismatch');
assert(fishwayCells.length === 2 && fishwayComponents.length === 2, 'fishway mapping shape mismatch');

let minimumArea = Infinity;
let totalArea = 0;
for (let cell = 0; cell < counts.cells; cell += 1) {
  for (let corner = 0; corner < 3; corner += 1) {
    const vertex = triangles[3 * cell + corner];
    assert(vertex >= 0 && vertex < counts.vertices, `cell ${cell} vertex out of range`);
  }
  const area = triangleArea(vertices, triangles, cell);
  assert(area > 0 && Number.isFinite(area), `cell ${cell} area invalid`);
  minimumArea = Math.min(minimumArea, area);
  totalArea += area;
}
const centroids = buildCentroids(vertices, triangles, counts.cells);
let minimumInternalLength = Infinity;
let minimumInternalOrientation = Infinity;
for (let face = 0; face < counts.internalFaces; face += 1) {
  const left = internalCells[2 * face];
  const right = internalCells[2 * face + 1];
  assert(left >= 0 && left < counts.cells && right >= 0 && right < counts.cells && left !== right,
    `internal face ${face} cells invalid`);
  const length = edgeLength(vertices, internalVertices, face);
  assert(length > 0 && Number.isFinite(length), `internal face ${face} length invalid`);
  minimumInternalLength = Math.min(minimumInternalLength, length);
  const a = at2(vertices, internalVertices[2 * face]);
  const b = at2(vertices, internalVertices[2 * face + 1]);
  let nx = (b[1] - a[1]) / length;
  let ny = -(b[0] - a[0]) / length;
  const dx = centroids[2 * right] - centroids[2 * left];
  const dy = centroids[2 * right + 1] - centroids[2 * left + 1];
  if (nx * dx + ny * dy < 0) { nx = -nx; ny = -ny; }
  minimumInternalOrientation = Math.min(minimumInternalOrientation, nx * dx + ny * dy);
}
let minimumBoundaryLength = Infinity;
let minimumBoundaryOrientation = Infinity;
const boundaryCounts = { shoreline: 0, M: 0, N: 0, O: 0, G: 0 };
const tagName = ['shoreline', 'M', 'N', 'O', 'G'];
for (let face = 0; face < counts.boundaryFaces; face += 1) {
  const cell = boundaryCells[face];
  assert(cell >= 0 && cell < counts.cells, `boundary face ${face} cell invalid`);
  const tag = boundaryTags[face];
  assert(tag >= 0 && tag <= 4, `boundary face ${face} tag invalid`);
  boundaryCounts[tagName[tag]] += 1;
  const length = edgeLength(vertices, boundaryVertices, face);
  assert(length > 0 && Number.isFinite(length), `boundary face ${face} length invalid`);
  minimumBoundaryLength = Math.min(minimumBoundaryLength, length);
  const a = at2(vertices, boundaryVertices[2 * face]);
  const b = at2(vertices, boundaryVertices[2 * face + 1]);
  let nx = (b[1] - a[1]) / length;
  let ny = -(b[0] - a[0]) / length;
  const mx = 0.5 * (a[0] + b[0]);
  const my = 0.5 * (a[1] + b[1]);
  const dx = mx - centroids[2 * cell];
  const dy = my - centroids[2 * cell + 1];
  if (nx * dx + ny * dy < 0) { nx = -nx; ny = -ny; }
  minimumBoundaryOrientation = Math.min(minimumBoundaryOrientation, nx * dx + ny * dy);
}

const uniqueBarrage = new Set(barrageFaces);
assert(uniqueBarrage.size === barrageFaces.length, 'duplicate barrage face id');
const gateCounts = Object.fromEntries(Array.from({ length: 8 }, (_, index) => [String(index + 1), 0]));
for (let index = 0; index < barrageFaces.length; index += 1) {
  assert(barrageFaces[index] >= 0 && barrageFaces[index] < counts.internalFaces, 'barrage face out of range');
  assert(gateIds[index] >= 1 && gateIds[index] <= 8, 'gate id out of range');
  gateCounts[String(gateIds[index])] += 1;
}
const components = componentLabels(counts.cells, internalCells, barrageFaces);
assert(components.count === 2, `closed barrage component count ${components.count}`);
assert(components.labels[fishwayCells[0]] === fishwayComponents[0], 'fishway upstream component mismatch');
assert(components.labels[fishwayCells[1]] === fishwayComponents[1], 'fishway downstream component mismatch');
assert(fishwayComponents[0] !== fishwayComponents[1], 'fishway cells are not on opposite components');

const areaRelativeError = Math.abs(totalArea - manifest.geometryDiagnostics.totalAreaM2)
  / manifest.geometryDiagnostics.totalAreaM2;
const checks = [
  check('compressed package hash', manifest.sha256Compressed, source.expectedPackage.sha256Compressed,
    manifest.sha256Compressed === source.expectedPackage.sha256Compressed),
  check('uncompressed package hash', manifest.sha256Uncompressed, source.expectedPackage.sha256Uncompressed,
    manifest.sha256Uncompressed === source.expectedPackage.sha256Uncompressed),
  check('vertex count', counts.vertices, source.expected.vertices, counts.vertices === source.expected.vertices),
  check('cell count', counts.cells, source.expected.cells, counts.cells === source.expected.cells),
  check('internal face count', counts.internalFaces, source.expected.internalFaces,
    counts.internalFaces === source.expected.internalFaces),
  check('boundary face count', counts.boundaryFaces, source.expected.boundaryFaces,
    counts.boundaryFaces === source.expected.boundaryFaces),
  check('minimum quantized cell area', minimumArea, '>0', minimumArea > 0),
  check('quantized total area relative error', areaRelativeError, '<1e-6', areaRelativeError < 1e-6),
  check('minimum internal face length', minimumInternalLength, '>0', minimumInternalLength > 0),
  check('minimum boundary face length', minimumBoundaryLength, '>0', minimumBoundaryLength > 0),
  check('internal normal orientation', minimumInternalOrientation, '>0', minimumInternalOrientation > 0),
  check('boundary normal orientation', minimumBoundaryOrientation, '>0', minimumBoundaryOrientation > 0),
  check('boundary tag counts', JSON.stringify(boundaryCounts), JSON.stringify(manifest.boundaryFaceCounts),
    JSON.stringify(boundaryCounts) === JSON.stringify(manifest.boundaryFaceCounts)),
  check('gate face counts', JSON.stringify(gateCounts), JSON.stringify(manifest.gateFaceCounts),
    JSON.stringify(gateCounts) === JSON.stringify(manifest.gateFaceCounts)),
  check('closed barrage components', components.count, 2, components.count === 2),
  check('fishway opposite components', fishwayComponents[0] !== fishwayComponents[1], true,
    fishwayComponents[0] !== fishwayComponents[1]),
  check('reference sections mapped', Object.values(manifest.referenceSections).every(section => section.uniqueMeshEdgeIds.length > 0),
    true, Object.values(manifest.referenceSections).every(section => section.uniqueMeshEdgeIds.length > 0)),
  check('approved geometry unchanged', manifest.safeguards.approvedWaterGeometryChanged, false,
    manifest.safeguards.approvedWaterGeometryChanged === false),
  check('physical values unassigned', manifest.safeguards.physicalValuesAssigned, false,
    manifest.safeguards.physicalValuesAssigned === false),
];
const report = {
  schema: 'onga-stage16-metric-mesh-validation-v1',
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  manifestPath,
  counts,
  diagnostics: {
    minimumArea,
    totalArea,
    areaRelativeError,
    minimumInternalLength,
    minimumBoundaryLength,
    minimumInternalOrientation,
    minimumBoundaryOrientation,
    boundaryCounts,
    gateCounts,
    closedComponents: components.count,
    fishwayCells: [...fishwayCells],
    fishwayComponents: [...fishwayComponents],
  },
  safeguards: manifest.safeguards,
  checks,
};
await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
