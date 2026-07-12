import { buildUnstructuredMeshGeometry } from './onga_stage15_unstructured_mesh_geometry.mjs';

export const STAGE15_PRODUCTION_MESH_AUDIT_VERSION = 'stage15-production-mesh-audit-v1';

function assert(condition, message) {
  if (!condition) throw new Error(`[stage15-production-mesh-audit] ${message}`);
}

function finite(value, label) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) throw new TypeError(`${label} must be finite`);
  return numeric;
}

function edgeKey(a, b) {
  return Number(a) < Number(b) ? `${Number(a)}:${Number(b)}` : `${Number(b)}:${Number(a)}`;
}

function relativeError(left, right) {
  return Math.abs(left - right) / Math.max(1, Math.abs(left), Math.abs(right));
}

function connectedComponentCount(cellCount, interiorFaces) {
  const neighbours = Array.from({ length: cellCount }, () => []);
  for (const face of interiorFaces) {
    neighbours[face.leftCell].push(face.rightCell);
    neighbours[face.rightCell].push(face.leftCell);
  }
  const visited = new Uint8Array(cellCount);
  let components = 0;
  for (let seed = 0; seed < cellCount; seed += 1) {
    if (visited[seed]) continue;
    components += 1;
    const stack = [seed];
    visited[seed] = 1;
    while (stack.length) {
      const cell = stack.pop();
      for (const neighbour of neighbours[cell]) {
        if (visited[neighbour]) continue;
        visited[neighbour] = 1;
        stack.push(neighbour);
      }
    }
  }
  return components;
}

function check(name, value, expected, ok) {
  return Object.freeze({ name, value, expected, ok: Boolean(ok) });
}

