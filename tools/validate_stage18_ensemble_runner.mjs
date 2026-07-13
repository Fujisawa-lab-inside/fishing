import assert from 'node:assert/strict';
import { runEnsemble, reduceEnsembleStatistics, validateEnsembleCases } from '../onga_stage18_ensemble_runner.mjs';

function makeCase(index) {
  return {
    caseId: `case-${String(index).padStart(3, '0')}`,
    seed: 20260713,
    bathymetry: { shape: index % 2 ? 'parabolic' : 'trapezoidal' },
    roughness: { n: 0.025 + index * 0.001 },
    boundary: { M: {}, N: {}, O: {}, G: {} },
    fishway: { mode: index % 3 ? 'head_difference' : 'disabled' },
    barrage: { scenario: index % 2 ? 'uniform_50_percent' : 'fully_closed' }
  };
}

const cases = Array.from({ length: 8 }, (_, index) => makeCase(index));
assert.equal(validateEnsembleCases(cases), true);
assert.throws(() => validateEnsembleCases([cases[0], cases[0]]), /duplicate caseId/);

async function syntheticSolver(scenario, policy) {
  assert.equal(policy.physicalValidationClaimAllowed, false);
  assert.equal(policy.visualFittingAllowed, false);
  const i = Number(scenario.caseId.split('-')[1]);
  if (i === 6) throw new Error('synthetic divergence');
  return {
    velocityU: [1 + i * 0.1, -0.5 + i * 0.01, 0],
    velocityV: [0.2, 0.4 - i * 0.02, 0],
    waterDepth: [1.5 + i * 0.01, 0.5, i % 2 ? 0 : 0.2],
    massBalanceError: 1e-12 * (i + 1),
    converged: true,
    cflMax: 0.45 + i * 0.01,
    diagnostics: { synthetic: true }
  };
}

const run = await runEnsemble({ cases, solver: syntheticSolver, concurrency: 3 });
assert.equal(run.caseCountRequested, 8);
assert.equal(run.caseCountCompleted, 8);
assert.equal(run.succeeded, 7);
assert.equal(run.failed, 1);
assert.equal(run.physicalValidationClaimAllowed, false);
assert.equal(run.publicSimulatorConnected, false);
assert.match(run.results.find(r => r.caseId === 'case-006').error, /synthetic divergence/);

const stats = reduceEnsembleStatistics(run);
assert.equal(stats.caseCountUsed, 7);
assert.equal(stats.excludedFailedCaseCount, 1);
assert.equal(stats.cells.length, 3);
assert(stats.cells[0].speedMedian > 1);
assert(stats.cells[0].flowDirectionAgreementFraction === 1);
assert(stats.cells[2].wetProbability > 0 && stats.cells[2].wetProbability < 1);
assert(stats.runDiagnostics.maxAbsoluteMassBalanceError <= 8e-12);

await assert.rejects(
  () => runEnsemble({ cases, solver: syntheticSolver, physicalRunEnabled: true }),
  /physicalRunEnabled/
);
await assert.rejects(
  () => runEnsemble({ cases, solver: syntheticSolver, publicSimulatorConnected: true }),
  /public simulator connection/
);

const invalidDepthRun = await runEnsemble({
  cases: cases.slice(0, 2),
  solver: async () => ({
    velocityU: [0], velocityV: [0], waterDepth: [-1],
    massBalanceError: 0, converged: true, cflMax: 0.1
  })
});
assert.equal(invalidDepthRun.succeeded, 0);
assert.equal(invalidDepthRun.failed, 2);
assert(invalidDepthRun.results.every(result => /negative water depth/.test(result.error)));

console.log(JSON.stringify({
  status: 'passed',
  cases: run.caseCountRequested,
  succeeded: run.succeeded,
  failed: run.failed,
  statisticCellCount: stats.cells.length,
  safeguards: {
    physicalRunEnabled: false,
    publicSimulatorConnected: false,
    physicalValidationClaimAllowed: false
  }
}, null, 2));
