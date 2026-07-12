import fs from 'node:fs/promises';
import { buildUnstructuredMeshGeometry } from '../onga_stage15_unstructured_mesh_geometry.mjs';
import {
  STAGE15_PRODUCTION_MESH_AUDIT_VERSION,
  auditLoadedProductionMesh,
} from '../onga_stage15_production_mesh_audit.mjs';

const outputPath = process.argv[2] || 'stage15-production-mesh-audit-validation.json';

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

function loadedFromGeometry(vertices, triangles, boundarySegments, version = 'synthetic') {
  const geometry = buildUnstructuredMeshGeometry({ vertices, triangles, boundarySegments });
  return {
    manifest: { version },
    counts: {
      vertices: geometry.vertices.length,
      triangles: geometry.cells.length,
      interiorFaces: geometry.interiorFaces.length,
      boundaryFaces: geometry.boundaryFaces.length,
    },
    vertices: geometry.vertices.map(row => [...row]),
    triangles: triangles.map(row => [...row]),
    interiorFaces: geometry.interiorFaces.map(face => [
      face.vertices[0], face.vertices[1], face.leftCell, face.rightCell,
      face.length, face.centreDistance, face.midpoint[0], face.midpoint[1],
    ]),
    boundaryFaces: geometry.boundaryFaces.map(face => [
      face.vertices[0], face.vertices[1], face.cell,
      face.length, face.midpoint[0], face.midpoint[1], face.marker,
    ]),
  };
}

const vertices = [[0, 0], [2, 0], [2, 1], [0, 1]];
const triangles = [[0, 1, 2], [0, 2, 3]];
const boundarySegments = [[0, 1, 1], [1, 2, 2], [2, 3, 3], [3, 0, 4]];
const loaded = loadedFromGeometry(vertices, triangles, boundarySegments, 'two-triangle-rectangle');
const audit = auditLoadedProductionMesh(loaded);

const alteredLength = structuredClone(loaded);
alteredLength.interiorFaces[0][4] *= 1.01;
const alteredAudit = auditLoadedProductionMesh(alteredLength);

const alteredCells = structuredClone(loaded);
alteredCells.interiorFaces[0][2] = alteredCells.interiorFaces[0][3];
const alteredCellAudit = auditLoadedProductionMesh(alteredCells);

const disconnected = loadedFromGeometry(
  [[0, 0], [1, 0], [0, 1], [3, 0], [4, 0], [3, 1]],
  [[0, 1, 2], [3, 4, 5]],
  [[0, 1, 'a'], [1, 2, 'b'], [2, 0, 'c'], [3, 4, 'd'], [4, 5, 'e'], [5, 3, 'f']],
  'disconnected-two-triangle',
);
const disconnectedAudit = auditLoadedProductionMesh(disconnected);

const failedCheckCount = report => report.checks.filter(item => !item.ok).length;
const checks = [
  check('valid synthetic mesh passes', audit.status, 'passed', audit.status === 'passed'),
  check('audit version', audit.auditVersion, STAGE15_PRODUCTION_MESH_AUDIT_VERSION,
    audit.auditVersion === STAGE15_PRODUCTION_MESH_AUDIT_VERSION),
  check('connected component count', audit.diagnostics.components, 1,
    audit.diagnostics.components === 1),
  check('altered interior length fails', alteredAudit.status, 'failed', alteredAudit.status === 'failed'),
  check('altered interior length reports check failure', failedCheckCount(alteredAudit), '>=1',
    failedCheckCount(alteredAudit) >= 1),
  check('altered cell pair fails', alteredCellAudit.status, 'failed', alteredCellAudit.status === 'failed'),
  check('disconnected mesh fails', disconnectedAudit.status, 'failed', disconnectedAudit.status === 'failed'),
  check('disconnected component count', disconnectedAudit.diagnostics.components, 2,
    disconnectedAudit.diagnostics.components === 2),
];

const report = {
  schema: 'onga-stage15-production-mesh-audit-validation-v1',
  moduleVersion: STAGE15_PRODUCTION_MESH_AUDIT_VERSION,
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  checks,
  safeguards: {
    productionMeshIncludedInCi: false,
    publicRuntimeConnected: false,
    modifiesApprovedWaterGeometry: false,
    physicalValuesAssigned: false,
  },
};

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
