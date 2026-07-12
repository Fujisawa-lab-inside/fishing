import fs from 'node:fs/promises';
import {
  advanceEuler as advanceRawEuler,
  estimateCflDt,
} from '../onga_stage15_shallow_water_flux_core.mjs';
import {
  advancePositivityEuler,
  advanceSspRk2,
  buildLimitedResidual,
  totalVolume,
} from '../onga_stage15_positivity_limiter.mjs';

const outputPath = process.argv[2] || 'stage15-positivity-validation.json';
const tolerance = 1e-10;

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

function maximumStateError(left, right) {
  let error = 0;
  for (const key of ['h', 'hu', 'hv']) {
    for (let index = 0; index < left[key].length; index += 1) {
      error = Math.max(error, Math.abs(left[key][index] - right[key][index]));
    }
  }
  return error;
}

const faces = [{ left: 0, right: 1, length: 1, nx: 1, ny: 0 }];
const areas = [1, 1];
const damState = {
  h: new Float64Array([1, 0.1]),
  hu: new Float64Array([0, 0]),
  hv: new Float64Array([0, 0]),
};
const cflDt = estimateCflDt({
  cellCount: 2,
  faces,
  state: damState,
  areas,
  cfl: 0.2,
  minimumDepth: 1e-8,
});
const rawCfl = advanceRawEuler({
  cellCount: 2,
  faces,
  state: damState,
  areas,
  dt: cflDt,
  minimumDepth: 1e-8,
});
const limitedCfl = advancePositivityEuler({
  cellCount: 2,
  faces,
  state: damState,
  areas,
  dt: cflDt,
  minimumDepth: 1e-8,
});
const inactiveLimiterError = maximumStateError(rawCfl.nextState, limitedCfl.nextState);
const minimumCflAlpha = Math.min(...limitedCfl.limited.limiter.alpha);

const hugeDt = 100;
const huge = advancePositivityEuler({
  cellCount: 2,
  faces,
  state: damState,
  areas,
  dt: hugeDt,
  minimumDepth: 1e-12,
});
const hugeMinimumDepth = Math.min(...huge.nextState.h);
const hugeMassError = Math.abs(totalVolume(huge.nextState, areas) - totalVolume(damState, areas));
const hugeMinimumAlpha = Math.min(...huge.limited.limiter.alpha);

const stageTwo = advanceSspRk2({
  cellCount: 2,
  faces,
  state: damState,
  areas,
  dt: hugeDt,
  minimumDepth: 1e-12,
});
const sspMinimumDepth = Math.min(...stageTwo.nextState.h);
const sspMassError = Math.abs(totalVolume(stageTwo.nextState, areas) - totalVolume(damState, areas));

const zero = advanceSspRk2({
  cellCount: 3,
  faces: [
    { left: 0, right: 1, length: 1, nx: 1, ny: 0 },
    { left: 1, right: 2, length: 1, nx: 1, ny: 0 },
  ],
  state: { h: [0, 0, 0], hu: [0, 0, 0], hv: [0, 0, 0] },
  areas: [1, 1, 1],
  dt: 500,
});
const zeroError = Math.max(
  ...zero.nextState.h.map(Math.abs),
  ...zero.nextState.hu.map(Math.abs),
  ...zero.nextState.hv.map(Math.abs),
);

const boundary = advancePositivityEuler({
  cellCount: 1,
  faces: [],
  boundaryFaces: [{
    cell: 0,
    length: 2,
    nx: 1,
    ny: 0,
    type: 'state',
    state: { h: 0, hu: 0, hv: 0 },
  }],
  state: { h: [0.5], hu: [1.5], hv: [0] },
  areas: [3],
  dt: 100,
  minimumDepth: 1e-12,
});
const boundaryMinimumDepth = boundary.nextState.h[0];
const boundaryAlpha = boundary.limited.limiter.alpha[0];
const initialBoundaryVolume = 0.5 * 3;
const removedBoundaryVolume = 100 * boundary.limited.boundaryFluxes[0].integratedMass;
const boundaryVolumeError = Math.abs(removedBoundaryVolume - initialBoundaryVolume);

const sink = advancePositivityEuler({
  cellCount: 1,
  faces: [],
  state: { h: [1], hu: [0.2], hv: [-0.1] },
  areas: [1],
  dt: 1,
  sources: { mass: [-10], momentumX: [-2], momentumY: [1] },
  minimumDepth: 1e-12,
});
const sinkDepth = sink.nextState.h[0];
const sinkAlpha = sink.limited.limiter.alpha[0];

