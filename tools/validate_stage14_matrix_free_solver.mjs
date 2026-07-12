import fs from 'node:fs/promises';
import {
  buildSteadySystem,
  computeBoundaryFluxes,
  maxAbs,
  residualVector,
  solvePcg,
} from '../onga_stage14_matrix_free_solver.mjs';

const outputPath = process.argv[2] || 'stage14-pcg-validation.json';
const tolerance = 1e-9;

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

function chainEdges(cellCount, conductance = 1) {
  return Array.from({ length: cellCount - 1 }, (_, left) => ({
    left,
    right: left + 1,
    transmissibility: conductance,
  }));
}

function maxError(actual, expected) {
  let error = 0;
  for (let index = 0; index < actual.length; index += 1) error = Math.max(error, Math.abs(actual[index] - expected[index]));
  return error;
}

const n = 41;
const leftValue = -0.25;
const rightValue = 1.15;
const linearExpected = Float64Array.from({ length: n }, (_, index) => (
  leftValue + (rightValue - leftValue) * (index + 1) / (n + 1)
));
const linearSystem = buildSteadySystem({
  cellCount: n,
  edges: chainEdges(n),
  boundaries: [
    { id: 'left', cell: 0, type: 'dirichlet', conductance: 1, value: leftValue },
    { id: 'right', cell: n - 1, type: 'dirichlet', conductance: 1, value: rightValue },
  ],
});
const linearSolve = solvePcg(linearSystem, { relativeTolerance: 1e-12, absoluteTolerance: 1e-13 });
const linearError = maxError(linearSolve.solution, linearExpected);
const linearResidual = maxAbs(residualVector(linearSystem, linearSolve.solution));

const reversedSystem = buildSteadySystem({
  cellCount: n,
  edges: chainEdges(n),
  boundaries: [
    { id: 'left', cell: 0, type: 'dirichlet', conductance: 1, value: 1 - leftValue },
    { id: 'right', cell: n - 1, type: 'dirichlet', conductance: 1, value: 1 - rightValue },
  ],
});
const reversedSolve = solvePcg(reversedSystem, { relativeTolerance: 1e-12, absoluteTolerance: 1e-13 });
let reversalError = 0;
for (let index = 0; index < n; index += 1) {
  reversalError = Math.max(reversalError, Math.abs(reversedSolve.solution[index] - (1 - linearSolve.solution[index])));
}

const fluxSystem = buildSteadySystem({
  cellCount: 8,
  edges: chainEdges(8, 1.3),
  sources: [1, 0, 0, 0, 0, 0, 0, 0],
  boundaries: [{ id: 'outlet', cell: 7, type: 'flux', value: 1 }],
  anchor: { cell: 0, value: 0 },
});
const fluxSolve = solvePcg(fluxSystem, { relativeTolerance: 1e-12, absoluteTolerance: 1e-13 });
const fluxResidual = maxAbs(residualVector(fluxSystem, fluxSolve.solution));
const boundaryFlux = computeBoundaryFluxes(fluxSystem, fluxSolve.solution)[0].outwardFlux;

const interfaceEdges = chainEdges(6);
const closedMultipliers = new Float64Array(interfaceEdges.length);
closedMultipliers.fill(1);
closedMultipliers[2] = 0;
const closedSystem = buildSteadySystem({
  cellCount: 6,
  edges: interfaceEdges,
  edgeMultipliers: closedMultipliers,
  boundaries: [
    { cell: 0, type: 'dirichlet', conductance: 1, value: 0 },
    { cell: 5, type: 'dirichlet', conductance: 1, value: 1 },
  ],
});
const closedSolve = solvePcg(closedSystem, { relativeTolerance: 1e-12, absoluteTolerance: 1e-13 });
const closedJump = Math.abs(closedSolve.solution[2] - closedSolve.solution[3]);
const closedInterfaceFlux = interfaceEdges[2].transmissibility * closedMultipliers[2]
  * (closedSolve.solution[2] - closedSolve.solution[3]);

let neumannRejected = false;
try {
  buildSteadySystem({
    cellCount: 3,
    edges: chainEdges(3),
    boundaries: [{ cell: 2, type: 'flux', value: 0 }],
  });
} catch (error) {
  neumannRejected = /Dirichlet boundary or anchor/.test(String(error));
}

const denseReferenceSystem = buildSteadySystem({
  cellCount: 2,
  edges: [{ left: 0, right: 1, transmissibility: 1 }],
  boundaries: [
    { cell: 0, type: 'dirichlet', conductance: 2, value: 1 },
    { cell: 1, type: 'dirichlet', conductance: 1, value: 0 },
  ],
});
const denseReference = solvePcg(denseReferenceSystem, { relativeTolerance: 1e-14, absoluteTolerance: 1e-14 });
const denseError = maxError(denseReference.solution, [0.8, 0.4]);

const checks = [
  check('linear profile convergence', linearSolve.converged, true, linearSolve.converged),
  check('linear profile maximum error', linearError, `<${tolerance}`, linearError < tolerance),
  check('linear profile residual', linearResidual, `<${tolerance}`, linearResidual < tolerance),
  check('reversal symmetry', reversalError, `<${tolerance}`, reversalError < tolerance),
  check('flux-boundary convergence', fluxSolve.converged, true, fluxSolve.converged),
  check('flux-boundary residual', fluxResidual, `<${tolerance}`, fluxResidual < tolerance),
  check('prescribed outward flux', boundaryFlux, 1, Math.abs(boundaryFlux - 1) < 1e-14),
  check('closed interface flux', closedInterfaceFlux, 0, closedInterfaceFlux === 0),
  check('closed interface permits discontinuity', closedJump, '>0.5', closedJump > 0.5),
  check('pure Neumann rejected without anchor', neumannRejected, true, neumannRejected),
  check('dense reference error', denseError, `<${tolerance}`, denseError < tolerance),
];

const report = {
  schema: 'onga-stage14-pcg-validation-v1',
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  diagnostics: {
    linearIterations: linearSolve.iterations,
    linearResidual,
    linearError,
    reversalError,
    fluxIterations: fluxSolve.iterations,
    fluxResidual,
    closedJump,
    denseError,
  },
  safeguards: {
    connectedToPublicSimulator: false,
    approvedWaterGeometryChanged: false,
    physicalValuesAssigned: false,
    calibrationPerformed: false,
    purpose: 'matrix-free linear-solver verification only',
  },
  checks,
};

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
