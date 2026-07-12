import fs from 'node:fs/promises';
import {
  STAGE14_TRANSIENT_VERSION,
  advanceEuler,
  advanceHeun,
  estimateExplicitStableDt,
  evaluateSemiDiscrete,
  totalMass,
} from '../onga_stage14_transient_boundary_core.mjs';

const outputPath = process.argv[2] || 'stage14-transient-boundary-validation.json';
const tolerance = 1e-11;

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

function integrateHeun(options, finalTime, dt) {
  let field = Float64Array.from(options.field);
  let time = Number(options.time || 0);
  const steps = Math.round((finalTime - time) / dt);
  for (let step = 0; step < steps; step += 1) {
    const result = advanceHeun({ ...options, field, time, dt });
    field = result.nextField;
    time = result.nextTime;
  }
  return field;
}

const constantCase = evaluateSemiDiscrete({
  cellCount: 3,
  edges: [
    { left: 0, right: 1, transmissibility: 1.2 },
    { left: 1, right: 2, transmissibility: 0.8 },
  ],
  field: [2.75, 2.75, 2.75],
  capacities: [1, 1.5, 2],
  boundaries: [
    { id: 'left', cell: 0, type: 'dirichlet', conductance: 0.7, value: 2.75 },
    { id: 'right', cell: 2, type: 'dirichlet', conductance: 0.9, value: 2.75 },
  ],
});
const constantDerivative = Math.max(...constantCase.derivative.map(Math.abs));

const closedOptions = {
  cellCount: 4,
  edges: [
    { left: 0, right: 1, transmissibility: 0.7 },
    { left: 1, right: 2, transmissibility: 1.1 },
    { left: 2, right: 3, transmissibility: 0.8 },
    { left: 0, right: 3, transmissibility: 0.3 },
  ],
  field: [0.1, 0.9, 0.4, 0.7],
  capacities: [1, 1.2, 0.8, 1.5],
  boundaries: [],
};
let closedField = Float64Array.from(closedOptions.field);
const closedInitialMass = totalMass(closedField, closedOptions.capacities);
for (let step = 0; step < 200; step += 1) {
  closedField = advanceHeun({ ...closedOptions, field: closedField, time: step * 0.01, dt: 0.01 }).nextField;
}
const closedMassError = Math.abs(totalMass(closedField, closedOptions.capacities) - closedInitialMass);

const oneCell = advanceEuler({
  cellCount: 1,
  edges: [],
  field: [1],
  capacities: [2],
  boundaries: [{ id: 'outlet', cell: 0, type: 'flux', value: 0.3 }],
  sources: [0.1],
  time: 0,
  dt: 0.5,
});
const oneCellExpected = 0.95;
const oneCellError = Math.abs(oneCell.nextField[0] - oneCellExpected);

const relaxation = {
  cellCount: 1,
  edges: [],
  field: [0],
  capacities: [1],
  boundaries: [{ id: 'level', cell: 0, type: 'dirichlet', conductance: 2, value: 1 }],
  sources: [0],
  time: 0,
};
const exactRelaxation = 1 - Math.exp(-2);
const coarse = integrateHeun(relaxation, 1, 0.1)[0];
const fine = integrateHeun(relaxation, 1, 0.05)[0];
const coarseError = Math.abs(coarse - exactRelaxation);
const fineError = Math.abs(fine - exactRelaxation);
const convergenceRatio = coarseError / fineError;

const originalBoundary = evaluateSemiDiscrete({
  cellCount: 1,
  edges: [],
  field: [0.2],
  capacities: [1],
  boundaries: [{ id: 'reversal', cell: 0, type: 'dirichlet', conductance: 3, value: 0.7 }],
});
const reversedBoundary = evaluateSemiDiscrete({
  cellCount: 1,
  edges: [],
  field: [0.8],
  capacities: [1],
  boundaries: [{ id: 'reversal', cell: 0, type: 'dirichlet', conductance: 3, value: 0.3 }],
});
const boundaryReversalError = Math.abs(
  originalBoundary.boundaryFluxes[0].outwardFlux + reversedBoundary.boundaryFluxes[0].outwardFlux,
);

const openInterface = evaluateSemiDiscrete({
  cellCount: 2,
  edges: [{ left: 0, right: 1, transmissibility: 4 }],
  edgeMultipliers: [1],
  field: [1, 0],
  capacities: [1, 1],
});
const closedInterface = evaluateSemiDiscrete({
  cellCount: 2,
  edges: [{ left: 0, right: 1, transmissibility: 4 }],
  edgeMultipliers: [0],
  field: [1, 0],
  capacities: [1, 1],
});
const closedInterfaceFlux = Math.abs(closedInterface.internalFluxes[0].fluxLeftToRight);
const openInterfaceFlux = Math.abs(openInterface.internalFluxes[0].fluxLeftToRight);

const stableDt = estimateExplicitStableDt({
  cellCount: 2,
  edges: [{ left: 0, right: 1, transmissibility: 1 }],
  capacities: [1, 2],
  boundaries: [{ id: 'left', cell: 0, type: 'dirichlet', conductance: 1, value: 0 }],
  safety: 0.9,
});
const stableDtError = Math.abs(stableDt - 0.45);

const timeDependentFlux = evaluateSemiDiscrete({
  cellCount: 1,
  edges: [],
  field: [0],
  capacities: [1],
  boundaries: [{ id: 'tide', cell: 0, type: 'flux', value: time => Math.sin(time) }],
  time: Math.PI / 2,
});
const timeDependentFluxError = Math.abs(timeDependentFlux.boundaryFluxes[0].outwardFlux - 1);

const checks = [
  check('constant field derivative', constantDerivative, `<${tolerance}`, constantDerivative < tolerance),
  check('closed-domain mass conservation', closedMassError, `<${tolerance}`, closedMassError < tolerance),
  check('prescribed flux and source mass update', oneCellError, `<${tolerance}`, oneCellError < tolerance),
  check('Heun second-order convergence ratio', convergenceRatio, '>3.5', convergenceRatio > 3.5),
  check('boundary reversal flux error', boundaryReversalError, `<${tolerance}`, boundaryReversalError < tolerance),
  check('closed interface flux', closedInterfaceFlux, `<${tolerance}`, closedInterfaceFlux < tolerance),
  check('open interface remains active', openInterfaceFlux, '>0', openInterfaceFlux > 0),
  check('explicit stable dt estimate', stableDtError, `<${tolerance}`, stableDtError < tolerance),
  check('time-dependent flux evaluation', timeDependentFluxError, `<${tolerance}`, timeDependentFluxError < tolerance),
];

const report = {
  schema: 'onga-stage14-transient-boundary-validation-v1',
  transientVersion: STAGE14_TRANSIENT_VERSION,
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  checks,
  diagnostics: {
    exactRelaxation,
    coarse,
    fine,
    coarseError,
    fineError,
    convergenceRatio,
    stableDt,
  },
  safeguards: {
    connectedToPublicSimulator: false,
    usesApprovedWaterGeometry: false,
    usesPhysicalBoundaryValues: false,
    changesLegacyFlowCalculation: false,
    calibrationPerformed: false,
    purpose: 'synthetic verification of transient conservation and boundary algebra only',
  },
};

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