const syntheticFluxEvaluation = {
  internalFluxes: [
    { left: 0, right: 1, length: 2, mass: 3, momentumX: 4, momentumY: -1 },
    { left: 1, right: 2, length: 1, mass: -2, momentumX: 1, momentumY: 5 },
  ],
  boundaryFluxes: [],
};
const syntheticLimited = buildLimitedResidual({
  cellCount: 3,
  state: { h: [0.2, 0.4, 0.1], hu: [0, 0, 0], hv: [0, 0, 0] },
  areas: [1, 1, 1],
  dt: 10,
  fluxEvaluation: syntheticFluxEvaluation,
});
const limitedInternalConservation = Math.max(
  Math.abs([...syntheticLimited.residual.mass].reduce((sum, value) => sum + value, 0)),
  Math.abs([...syntheticLimited.residual.momentumX].reduce((sum, value) => sum + value, 0)),
  Math.abs([...syntheticLimited.residual.momentumY].reduce((sum, value) => sum + value, 0)),
);

// This is a cell-index relabelling test，not a reflection of the global x-axis．
// Reversing left/right cell ids and the face normal must preserve global momentum signs.
const swapped = advancePositivityEuler({
  cellCount: 2,
  faces: [{ left: 0, right: 1, length: 1, nx: -1, ny: 0 }],
  state: { h: [0.1, 1], hu: [0, 0], hv: [0, 0] },
  areas,
  dt: hugeDt,
  minimumDepth: 1e-12,
});
const relabellingSymmetryError = Math.max(
  Math.abs(swapped.nextState.h[0] - huge.nextState.h[1]),
  Math.abs(swapped.nextState.h[1] - huge.nextState.h[0]),
  Math.abs(swapped.nextState.hu[0] - huge.nextState.hu[1]),
  Math.abs(swapped.nextState.hu[1] - huge.nextState.hu[0]),
  Math.abs(swapped.nextState.hv[0] - huge.nextState.hv[1]),
  Math.abs(swapped.nextState.hv[1] - huge.nextState.hv[0]),
);

const checks = [
  check('limiter inactive below CFL', inactiveLimiterError, `<${tolerance}`, inactiveLimiterError < tolerance),
  check('inactive limiter alpha', Math.abs(minimumCflAlpha - 1), `<${tolerance}`, Math.abs(minimumCflAlpha - 1) < tolerance),
  check('huge-step minimum depth', hugeMinimumDepth, '>=0', hugeMinimumDepth >= 0),
  check('huge-step mass conservation', hugeMassError, `<${tolerance}`, hugeMassError < tolerance),
  check('huge-step limiter activates', hugeMinimumAlpha, '<1', hugeMinimumAlpha < 1),
  check('SSP-RK2 minimum depth', sspMinimumDepth, '>=0', sspMinimumDepth >= 0),
  check('SSP-RK2 mass conservation', sspMassError, `<${tolerance}`, sspMassError < tolerance),
  check('zero state unchanged', zeroError, `<${tolerance}`, zeroError < tolerance),
  check('boundary outflow nonnegative depth', boundaryMinimumDepth, '>=0', boundaryMinimumDepth >= 0),
  check('boundary limiter activates', boundaryAlpha, '<1', boundaryAlpha < 1),
  check('boundary outflow capped at available volume', boundaryVolumeError, `<${tolerance}`, boundaryVolumeError < tolerance),
  check('negative source capped at zero depth', sinkDepth, '>=0', sinkDepth >= 0),
  check('negative source limiter', Math.abs(sinkAlpha - 0.1), `<${tolerance}`, Math.abs(sinkAlpha - 0.1) < tolerance),
  check('limited internal conservation', limitedInternalConservation, `<${tolerance}`, limitedInternalConservation < tolerance),
  check('cell relabelling symmetry', relabellingSymmetryError, `<${tolerance}`, relabellingSymmetryError < tolerance),
];

const report = {
  schema: 'onga-stage15-positivity-validation-v1',
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  diagnostics: {
    cflDt,
    inactiveLimiterError,
    minimumCflAlpha,
    hugeMinimumDepth,
    hugeMassError,
    hugeMinimumAlpha,
    sspMinimumDepth,
    sspMassError,
    zeroError,
    boundaryMinimumDepth,
    boundaryAlpha,
    boundaryVolumeError,
    sinkDepth,
    sinkAlpha,
    limitedInternalConservation,
    relabellingSymmetryError,
  },
  safeguards: {
    connectedToPublicSimulator: false,
    approvedWaterGeometryChanged: false,
    physicalValuesAssigned: false,
    calibrationPerformed: false,
    purpose: 'positivity and SSP verification only',
  },
  checks,
};

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
