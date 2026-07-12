import fs from 'node:fs/promises';
import { rusanovFlux } from '../onga_stage15_shallow_water_flux_core.mjs';
import {
  accumulateWellBalancedResidual,
  applyManningFriction,
  hydrostaticFaceFlux,
  totalVolume,
} from '../onga_stage15_well_balanced_sources.mjs';

const outputPath = process.argv[2] || 'stage15-well-balanced-validation.json';
const tolerance = 1e-10;

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

function maximumAbsolute(...values) {
  let maximum = 0;
  const visit = value => {
    if (Array.isArray(value) || ArrayBuffer.isView(value)) {
      for (const entry of value) visit(entry);
      return;
    }
    const numeric = Math.abs(Number(value));
    if (Number.isNaN(numeric)) throw new TypeError('maximumAbsolute received a nonnumeric value');
    maximum = Math.max(maximum, numeric);
  };
  for (const value of values) visit(value);
  return maximum;
}

const lake = accumulateWellBalancedResidual({
  cellCount: 2,
  faces: [{ left: 0, right: 1, length: 1, nx: 1, ny: 0 }],
  boundaryFaces: [
    { cell: 0, length: 1, nx: -1, ny: 0, type: 'wall' },
    { cell: 0, length: 1, nx: 0, ny: 1, type: 'wall' },
    { cell: 0, length: 1, nx: 0, ny: -1, type: 'wall' },
    { cell: 1, length: 1, nx: 1, ny: 0, type: 'wall' },
    { cell: 1, length: 1, nx: 0, ny: 1, type: 'wall' },
    { cell: 1, length: 1, nx: 0, ny: -1, type: 'wall' },
  ],
  state: { h: [2, 1.5], hu: [0, 0], hv: [0, 0] },
  bedElevation: [0, 0.5],
});
const lakeResidual = maximumAbsolute(
  lake.residual.mass,
  lake.residual.momentumX,
  lake.residual.momentumY,
);

const left = { h: 1.4, hu: 0.6, hv: -0.2 };
const right = { h: 0.9, hu: -0.1, hv: 0.25 };
const homogeneous = rusanovFlux(left, right, 0.6, 0.8);
const flat = hydrostaticFaceFlux(left, right, 0, 0, 0.6, 0.8);
const flatBedError = maximumAbsolute(
  flat.mass - homogeneous.mass,
  flat.leftMomentumX - homogeneous.momentumX,
  flat.leftMomentumY - homogeneous.momentumY,
  flat.rightMomentumX - homogeneous.momentumX,
  flat.rightMomentumY - homogeneous.momentumY,
);

const shifted = hydrostaticFaceFlux(left, right, 8.25, 8.25, 0.6, 0.8);
const datumShiftError = maximumAbsolute(
  shifted.mass - flat.mass,
  shifted.leftMomentumX - flat.leftMomentumX,
  shifted.leftMomentumY - flat.leftMomentumY,
  shifted.rightMomentumX - flat.rightMomentumX,
  shifted.rightMomentumY - flat.rightMomentumY,
);

const internal = accumulateWellBalancedResidual({
  cellCount: 3,
  faces: [
    { left: 0, right: 1, length: 2, nx: 1, ny: 0 },
    { left: 1, right: 2, length: 1.3, nx: 0.4, ny: Math.sqrt(0.84) },
  ],
  state: {
    h: [1.2, 0.6, 1.8],
    hu: [0.2, -0.1, 0.3],
    hv: [0.05, 0.2, -0.15],
  },
  bedElevation: [0.2, 0.8, -0.1],
});
const internalMassError = Math.abs(
  [...internal.residual.mass].reduce((sum, value) => sum + value, 0),
);

const dry = hydrostaticFaceFlux(
  { h: 0, hu: 4, hv: -2 },
  { h: 0.7, hu: 0.1, hv: 0 },
  1.2,
  0,
  1,
  0,
);
const dryFinite = [
  dry.mass,
  dry.leftMomentumX,
  dry.leftMomentumY,
  dry.rightMomentumX,
  dry.rightMomentumY,
  dry.signalSpeed,
].every(Number.isFinite);
const reconstructedNonnegative = dry.reconstruction.left.h >= 0 && dry.reconstruction.right.h >= 0;

