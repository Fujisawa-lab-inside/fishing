import fs from 'node:fs/promises';
import { generateInferenceEnsemble, loadPrior } from '../onga_stage18_inference_ensemble.mjs';
import { aggregateEnsembleResults, quantile, circularAgreement } from '../onga_stage18_ensemble_statistics.mjs';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function close(actual, expected, tolerance = 1e-12) {
  assert(Math.abs(actual - expected) <= tolerance, `expected ${expected}, got ${actual}`);
}

const prior = await loadPrior();
const ensemble = generateInferenceEnsemble(prior, { count: 16, seed: 20260713 });
const cellCount = 4;

const results = ensemble.cases.map((entry, caseIndex) => ({
  schema: 'onga-stage18-case-result-v1',
  caseId: entry.caseId,
  status: 'completed',
  massBalanceError: (caseIndex - 7.5) * 1e-10,
  cells: Array.from({ length: cellCount }, (_, cellId) => {
    const angle = cellId === 0 ? 0 : cellId === 1 ? Math.PI / 2 : cellId === 2 ? Math.PI : caseIndex * Math.PI / 8;
    const speed = 0.1 * (caseIndex + 1) + 0.01 * cellId;
    const wet = cellId !== 3 || caseIndex % 4 !== 0;
    return {
      cellId,
      waterDepthM: wet ? 1 + 0.05 * caseIndex + 0.1 * cellId : 0,
      velocityUms: wet ? speed * Math.cos(angle) : 0,
      velocityVms: wet ? speed * Math.sin(angle) : 0,
      wet,
    };
  }),
}));

const statistics = aggregateEnsembleResults(ensemble, results, { cellCount, minimumCompletedFraction: 1 });
assert(statistics.schema === 'onga-stage18-ensemble-statistics-v1', 'statistics schema mismatch');
assert(statistics.completedCaseCount === 16, 'completed case count mismatch');
assert(statistics.failedCaseCount === 0, 'unexpected failed cases');
assert(statistics.cells.length === cellCount, 'statistics cell count mismatch');
close(statistics.cells[0].flowDirectionAgreementFraction, 1);
close(statistics.cells[1].flowDirectionAgreementFraction, 1);
close(statistics.cells[2].flowDirectionAgreementFraction, 1);
close(statistics.cells[3].wetProbability, 0.75);
assert(statistics.cells[3].flowDirectionAgreementFraction < 0.2, 'rotating direction should have low agreement');
assert(statistics.diagnostics.physicalValidationClaimAllowed === false, 'validation claim safeguard changed');
assert(statistics.diagnostics.publicSimulatorConnectionAllowed === false, 'public connection safeguard changed');
assert(statistics.geometry.approvedWaterPixelCount === 679791, 'water geometry changed');
assert(statistics.geometry.metricMeshCellCount === 50333, 'mesh changed');

close(quantile([0, 10, 20, 30], 0.5), 15);
const opposite = circularAgreement([{ u: 1, v: 0 }, { u: -1, v: 0 }]);
close(opposite.fraction, 0, 1e-10);

const withFailure = results.map(item => structuredClone(item));
withFailure[0] = {
  schema: 'onga-stage18-case-result-v1',
  caseId: ensemble.cases[0].caseId,
  status: 'failed',
  failureReason: 'synthetic divergence fixture',
};
const partial = aggregateEnsembleResults(ensemble, withFailure, { cellCount, minimumCompletedFraction: 0.9 });
assert(partial.completedCaseCount === 15, 'failed case exclusion mismatch');
assert(partial.failedCaseCount === 1, 'failed case diagnostic mismatch');

let insufficientRejected = false;
try {
  aggregateEnsembleResults(ensemble, withFailure.slice(0, 8), { cellCount, minimumCompletedFraction: 0.8 });
} catch (error) {
  insufficientRejected = /insufficient completed-case fraction/.test(String(error));
}
assert(insufficientRejected, 'insufficient ensemble completion must be rejected');

let duplicateRejected = false;
try {
  aggregateEnsembleResults(ensemble, [results[0], results[0], ...results.slice(2)], { cellCount });
} catch (error) {
  duplicateRejected = /duplicate caseId/.test(String(error));
}
assert(duplicateRejected, 'duplicate case IDs must be rejected');

const report = {
  schema: 'onga-stage18-ensemble-statistics-validation-v1',
  status: 'passed',
  completedCaseCount: statistics.completedCaseCount,
  cellCount,
  verified: [
    'median and quantile aggregation',
    'wet probability',
    'circular flow-direction agreement',
    'failed-case exclusion with explicit diagnostics',
    'minimum completion threshold',
    'duplicate case rejection',
    'geometry and publication safeguards',
  ],
};
await fs.writeFile('stage18-ensemble-statistics-validation.json', `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify(report));
