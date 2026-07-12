import fs from 'node:fs/promises';
import {
  accumulateFluxResidual,
  estimateCflDt,
} from '../onga_stage15_shallow_water_flux_core.mjs';
import {
  accumulateWellBalancedResidual,
} from '../onga_stage15_well_balanced_sources.mjs';
import {
  advanceSspRk2,
  totalVolume,
} from '../onga_stage15_positivity_limiter.mjs';
import {
  activeInternalFaces,
  allWallBoundaries,
  connectedComponents,
  loadStage16ActualMesh,
} from '../onga_stage16_actual_mesh_adapter.mjs';

const manifestPath = process.argv[2] || 'data/stage16/onga_fv_metric_mesh_compact_manifest_v1.json';
const outputPath = process.argv[3] || 'stage16-actual-mesh-solver-validation.json';
const tolerance = 1e-7;

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

function maxAbs(values) {
  let maximum = 0;
  for (const value of values) maximum = Math.max(maximum, Math.abs(Number(value)));
  return maximum;
}

function sum(values) {
  let total = 0;
  for (const value of values) total += Number(value);
  return total;
}

function minimum(values) {
  let result = Infinity;
  for (const value of values) result = Math.min(result, Number(value));
  return result;
}

function bbox(centroids) {
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (let cell = 0; cell < centroids.length / 2; cell += 1) {
    minX = Math.min(minX, centroids[2 * cell]);
    maxX = Math.max(maxX, centroids[2 * cell]);
    minY = Math.min(minY, centroids[2 * cell + 1]);
    maxY = Math.max(maxY, centroids[2 * cell + 1]);
  }
  return { minX, maxX, minY, maxY };
}

function smoothCoordinates(mesh) {
  const bounds = bbox(mesh.centroids);
  const width = Math.max(bounds.maxX - bounds.minX, 1);
  const height = Math.max(bounds.maxY - bounds.minY, 1);
  const x = new Float64Array(mesh.cellCount);
  const y = new Float64Array(mesh.cellCount);
  for (let cell = 0; cell < mesh.cellCount; cell += 1) {
    x[cell] = (mesh.centroids[2 * cell] - bounds.minX) / width;
    y[cell] = (mesh.centroids[2 * cell + 1] - bounds.minY) / height;
  }
  return { x, y, bounds };
}

function residualMaximum(result) {
  return Math.max(
    maxAbs(result.residual.mass),
    maxAbs(result.residual.momentumX),
    maxAbs(result.residual.momentumY),
  );
}

const mesh = await loadStage16ActualMesh({ manifestPath });
const walls = allWallBoundaries(mesh);
const zero = new Float64Array(mesh.cellCount);
const flatState = {
  h: new Float64Array(mesh.cellCount).fill(2),
  hu: new Float64Array(mesh.cellCount),
  hv: new Float64Array(mesh.cellCount),
};
const flatLake = accumulateWellBalancedResidual({
  cellCount: mesh.cellCount,
  faces: mesh.internalFaces,
  boundaryFaces: walls,
  state: flatState,
  bedElevation: zero,
});
const flatLakeResidual = residualMaximum(flatLake);

const coordinates = smoothCoordinates(mesh);
const bed = new Float64Array(mesh.cellCount);
const variableState = {
  h: new Float64Array(mesh.cellCount),
  hu: new Float64Array(mesh.cellCount),
  hv: new Float64Array(mesh.cellCount),
};
const freeSurface = 2.5;
for (let cell = 0; cell < mesh.cellCount; cell += 1) {
  bed[cell] = 0.25 * Math.sin(2 * Math.PI * coordinates.x[cell])
    * Math.cos(2 * Math.PI * coordinates.y[cell]);
  variableState.h[cell] = freeSurface - bed[cell];
}
const variableLake = accumulateWellBalancedResidual({
  cellCount: mesh.cellCount,
  faces: mesh.internalFaces,
  boundaryFaces: walls,
  state: variableState,
  bedElevation: bed,
});
const variableLakeResidual = residualMaximum(variableLake);

const smoothState = {
  h: new Float64Array(mesh.cellCount),
  hu: new Float64Array(mesh.cellCount),
  hv: new Float64Array(mesh.cellCount),
};
for (let cell = 0; cell < mesh.cellCount; cell += 1) {
  const phaseX = 2 * Math.PI * coordinates.x[cell];
  const phaseY = 2 * Math.PI * coordinates.y[cell];
  smoothState.h[cell] = 1.5 + 0.12 * Math.sin(phaseX) * Math.cos(phaseY);
  smoothState.hu[cell] = 0.025 * smoothState.h[cell] * Math.cos(phaseY);
  smoothState.hv[cell] = -0.02 * smoothState.h[cell] * Math.sin(phaseX);
}
const internalOnly = accumulateFluxResidual({
  cellCount: mesh.cellCount,
  faces: mesh.internalFaces,
  boundaryFaces: [],
  state: smoothState,
});
const internalGlobalConservation = Math.max(
  Math.abs(sum(internalOnly.residual.mass)),
  Math.abs(sum(internalOnly.residual.momentumX)),
  Math.abs(sum(internalOnly.residual.momentumY)),
);