const frictionState = { h: [2, 1], hu: [4, 0], hv: [3, 0] };
const areas = [5, 7];
const volumeBefore = totalVolume(frictionState, areas);
const friction = applyManningFriction(frictionState, [0.03, 0.03], 10);
const volumeAfter = totalVolume(friction, areas);
const momentumBefore = Math.hypot(frictionState.hu[0], frictionState.hv[0]);
const momentumAfter = Math.hypot(friction.hu[0], friction.hv[0]);
const directionError = Math.abs(friction.hu[0] / friction.hv[0] - 4 / 3);
const volumeError = Math.abs(volumeAfter - volumeBefore);
const zeroMomentumError = Math.hypot(friction.hu[1], friction.hv[1]);

const noFriction = applyManningFriction(frictionState, 0, 100);
const zeroRoughnessError = maximumAbsolute(
  noFriction.h.map((value, index) => value - frictionState.h[index]),
  noFriction.hu.map((value, index) => value - frictionState.hu[index]),
  noFriction.hv.map((value, index) => value - frictionState.hv[index]),
);

const timeBoundary = accumulateWellBalancedResidual({
  cellCount: 1,
  faces: [],
  boundaryFaces: [{
    id: 'time-state',
    cell: 0,
    length: 1,
    nx: 1,
    ny: 0,
    type: 'state',
    state: time => ({ h: 1 + time, hu: 0, hv: 0 }),
    bed: time => 0.5 * time,
  }],
  state: { h: [1], hu: [0], hv: [0] },
  bedElevation: [0],
  time: 2,
});
const timeBoundaryError = maximumAbsolute(
  timeBoundary.boundaryFluxes[0].ghost.state.h - 3,
  timeBoundary.boundaryFluxes[0].ghost.bed - 1,
);

const checks = [
  check('lake at rest over bed step', lakeResidual, `<${tolerance}`, lakeResidual < tolerance),
  check('flat-bed equivalence', flatBedError, `<${tolerance}`, flatBedError < tolerance),
  check('vertical datum invariance', datumShiftError, `<${tolerance}`, datumShiftError < tolerance),
  check('internal mass conservation', internalMassError, `<${tolerance}`, internalMassError < tolerance),
  check('dry-state finite reconstruction', dryFinite, true, dryFinite),
  check('reconstructed depth nonnegative', reconstructedNonnegative, true, reconstructedNonnegative),
  check('Manning momentum decreases', momentumAfter, `<${momentumBefore}`, momentumAfter < momentumBefore),
  check('Manning direction preserved', directionError, `<${tolerance}`, directionError < tolerance),
  check('Manning volume preserved', volumeError, `<${tolerance}`, volumeError < tolerance),
  check('zero momentum remains zero', zeroMomentumError, `<${tolerance}`, zeroMomentumError < tolerance),
  check('zero roughness unchanged', zeroRoughnessError, `<${tolerance}`, zeroRoughnessError < tolerance),
  check('time-dependent boundary state and bed', timeBoundaryError, `<${tolerance}`, timeBoundaryError < tolerance),
];

const report = {
  schema: 'onga-stage15-well-balanced-validation-v1',
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  diagnostics: {
    lakeResidual,
    flatBedError,
    datumShiftError,
    internalMassError,
    momentumBefore,
    momentumAfter,
    directionError,
    volumeError,
    zeroRoughnessError,
    timeBoundaryError,
  },
  safeguards: {
    syntheticBathymetryOnly: true,
    actualBathymetryAssigned: false,
    actualManningRoughnessAssigned: false,
    connectedToPublicSimulator: false,
    approvedWaterGeometryChanged: false,
    physicalValuesAssigned: false,
    calibrationPerformed: false,
  },
  checks,
};

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
