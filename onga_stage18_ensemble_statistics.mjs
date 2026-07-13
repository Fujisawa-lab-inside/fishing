function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function finite(value, label) {
  assert(Number.isFinite(value), `${label} must be finite`);
  return value;
}

function quantile(values, probability) {
  assert(Array.isArray(values) && values.length > 0, 'quantile requires values');
  const sorted = [...values].sort((a, b) => a - b);
  const position = (sorted.length - 1) * probability;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  if (lower === upper) return sorted[lower];
  const weight = position - lower;
  return sorted[lower] * (1 - weight) + sorted[upper] * weight;
}

function circularAgreement(vectors, speedThreshold = 1e-9) {
  const active = vectors.filter(({ u, v }) => Math.hypot(u, v) > speedThreshold);
  if (active.length === 0) return { fraction: 0, meanDirectionRad: null, activeCount: 0 };
  const unit = active.map(({ u, v }) => {
    const speed = Math.hypot(u, v);
    return { x: u / speed, y: v / speed };
  });
  const meanX = unit.reduce((sum, item) => sum + item.x, 0) / unit.length;
  const meanY = unit.reduce((sum, item) => sum + item.y, 0) / unit.length;
  return {
    fraction: Math.hypot(meanX, meanY),
    meanDirectionRad: Math.atan2(meanY, meanX),
    activeCount: active.length,
  };
}

export function validateCaseResult(result, expectedCellCount) {
  assert(result?.schema === 'onga-stage18-case-result-v1', 'unsupported case result schema');
  assert(typeof result.caseId === 'string' && result.caseId.length > 0, 'caseId required');
  assert(['completed', 'failed'].includes(result.status), 'invalid case status');
  if (result.status === 'failed') {
    assert(typeof result.failureReason === 'string' && result.failureReason.length > 0, 'failure reason required');
    return true;
  }
  assert(Array.isArray(result.cells) && result.cells.length === expectedCellCount, 'cell count mismatch');
  finite(result.massBalanceError, 'massBalanceError');
  for (let index = 0; index < result.cells.length; index += 1) {
    const cell = result.cells[index];
    assert(cell.cellId === index, `cellId mismatch at ${index}`);
    finite(cell.waterDepthM, 'waterDepthM');
    finite(cell.velocityUms, 'velocityUms');
    finite(cell.velocityVms, 'velocityVms');
    assert(cell.waterDepthM >= 0, 'negative water depth');
    assert(typeof cell.wet === 'boolean', 'wet flag required');
  }
  return true;
}

export function aggregateEnsembleResults(ensemble, caseResults, options = {}) {
  assert(ensemble?.schema === 'onga-stage18-inference-ensemble-v1', 'unsupported ensemble schema');
  assert(ensemble?.geometry?.approvedWaterPixelCount === 679791, 'approved water geometry changed');
  assert(ensemble?.geometry?.metricMeshCellCount === 50333, 'metric mesh changed');
  assert(ensemble?.safeguards?.physicalRunEnabled === false, 'physical run must remain disabled');
  assert(Array.isArray(caseResults), 'caseResults must be an array');

  const expectedCaseIds = new Set(ensemble.cases.map(item => item.caseId));
  const seen = new Set();
  const completed = [];
  const failed = [];
  const cellCount = Number(options.cellCount ?? ensemble.geometry.metricMeshCellCount);

  for (const result of caseResults) {
    validateCaseResult(result, cellCount);
    assert(expectedCaseIds.has(result.caseId), `unknown caseId ${result.caseId}`);
    assert(!seen.has(result.caseId), `duplicate caseId ${result.caseId}`);
    seen.add(result.caseId);
    if (result.status === 'completed') completed.push(result);
    else failed.push({ caseId: result.caseId, failureReason: result.failureReason });
  }

  const minimumCompletedFraction = Number(options.minimumCompletedFraction ?? 0.8);
  const completedFraction = completed.length / ensemble.cases.length;
  assert(completedFraction >= minimumCompletedFraction, 'insufficient completed-case fraction');

  const cells = Array.from({ length: cellCount }, (_, cellId) => {
    const samples = completed.map(result => result.cells[cellId]);
    const speed = samples.map(cell => Math.hypot(cell.velocityUms, cell.velocityVms));
    const depth = samples.map(cell => cell.waterDepthM);
    const direction = circularAgreement(samples.map(cell => ({ u: cell.velocityUms, v: cell.velocityVms })));
    const wetCount = samples.filter(cell => cell.wet).length;
    return {
      cellId,
      velocityMedianMs: quantile(speed, 0.5),
      velocityQ1Ms: quantile(speed, 0.25),
      velocityQ3Ms: quantile(speed, 0.75),
      velocityP025Ms: quantile(speed, 0.025),
      velocityP975Ms: quantile(speed, 0.975),
      waterDepthMedianM: quantile(depth, 0.5),
      waterDepthQ1M: quantile(depth, 0.25),
      waterDepthQ3M: quantile(depth, 0.75),
      wetProbability: wetCount / samples.length,
      flowDirectionAgreementFraction: direction.fraction,
      meanFlowDirectionRad: direction.meanDirectionRad,
      activeDirectionSampleCount: direction.activeCount,
    };
  });

  const massErrors = completed.map(result => Math.abs(result.massBalanceError));
  return {
    schema: 'onga-stage18-ensemble-statistics-v1',
    sourceEnsembleSeed: ensemble.seed,
    sourceCaseCount: ensemble.count,
    completedCaseCount: completed.length,
    failedCaseCount: failed.length,
    completedFraction,
    failedCases: failed,
    geometry: ensemble.geometry,
    diagnostics: {
      massBalanceAbsoluteMedian: quantile(massErrors, 0.5),
      massBalanceAbsoluteMaximum: Math.max(...massErrors),
      physicalValidationClaimAllowed: false,
      publicSimulatorConnectionAllowed: false,
      classification: 'provisional_inference_statistics_not_observation',
    },
    cells,
  };
}

export { quantile, circularAgreement };