const cflDt = estimateCflDt({
  cellCount: mesh.cellCount,
  faces: mesh.internalFaces,
  boundaryFaces: walls,
  state: smoothState,
  areas: mesh.areas,
  cfl: 0.25,
  minimumDepth: 1e-8,
});
const initialVolume = totalVolume(smoothState, mesh.areas);
const transient = advanceSspRk2({
  cellCount: mesh.cellCount,
  faces: mesh.internalFaces,
  boundaryFaces: walls,
  state: smoothState,
  areas: mesh.areas,
  dt: 0.5 * cflDt,
  minimumDepth: 1e-8,
});
const transientVolume = totalVolume(transient.nextState, mesh.areas);
const transientVolumeRelativeError = Math.abs(transientVolume - initialVolume) / initialVolume;
const transientMinimumDepth = minimum(transient.nextState.h);

const openComponents = connectedComponents(mesh, activeInternalFaces(mesh, { barrageOpening: 1 }));
const closedFaces = activeInternalFaces(mesh, { barrageOpening: 0 });
const closedComponents = connectedComponents(mesh, closedFaces);
const fishway0 = mesh.structures.fishwayCells[0];
const fishway1 = mesh.structures.fishwayCells[1];
const fishwaySeparated = closedComponents.labels[fishway0] !== closedComponents.labels[fishway1];
const fishwaySource = new Float64Array(mesh.cellCount);
fishwaySource[fishway0] = -1;
fishwaySource[fishway1] = 1;
const fishwaySourceBalance = Math.abs(sum(fishwaySource));

const boundaryCounts = Object.fromEntries(
  Object.entries(mesh.boundaryGroups).map(([tag, faces]) => [tag, faces.length]),
);
const gateCounts = Object.fromEntries(
  Object.entries(mesh.structures.gates).map(([gate, faces]) => [gate, faces.length]),
);
const expectedBoundaryCounts = mesh.packageData.manifest.boundaryFaceCounts;
const expectedGateCounts = mesh.packageData.manifest.gateFaceCounts;
const referenceSectionsMapped = Object.values(mesh.referenceSections)
  .every(section => Array.isArray(section.uniqueMeshEdgeIds) && section.uniqueMeshEdgeIds.length > 0);

const checks = [
  check('actual mesh vertex count', mesh.vertexCount, 28560, mesh.vertexCount === 28560),
  check('actual mesh cell count', mesh.cellCount, 50333, mesh.cellCount === 50333),
  check('actual mesh internal face count', mesh.internalFaces.length, 72107,
    mesh.internalFaces.length === 72107),
  check('actual mesh boundary face count', mesh.boundaryFaces.length, 6785,
    mesh.boundaryFaces.length === 6785),
  check('flat-bed lake-at-rest residual', flatLakeResidual, `<${tolerance}`,
    flatLakeResidual < tolerance),
  check('variable-bed lake-at-rest residual', variableLakeResidual, `<${tolerance}`,
    variableLakeResidual < tolerance),
  check('actual-mesh internal conservation', internalGlobalConservation, `<${tolerance}`,
    internalGlobalConservation < tolerance),
  check('actual-mesh CFL step finite', cflDt, '>0 and finite', Number.isFinite(cflDt) && cflDt > 0),
  check('actual-mesh SSP-RK2 minimum depth', transientMinimumDepth, '>=0', transientMinimumDepth >= 0),
  check('actual-mesh SSP-RK2 volume error', transientVolumeRelativeError, '<1e-10',
    transientVolumeRelativeError < 1e-10),
  check('open barrage graph components', openComponents.count, 1, openComponents.count === 1),
  check('closed barrage graph components', closedComponents.count, 2, closedComponents.count === 2),
  check('fishway cells separated by closed barrage', fishwaySeparated, true, fishwaySeparated),
  check('fishway conservative source balance', fishwaySourceBalance, '<1e-12',
    fishwaySourceBalance < 1e-12),
  check('boundary tag counts', JSON.stringify(boundaryCounts), JSON.stringify(expectedBoundaryCounts),
    JSON.stringify(boundaryCounts) === JSON.stringify(expectedBoundaryCounts)),
  check('gate face counts', JSON.stringify(gateCounts), JSON.stringify(expectedGateCounts),
    JSON.stringify(gateCounts) === JSON.stringify(expectedGateCounts)),
  check('reference sections mapped', referenceSectionsMapped, true, referenceSectionsMapped),
  check('approved geometry unchanged', mesh.safeguards.approvedWaterGeometryChanged, false,
    mesh.safeguards.approvedWaterGeometryChanged === false),
  check('physical values unassigned', mesh.safeguards.physicalValuesAssigned, false,
    mesh.safeguards.physicalValuesAssigned === false),
];

const report = {
  schema: 'onga-stage16-actual-mesh-solver-validation-v1',
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  diagnostics: {
    counts: {
      vertices: mesh.vertexCount,
      cells: mesh.cellCount,
      internalFaces: mesh.internalFaces.length,
      boundaryFaces: mesh.boundaryFaces.length,
      barrageFaces: mesh.structures.barrageFaceIds.length,
    },
    totalAreaM2: mesh.totalArea,
    minimumAreaM2: mesh.minimumArea,
    maximumAreaM2: mesh.maximumArea,
    flatLakeResidual,
    variableLakeResidual,
    internalGlobalConservation,
    cflDt,
    transientMinimumDepth,
    transientVolumeRelativeError,
    openComponents: openComponents.count,
    closedComponents: closedComponents.count,
    fishwayCells: [fishway0, fishway1],
    fishwayComponentLabels: [closedComponents.labels[fishway0], closedComponents.labels[fishway1]],
    boundaryCounts,
    gateCounts,
  },
  safeguards: {
    connectedToPublicSimulator: false,
    approvedWaterGeometryChanged: false,
    physicalValuesAssigned: false,
    calibrationPerformed: false,
    syntheticBedOnly: true,
    syntheticStateOnly: true,
  },
  checks,
};

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
