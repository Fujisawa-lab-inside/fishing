import fs from 'node:fs/promises';
import {
  STAGE14_CORE_VERSION,
  accumulateCellResidual,
  computeInternalFluxes,
  maxAbs,
  reverseField,
  sum,
} from '../onga_stage14_conservative_flux_core.mjs';

const outputPath = process.argv[2] || 'stage14-conservative-core-validation.json';
const tolerance = 1e-12;

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

const cellCount = 6;
const edges = [
  { left: 0, right: 1, transmissibility: 1.2 },
  { left: 1, right: 2, transmissibility: 0.8 },
  { left: 2, right: 3, transmissibility: 1.1 },
  { left: 3, right: 4, transmissibility: 0.9 },
  { left: 4, right: 5, transmissibility: 1.3 },
  { left: 1, right: 4, transmissibility: 0.4 },
];

const constantField = Array(cellCount).fill(2.75);
const constantResidual = accumulateCellResidual({ cellCount, edges, field: constantField });

const field = [0.1, 0.3, 0.55, 0.7, 0.85, 0.95];
const reversedField = reverseField(field, 1);
const flux = computeInternalFluxes({ cellCount, edges, field });
const reversedFlux = computeInternalFluxes({ cellCount, edges, field: reversedField });
const reversalError = Math.max(...flux.map((edge, index) => (
  Math.abs(edge.fluxLeftToRight + reversedFlux[index].fluxLeftToRight)
)));

const residual = accumulateCellResidual({ cellCount, edges, field });
const internalMassError = Math.abs(sum(residual));

const sources = [0.4, 0, 0, 0, 0, -0.4];
const sourceResidual = accumulateCellResidual({ cellCount, edges, field, sources });
const sourceBalanceError = Math.abs(sum(sources));
const globalResidualBalance = Math.abs(sum(sourceResidual));

const closedEdges = edges.map((edge, index) => (
  index === 2 ? { ...edge, transmissibility: 0 } : edge
));
const closedFlux = computeInternalFluxes({ cellCount, edges: closedEdges, field });
const closedInterfaceFlux = Math.abs(closedFlux[2].fluxLeftToRight);

const checks = [
  check('constant field residual', maxAbs(constantResidual), `<${tolerance}`, maxAbs(constantResidual) < tolerance),
  check('internal mass conservation', internalMassError, `<${tolerance}`, internalMassError < tolerance),
  check('field reversal flux error', reversalError, `<${tolerance}`, reversalError < tolerance),
  check('balanced source sum', sourceBalanceError, `<${tolerance}`, sourceBalanceError < tolerance),
  check('global residual balance with sources', globalResidualBalance, `<${tolerance}`, globalResidualBalance < tolerance),
  check('closed interface flux', closedInterfaceFlux, `<${tolerance}`, closedInterfaceFlux < tolerance),
];

const report = {
  schema: 'onga-stage14-conservative-core-validation-v1',
  coreVersion: STAGE14_CORE_VERSION,
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  checks,
  safeguards: {
    connectedToPublicSimulator: false,
    usesApprovedWaterGeometry: false,
    usesPhysicalBoundaryValues: false,
    calibrationPerformed: false,
    purpose: 'synthetic verification of conservation algebra only',
  },
};

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
