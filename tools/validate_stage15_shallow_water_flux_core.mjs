import fs from 'node:fs/promises';
import {
  accumulateFluxResidual,
  advanceEuler,
  estimateCflDt,
  physicalNormalFlux,
  reflectiveGhostState,
  rusanovFlux,
  sum,
} from '../onga_stage15_shallow_water_flux_core.mjs';

const outputPath = process.argv[2] || 'stage15-swe-flux-validation.json';
const tolerance = 1e-11;

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

function max3(a, b, c) {
  return Math.max(Math.abs(a), Math.abs(b), Math.abs(c));
}

const equalState = { h: 2, hu: 1.2, hv: -0.4 };
const nx = 0.6;
const ny = 0.8;
const physical = physicalNormalFlux(equalState, nx, ny);
const numerical = rusanovFlux(equalState, equalState, nx, ny);
const consistencyError = max3(
  numerical.mass - physical.mass,
  numerical.momentumX - physical.momentumX,
  numerical.momentumY - physical.momentumY,
);

const internal = accumulateFluxResidual({
  cellCount: 3,
  faces: [
    { left: 0, right: 1, length: 2, nx: 1, ny: 0 },
    { left: 1, right: 2, length: 1.5, nx: 0.3, ny: Math.sqrt(0.91) },
  ],
  state: {
    h: [1.2, 0.8, 1.5],
    hu: [0.4, -0.1, 0.2],
    hv: [0.1, 0.3, -0.2],
  },
});
const internalConservationError = max3(
  sum(internal.residual.mass),
  sum(internal.residual.momentumX),
  sum(internal.residual.momentumY),
);

const lake = accumulateFluxResidual({
  cellCount: 1,
  faces: [],
  boundaryFaces: [
    { cell: 0, length: 1, nx: 1, ny: 0, type: 'wall' },
    { cell: 0, length: 1, nx: -1, ny: 0, type: 'wall' },
    { cell: 0, length: 1, nx: 0, ny: 1, type: 'wall' },
    { cell: 0, length: 1, nx: 0, ny: -1, type: 'wall' },
  ],
  state: { h: [3], hu: [0], hv: [0] },
});
const lakeResidual = max3(
  lake.residual.mass[0],
  lake.residual.momentumX[0],
  lake.residual.momentumY[0],
);

const moving = { h: 2, hu: 3, hv: 0.5 };
const ghost = reflectiveGhostState(moving, 1, 0);
const wallFlux = rusanovFlux(moving, ghost, 1, 0);
const wallMassFlux = Math.abs(wallFlux.mass);

const angle = 0.73;
const cosine = Math.cos(angle);
const sine = Math.sin(angle);
const rotateVector = (x, y) => [cosine * x - sine * y, sine * x + cosine * y];
const left = { h: 1.7, hu: 1.1, hv: -0.2 };
const right = { h: 0.9, hu: -0.15, hv: 0.35 };
const normal = [0.8, 0.6];
const baseFlux = rusanovFlux(left, right, normal[0], normal[1]);
const leftMomentum = rotateVector(left.hu, left.hv);
const rightMomentum = rotateVector(right.hu, right.hv);
const rotatedNormal = rotateVector(normal[0], normal[1]);
const rotatedFlux = rusanovFlux(
  { h: left.h, hu: leftMomentum[0], hv: leftMomentum[1] },
  { h: right.h, hu: rightMomentum[0], hv: rightMomentum[1] },
  rotatedNormal[0],
  rotatedNormal[1],
);
const expectedRotatedMomentum = rotateVector(baseFlux.momentumX, baseFlux.momentumY);
const rotationalError = Math.max(
  Math.abs(rotatedFlux.mass - baseFlux.mass),
  Math.abs(rotatedFlux.momentumX - expectedRotatedMomentum[0]),
  Math.abs(rotatedFlux.momentumY - expectedRotatedMomentum[1]),
);

const forwardState = { h: 1.5, hu: 1.5, hv: -0.3 };
const reversedState = { h: 1.5, hu: -1.5, hv: 0.3 };
const forwardFlux = rusanovFlux(forwardState, forwardState, 0.8, 0.6);
const reversedFlux = rusanovFlux(reversedState, reversedState, 0.8, 0.6);
const reversalMassError = Math.abs(forwardFlux.mass + reversedFlux.mass);
const reversalMomentumError = Math.max(
  Math.abs(forwardFlux.momentumX - reversedFlux.momentumX),
  Math.abs(forwardFlux.momentumY - reversedFlux.momentumY),
);

