import fs from 'node:fs/promises';
import {
  advanceBackwardEuler,
  advanceCrankNicolson,
  integrateImplicit,
  totalMass,
} from '../onga_stage14_implicit_integrator.mjs';

const outputPath = process.argv[2] || 'stage14-implicit-validation.json';

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

function relaxation(method, dt, finalTime = 1) {
  let field = new Float64Array([0]);
  let time = 0;
  while (time < finalTime - 1e-14) {
    const step = Math.min(dt, finalTime - time);
    const result = method({
      cellCount: 1,
      edges: [],
      capacities: [1],
      field,
      time,
      dt: step,
      boundaries: [{ cell: 0, type: 'dirichlet', conductance: 2, value: 1 }],
      relativeTolerance: 1e-13,
      absoluteTolerance: 1e-14,
    });
    field = result.nextField;
    time = result.nextTime;
  }
  return Math.abs(field[0] - (1 - Math.exp(-2 * finalTime)));
}

const beCoarse = relaxation(advanceBackwardEuler, 0.2);
const beFine = relaxation(advanceBackwardEuler, 0.1);
const beOrder = Math.log2(beCoarse / beFine);
const cnCoarse = relaxation(advanceCrankNicolson, 0.2);
const cnFine = relaxation(advanceCrankNicolson, 0.1);
const cnOrder = Math.log2(cnCoarse / cnFine);

const cells = 20;
const edges = Array.from({ length: cells - 1 }, (_, left) => ({ left, right: left + 1, transmissibility: 1 }));
const capacities = Float64Array.from({ length: cells }, (_, index) => 1 + 0.05 * index);
const initial = Float64Array.from({ length: cells }, (_, index) => 0.4 + 0.2 * Math.sin(index * 0.4));
const initialMass = totalMass(initial, capacities);
const closed = integrateImplicit({
  cellCount: cells,
  edges,
  capacities,
  field: initial,
  dt: 5,
  steps: 12,
  theta: 0.5,
  boundaries: [],
  relativeTolerance: 1e-11,
  absoluteTolerance: 1e-12,
});
const closedMassError = Math.abs(totalMass(closed.field, capacities) - initialMass);
const initialAmplitude = Math.max(...initial) - Math.min(...initial);
const finalAmplitude = Math.max(...closed.field) - Math.min(...closed.field);

const reversalInitial = [0.15, 0.35, 0.65, 0.85];
const reversalEdges = [
  { left: 0, right: 1, transmissibility: 1 },
  { left: 1, right: 2, transmissibility: 1 },
  { left: 2, right: 3, transmissibility: 1 },
];
const forward = advanceCrankNicolson({
  cellCount: 4,
  edges: reversalEdges,
  capacities: [1, 1, 1, 1],
  field: reversalInitial,
  dt: 0.3,
  boundaries: [
    { cell: 0, type: 'dirichlet', conductance: 1, value: 0.1 },
    { cell: 3, type: 'dirichlet', conductance: 1, value: 0.9 },
  ],
});
const reverse = advanceCrankNicolson({
  cellCount: 4,
  edges: reversalEdges,
  capacities: [1, 1, 1, 1],
  field: reversalInitial.map(value => 1 - value),
  dt: 0.3,
  boundaries: [
    { cell: 0, type: 'dirichlet', conductance: 1, value: 0.9 },
    { cell: 3, type: 'dirichlet', conductance: 1, value: 0.1 },
  ],
});
let reversalError = 0;
for (let cell = 0; cell < 4; cell += 1) {
  reversalError = Math.max(reversalError, Math.abs(reverse.nextField[cell] - (1 - forward.nextField[cell])));
}

const closedInterface = advanceBackwardEuler({
  cellCount: 2,
  edges: [{ left: 0, right: 1, transmissibility: 3 }],
  edgeMultipliers: [0],
  capacities: [1, 1],
  field: [1, 0],
  dt: 100,
  boundaries: [],
});
const closedInterfaceError = Math.max(
  Math.abs(closedInterface.nextField[0] - 1),
  Math.abs(closedInterface.nextField[1]),
);

const timeBoundary = advanceBackwardEuler({
  cellCount: 1,
  edges: [],
  capacities: [1],
  field: [0],
  time: 2,
  dt: 0.5,
  boundaries: [{ cell: 0, type: 'dirichlet', conductance: 2, value: time => time }],
});
const timeBoundaryExpected = (0 + 0.5 * 2 * 2.5) / (1 + 0.5 * 2);
const timeBoundaryError = Math.abs(timeBoundary.nextField[0] - timeBoundaryExpected);

const checks = [
  check('backward Euler order', beOrder, 'approximately 1', beOrder > 0.8 && beOrder < 1.2),
  check('Crank-Nicolson order', cnOrder, 'approximately 2', cnOrder > 1.8 && cnOrder < 2.2),
  check('closed-domain mass conservation', closedMassError, '<1e-9', closedMassError < 1e-9),
  check('large-step amplitude non-growth', finalAmplitude, `<=${initialAmplitude}`, finalAmplitude <= initialAmplitude + 1e-12),
  check('reversal symmetry', reversalError, '<1e-10', reversalError < 1e-10),
  check('closed interface unchanged', closedInterfaceError, '<1e-12', closedInterfaceError < 1e-12),
  check('time-dependent boundary evaluation', timeBoundaryError, '<1e-12', timeBoundaryError < 1e-12),
  check('implicit PCG convergence', timeBoundary.solve.converged, true, timeBoundary.solve.converged),
];

const report = {
  schema: 'onga-stage14-implicit-validation-v1',
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  diagnostics: {
    beCoarse,
    beFine,
    beOrder,
    cnCoarse,
    cnFine,
    cnOrder,
    closedMassError,
    initialAmplitude,
    finalAmplitude,
    reversalError,
    closedInterfaceError,
    timeBoundaryError,
  },
  safeguards: {
    connectedToPublicSimulator: false,
    approvedWaterGeometryChanged: false,
    physicalValuesAssigned: false,
    calibrationPerformed: false,
    purpose: 'implicit time-integration verification only',
  },
  checks,
};

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
