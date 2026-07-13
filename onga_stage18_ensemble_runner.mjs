const REQUIRED_CASE_FIELDS = [
  'caseId', 'seed', 'bathymetry', 'roughness', 'boundary', 'fishway', 'barrage'
];

function finiteNumber(value, label) {
  if (!Number.isFinite(value)) throw new TypeError(`${label} must be finite`);
  return value;
}

function quantile(sorted, p) {
  if (!sorted.length) return NaN;
  const x = (sorted.length - 1) * p;
  const lo = Math.floor(x);
  const hi = Math.ceil(x);
  if (lo === hi) return sorted[lo];
  return sorted[lo] * (hi - x) + sorted[hi] * (x - lo);
}

export function validateEnsembleCases(cases) {
  if (!Array.isArray(cases) || cases.length < 2) {
    throw new Error('ensemble must contain at least two cases');
  }
  const ids = new Set();
  for (const [index, item] of cases.entries()) {
    if (!item || typeof item !== 'object') throw new TypeError(`case ${index} must be an object`);
    for (const field of REQUIRED_CASE_FIELDS) {
      if (!(field in item)) throw new Error(`case ${index} missing ${field}`);
    }
    if (ids.has(item.caseId)) throw new Error(`duplicate caseId ${item.caseId}`);
    ids.add(item.caseId);
  }
  return true;
}

export async function runEnsemble({
  cases,
  solver,
  concurrency = 1,
  failFast = false,
  physicalRunEnabled = false,
  publicSimulatorConnected = false
}) {
  validateEnsembleCases(cases);
  if (typeof solver !== 'function') throw new TypeError('solver callback is required');
  if (physicalRunEnabled) throw new Error('physicalRunEnabled must remain false for inferred ensemble');
  if (publicSimulatorConnected) throw new Error('public simulator connection is forbidden');
  if (!Number.isInteger(concurrency) || concurrency < 1 || concurrency > 16) {
    throw new RangeError('concurrency must be an integer in [1,16]');
  }

  const results = new Array(cases.length);
  let cursor = 0;
  let cancelled = false;

  async function worker() {
    while (!cancelled) {
      const index = cursor++;
      if (index >= cases.length) return;
      const scenario = cases[index];
      const started = Date.now();
      try {
        const output = await solver(scenario, {
          purpose: 'provisional_sensitivity_and_model_development_only',
          physicalValidationClaimAllowed: false,
          visualFittingAllowed: false
        });
        results[index] = validateCaseResult(scenario, output, Date.now() - started);
      } catch (error) {
        results[index] = {
          caseId: scenario.caseId,
          status: 'failed',
          elapsedMs: Date.now() - started,
          error: `${error?.name || 'Error'}: ${error?.message || error}`
        };
        if (failFast) cancelled = true;
      }
    }
  }

  await Promise.all(Array.from({ length: Math.min(concurrency, cases.length) }, () => worker()));
  const completed = results.filter(Boolean);
  return {
    schema: 'onga-stage18-ensemble-run-v1',
    purpose: 'provisional_sensitivity_and_model_development_only',
    caseCountRequested: cases.length,
    caseCountCompleted: completed.length,
    succeeded: completed.filter(r => r.status === 'success').length,
    failed: completed.filter(r => r.status === 'failed').length,
    physicalValidationClaimAllowed: false,
    publicSimulatorConnected: false,
    results: completed
  };
}

export function validateCaseResult(scenario, output, elapsedMs = 0) {
  if (!output || typeof output !== 'object') throw new TypeError('solver output must be an object');
  const { velocityU, velocityV, waterDepth, massBalanceError, converged, cflMax } = output;
  for (const [name, values] of Object.entries({ velocityU, velocityV, waterDepth })) {
    if (!Array.isArray(values) && !ArrayBuffer.isView(values)) {
      throw new TypeError(`${name} must be an array`);
    }
    if (!values.length) throw new Error(`${name} must not be empty`);
    for (const value of values) finiteNumber(Number(value), name);
  }
  if (velocityU.length !== velocityV.length || velocityU.length !== waterDepth.length) {
    throw new Error('field lengths must match');
  }
  if ([...waterDepth].some(value => value < -1e-12)) throw new Error('negative water depth detected');
  finiteNumber(Number(massBalanceError), 'massBalanceError');
  finiteNumber(Number(cflMax), 'cflMax');
  if (converged !== true) throw new Error('case did not converge');

  return {
    caseId: scenario.caseId,
    status: 'success',
    elapsedMs,
    cellCount: velocityU.length,
    velocityU: Array.from(velocityU),
    velocityV: Array.from(velocityV),
    waterDepth: Array.from(waterDepth),
    massBalanceError: Number(massBalanceError),
    cflMax: Number(cflMax),
    diagnostics: output.diagnostics || {}
  };
}

export function reduceEnsembleStatistics(runReport, { dryThreshold = 1e-4 } = {}) {
  if (!runReport || runReport.schema !== 'onga-stage18-ensemble-run-v1') {
    throw new Error('invalid ensemble run report');
  }
  const successful = runReport.results.filter(r => r.status === 'success');
  if (successful.length < 2) throw new Error('at least two successful cases are required');
  const cellCount = successful[0].cellCount;
  if (successful.some(r => r.cellCount !== cellCount)) throw new Error('cell counts differ');

  const cells = [];
  for (let i = 0; i < cellCount; i++) {
    const speeds = [];
    const depths = [];
    let sumU = 0;
    let sumV = 0;
    let wetCount = 0;
    for (const result of successful) {
      const u = result.velocityU[i];
      const v = result.velocityV[i];
      const d = result.waterDepth[i];
      speeds.push(Math.hypot(u, v));
      depths.push(d);
      sumU += u;
      sumV += v;
      if (d > dryThreshold) wetCount++;
    }
    speeds.sort((a, b) => a - b);
    depths.sort((a, b) => a - b);
    const meanDirectionNorm = Math.hypot(sumU, sumV);
    let directionAgreement = 0;
    if (meanDirectionNorm > 1e-12) {
      const mu = sumU / meanDirectionNorm;
      const mv = sumV / meanDirectionNorm;
      directionAgreement = successful.filter(result => {
        const u = result.velocityU[i];
        const v = result.velocityV[i];
        const norm = Math.hypot(u, v);
        return norm <= 1e-12 || (u / norm) * mu + (v / norm) * mv >= 0;
      }).length / successful.length;
    }
    cells.push({
      cellIndex: i,
      speedMedian: quantile(speeds, 0.5),
      speedQ1: quantile(speeds, 0.25),
      speedQ3: quantile(speeds, 0.75),
      depthMedian: quantile(depths, 0.5),
      wetProbability: wetCount / successful.length,
      flowDirectionAgreementFraction: directionAgreement
    });
  }

  return {
    schema: 'onga-stage18-ensemble-statistics-v1',
    caseCountUsed: successful.length,
    excludedFailedCaseCount: runReport.failed,
    physicalValidationClaimAllowed: false,
    cells,
    runDiagnostics: {
      maxAbsoluteMassBalanceError: Math.max(...successful.map(r => Math.abs(r.massBalanceError))),
      maxCfl: Math.max(...successful.map(r => r.cflMax))
    }
  };
}