const periodic = accumulateFluxResidual({
  cellCount: 2,
  faces: [
    { left: 0, right: 1, length: 1, nx: 1, ny: 0 },
    { left: 0, right: 1, length: 1, nx: -1, ny: 0 },
  ],
  state: { h: [1.2, 1.2], hu: [0.6, 0.6], hv: [0.1, 0.1] },
});
const uniformPeriodicResidual = Math.max(
  ...periodic.residual.mass.map(Math.abs),
  ...periodic.residual.momentumX.map(Math.abs),
  ...periodic.residual.momentumY.map(Math.abs),
);

const dryFlux = rusanovFlux({ h: 0, hu: 9, hv: -4 }, { h: 1, hu: 0, hv: 0 }, 1, 0);
const dryFinite = [dryFlux.mass, dryFlux.momentumX, dryFlux.momentumY, dryFlux.signalSpeed]
  .every(Number.isFinite);

const damBreak = {
  h: new Float64Array([1, 0.1]),
  hu: new Float64Array([0, 0]),
  hv: new Float64Array([0, 0]),
};
const damFaces = [{ left: 0, right: 1, length: 1, nx: 1, ny: 0 }];
const damDt = estimateCflDt({
  cellCount: 2,
  faces: damFaces,
  state: damBreak,
  areas: [1, 1],
  cfl: 0.25,
});
const damStep = advanceEuler({
  cellCount: 2,
  faces: damFaces,
  state: damBreak,
  areas: [1, 1],
  dt: damDt,
});
const minimumAdvancedDepth = Math.min(...damStep.nextState.h);
const damMassError = Math.abs(sum(damStep.nextState.h) - sum(damBreak.h));

const timeBoundary = accumulateFluxResidual({
  cellCount: 1,
  faces: [],
  boundaryFaces: [{
    cell: 0,
    length: 1,
    nx: 1,
    ny: 0,
    type: 'state',
    state: time => ({ h: 1 + time, hu: 0, hv: 0 }),
  }],
  state: { h: [1], hu: [0], hv: [0] },
  time: 2,
});
const timeBoundaryError = Math.abs(timeBoundary.boundaryFluxes[0].ghost.h - 3);

const checks = [
  check('equal-state consistency', consistencyError, `<${tolerance}`, consistencyError < tolerance),
  check('internal conservation', internalConservationError, `<${tolerance}`, internalConservationError < tolerance),
  check('lake-at-rest wall balance', lakeResidual, `<${tolerance}`, lakeResidual < tolerance),
  check('reflective-wall mass flux', wallMassFlux, `<${tolerance}`, wallMassFlux < tolerance),
  check('rotational invariance', rotationalError, `<${tolerance}`, rotationalError < tolerance),
  check('velocity reversal mass flux', reversalMassError, `<${tolerance}`, reversalMassError < tolerance),
  check('velocity reversal momentum flux', reversalMomentumError, `<${tolerance}`, reversalMomentumError < tolerance),
  check('uniform periodic preservation', uniformPeriodicResidual, `<${tolerance}`, uniformPeriodicResidual < tolerance),
  check('dry-state finite flux', dryFinite, true, dryFinite),
  check('CFL step positive depth', minimumAdvancedDepth, '>0', minimumAdvancedDepth > 0),
  check('CFL step mass conservation', damMassError, `<${tolerance}`, damMassError < tolerance),
  check('time-dependent boundary state', timeBoundaryError, `<${tolerance}`, timeBoundaryError < tolerance),
];

const report = {
  schema: 'onga-stage15-swe-flux-validation-v1',
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  diagnostics: {
    consistencyError,
    internalConservationError,
    lakeResidual,
    wallMassFlux,
    rotationalError,
    reversalMassError,
    reversalMomentumError,
    uniformPeriodicResidual,
    damDt,
    minimumAdvancedDepth,
    damMassError,
    timeBoundaryError,
  },
  safeguards: {
    homogeneousEquationOnly: true,
    bathymetryAssigned: false,
    frictionAssigned: false,
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