export function auditLoadedProductionMesh(loaded, options = {}) {
  const tolerance = finite(options.tolerance ?? 1e-10, 'tolerance');
  assert(tolerance >= 0, 'tolerance must be nonnegative');
  assert(loaded?.counts && Array.isArray(loaded.vertices) && Array.isArray(loaded.triangles),
    'loaded mesh object is incomplete');

  const boundarySegments = loaded.boundaryFaces.map(row => [row[0], row[1], row[6] ?? null]);
  const geometry = buildUnstructuredMeshGeometry({
    vertices: loaded.vertices,
    triangles: loaded.triangles,
    boundarySegments,
  });

  const reconstructedInterior = new Map(
    geometry.interiorFaces.map(face => [edgeKey(face.vertices[0], face.vertices[1]), face]),
  );
  const reconstructedBoundary = new Map(
    geometry.boundaryFaces.map(face => [edgeKey(face.vertices[0], face.vertices[1]), face]),
  );

  let missingInterior = 0;
  let interiorCellMismatch = 0;
  let interiorLengthError = 0;
  let interiorCentreDistanceError = 0;
  let interiorMidpointError = 0;
  const seenInterior = new Set();
  for (const [index, row] of loaded.interiorFaces.entries()) {
    const key = edgeKey(row[0], row[1]);
    const face = reconstructedInterior.get(key);
    if (!face) {
      missingInterior += 1;
      continue;
    }
    if (seenInterior.has(key)) missingInterior += 1;
    seenInterior.add(key);
    const exportedCells = new Set([Number(row[2]), Number(row[3])]);
    if (!exportedCells.has(face.leftCell) || !exportedCells.has(face.rightCell)) interiorCellMismatch += 1;
    interiorLengthError = Math.max(interiorLengthError, relativeError(Number(row[4]), face.length));
    interiorCentreDistanceError = Math.max(
      interiorCentreDistanceError,
      relativeError(Number(row[5]), face.centreDistance),
    );
    interiorMidpointError = Math.max(
      interiorMidpointError,
      Math.hypot(Number(row[6]) - face.midpoint[0], Number(row[7]) - face.midpoint[1]),
    );
  }
  missingInterior += Math.max(0, reconstructedInterior.size - seenInterior.size);

  let missingBoundary = 0;
  let boundaryCellMismatch = 0;
  let boundaryMarkerMismatch = 0;
  let boundaryLengthError = 0;
  let boundaryMidpointError = 0;
  const seenBoundary = new Set();
  for (const row of loaded.boundaryFaces) {
    const key = edgeKey(row[0], row[1]);
    const face = reconstructedBoundary.get(key);
    if (!face) {
      missingBoundary += 1;
      continue;
    }
    if (seenBoundary.has(key)) missingBoundary += 1;
    seenBoundary.add(key);
    if (Number(row[2]) !== face.cell) boundaryCellMismatch += 1;
    if ((row[6] ?? null) !== face.marker) boundaryMarkerMismatch += 1;
    boundaryLengthError = Math.max(boundaryLengthError, relativeError(Number(row[3]), face.length));
    boundaryMidpointError = Math.max(
      boundaryMidpointError,
      Math.hypot(Number(row[4]) - face.midpoint[0], Number(row[5]) - face.midpoint[1]),
    );
  }
  missingBoundary += Math.max(0, reconstructedBoundary.size - seenBoundary.size);

  let triangleSetMismatch = 0;
  for (let index = 0; index < geometry.cells.length; index += 1) {
    const exported = [...loaded.triangles[index]].map(Number).sort((a, b) => a - b).join(':');
    const reconstructed = [...geometry.cells[index].vertices].sort((a, b) => a - b).join(':');
    if (exported !== reconstructed) triangleSetMismatch += 1;
  }

  const components = connectedComponentCount(geometry.cells.length, geometry.interiorFaces);
  const checks = [
    check('vertex count', geometry.vertices.length, loaded.counts.vertices,
      geometry.vertices.length === loaded.counts.vertices),
    check('cell count', geometry.cells.length, loaded.counts.triangles,
      geometry.cells.length === loaded.counts.triangles),
    check('interior face count', geometry.interiorFaces.length, loaded.counts.interiorFaces,
      geometry.interiorFaces.length === loaded.counts.interiorFaces),
    check('boundary face count', geometry.boundaryFaces.length, loaded.counts.boundaryFaces,
      geometry.boundaryFaces.length === loaded.counts.boundaryFaces),
    check('triangle vertex-set mismatch', triangleSetMismatch, 0, triangleSetMismatch === 0),
    check('missing or duplicate interior edges', missingInterior, 0, missingInterior === 0),
    check('interior cell-pair mismatch', interiorCellMismatch, 0, interiorCellMismatch === 0),
    check('interior relative length error', interiorLengthError, `<=${tolerance}`,
      interiorLengthError <= tolerance),
    check('interior relative centre-distance error', interiorCentreDistanceError, `<=${tolerance}`,
      interiorCentreDistanceError <= tolerance),
    check('interior midpoint absolute error', interiorMidpointError, `<=${tolerance}`,
      interiorMidpointError <= tolerance),
    check('missing or duplicate boundary edges', missingBoundary, 0, missingBoundary === 0),
    check('boundary cell mismatch', boundaryCellMismatch, 0, boundaryCellMismatch === 0),
    check('boundary marker mismatch', boundaryMarkerMismatch, 0, boundaryMarkerMismatch === 0),
    check('boundary relative length error', boundaryLengthError, `<=${tolerance}`,
      boundaryLengthError <= tolerance),
    check('boundary midpoint absolute error', boundaryMidpointError, `<=${tolerance}`,
      boundaryMidpointError <= tolerance),
    check('cell graph components', components, 1, components === 1),
    check('positive total area', geometry.totalArea, '>0', geometry.totalArea > 0),
  ];

  return Object.freeze({
    schema: 'onga-stage15-production-mesh-audit-v1',
    auditVersion: STAGE15_PRODUCTION_MESH_AUDIT_VERSION,
    meshVersion: loaded.manifest?.version ?? null,
    status: checks.every(item => item.ok) ? 'passed' : 'failed',
    checks: Object.freeze(checks),
    diagnostics: Object.freeze({
      totalArea: geometry.totalArea,
      totalBoundaryLength: geometry.totalBoundaryLength,
      components,
      markerCount: geometry.markerCount,
    }),
  });
}

export const Stage15ProductionMeshAudit = Object.freeze({
  version: STAGE15_PRODUCTION_MESH_AUDIT_VERSION,
  auditLoadedProductionMesh,
});
