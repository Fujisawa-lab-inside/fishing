import fs from 'node:fs/promises';
import {
  STAGE15_UNSTRUCTURED_GEOMETRY_VERSION,
  buildUnstructuredMeshGeometry,
  locatePointInMesh,
  toShallowWaterMesh,
} from '../onga_stage15_unstructured_mesh_geometry.mjs';

const outputPath = process.argv[2] || 'stage15-unstructured-mesh-validation.json';
const tolerance = 1e-12;

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

function maxAbs(values) {
  return Math.max(...Array.from(values, value => Math.abs(Number(value))));
}

const vertices = [
  [0, 0],
  [1, 0],
  [1, 1],
  [0, 1],
];
const triangles = [
  [0, 1, 2],
  [0, 3, 2], // clockwise input，which must be corrected
];
const boundarySegments = [
  [0, 1, 'south'],
  [1, 2, 'east'],
  [2, 3, 'north'],
  [3, 0, 'west'],
];

const mesh = buildUnstructuredMeshGeometry({ vertices, triangles, boundarySegments });
const swe = toShallowWaterMesh(mesh);
const interior = mesh.interiorFaces[0];
const interiorNormalLength = Math.hypot(interior.normal[0], interior.normal[1]);
const leftCentroid = mesh.cells[interior.leftCell].centroid;
const rightCentroid = mesh.cells[interior.rightCell].centroid;
const normalDot = interior.normal[0] * (rightCentroid[0] - leftCentroid[0])
  + interior.normal[1] * (rightCentroid[1] - leftCentroid[1]);
const boundaryNormalErrors = mesh.boundaryFaces.map(face => Math.abs(Math.hypot(...face.normal) - 1));
const markerSet = new Set(mesh.boundaryFaces.map(face => face.marker));
const insideA = locatePointInMesh(mesh, 0.75, 0.25);
const insideB = locatePointInMesh(mesh, 0.25, 0.75);
const outside = locatePointInMesh(mesh, 1.2, 0.5);
const barycentricSumError = Math.max(
  Math.abs(insideA.barycentric.reduce((sum, value) => sum + value, 0) - 1),
  Math.abs(insideB.barycentric.reduce((sum, value) => sum + value, 0) - 1),
);
const areaSum = Array.from(swe.areas).reduce((sum, area) => sum + area, 0);

let nonmanifoldRejected = false;
try {
  buildUnstructuredMeshGeometry({
    vertices: [[0, 0], [1, 0], [0, 1], [0, -1], [0.5, 0.5]],
    triangles: [[0, 1, 2], [1, 0, 3], [0, 1, 4]],
  });
} catch (_) {
  nonmanifoldRejected = true;
}

let degenerateRejected = false;
try {
  buildUnstructuredMeshGeometry({
    vertices: [[0, 0], [1, 0], [2, 0]],
    triangles: [[0, 1, 2]],
  });
} catch (_) {
  degenerateRejected = true;
}

let unmatchedMarkerRejected = false;
try {
  buildUnstructuredMeshGeometry({
    vertices,
    triangles,
    boundarySegments: [[0, 2, 'diagonal-is-interior']],
  });
} catch (_) {
  unmatchedMarkerRejected = true;
}

const checks = [
  check('cell count', mesh.cells.length, 2, mesh.cells.length === 2),
  check('interior face count', mesh.interiorFaces.length, 1, mesh.interiorFaces.length === 1),
  check('boundary face count', mesh.boundaryFaces.length, 4, mesh.boundaryFaces.length === 4),
  check('total area', mesh.totalArea, 1, Math.abs(mesh.totalArea - 1) < tolerance),
  check('SWE area sum', areaSum, 1, Math.abs(areaSum - 1) < tolerance),
  check('boundary length', mesh.totalBoundaryLength, 4,
    Math.abs(mesh.totalBoundaryLength - 4) < tolerance),
  check('interior normal unit length', Math.abs(interiorNormalLength - 1), `<${tolerance}`,
    Math.abs(interiorNormalLength - 1) < tolerance),
  check('interior normal left-to-right', normalDot, '>0', normalDot > 0),
  check('boundary normal unit length', maxAbs(boundaryNormalErrors), `<${tolerance}`,
    maxAbs(boundaryNormalErrors) < tolerance),
  check('all boundary markers retained', markerSet.size, 4,
    markerSet.size === 4 && ['south', 'east', 'north', 'west'].every(marker => markerSet.has(marker))),
  check('clockwise triangle corrected', mesh.cells[1].vertices.join(','), '0,2,3',
    mesh.cells[1].vertices.join(',') === '0,2,3'),
  check('point A located', insideA?.cell, 0, insideA?.cell === 0),
  check('point B located', insideB?.cell, 1, insideB?.cell === 1),
  check('outside point rejected', outside, null, outside === null),
  check('barycentric sums', barycentricSumError, `<${tolerance}`,
    barycentricSumError < tolerance),
  check('neighbour symmetry', `${mesh.neighbours[0]}|${mesh.neighbours[1]}`, '1|0',
    mesh.neighbours[0].length === 1 && mesh.neighbours[0][0] === 1
      && mesh.neighbours[1].length === 1 && mesh.neighbours[1][0] === 0),
  check('nonmanifold edge rejected', nonmanifoldRejected, true, nonmanifoldRejected),
  check('degenerate cell rejected', degenerateRejected, true, degenerateRejected),
  check('interior marked as boundary rejected', unmatchedMarkerRejected, true, unmatchedMarkerRejected),
];

const report = {
  schema: 'onga-stage15-unstructured-mesh-validation-v1',
  moduleVersion: STAGE15_UNSTRUCTURED_GEOMETRY_VERSION,
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  checks,
  safeguards: {
    connectedToPublicSimulator: false,
    usesApprovedProductionMeshData: false,
    modifiesApprovedWaterGeometry: false,
    calibrationPerformed: false,
    purpose: 'synthetic verification of unstructured-mesh geometry and topology only',
  },
};

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
