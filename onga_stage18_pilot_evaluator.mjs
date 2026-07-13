function assert(condition, message) {
  if (!condition) throw new Error(message);
}

export function evaluatePilotResult(config, report) {
  assert(config?.schema === 'onga-stage18-production-mesh-pilot-v1', 'unsupported pilot config');
  assert(report?.schema === 'onga-stage18-pilot-run-report-v1', 'unsupported pilot report');
  const tier = config.tiers.find(item => item.id === report.tierId);
  assert(tier, `unknown tier ${report.tierId}`);
  assert(report.geometry?.approvedWaterPixelCount === config.geometry.approvedWaterPixelCount, 'water geometry mismatch');
  assert(report.geometry?.metricMeshCellCount === config.geometry.metricMeshCellCount, 'mesh mismatch');
  assert(Number.isInteger(report.requestedCaseCount) && report.requestedCaseCount === tier.caseCount, 'requested case count mismatch');
  assert(Number.isInteger(report.completedCaseCount) && report.completedCaseCount >= 0, 'invalid completed case count');
  assert(Number.isInteger(report.failedCaseCount) && report.failedCaseCount >= 0, 'invalid failed case count');
  assert(report.completedCaseCount + report.failedCaseCount === report.requestedCaseCount, 'case accounting mismatch');

  for (const key of ['wallSeconds', 'peakResidentMemoryMiB', 'maxCfl', 'maxAbsoluteMassBalanceError', 'minimumDepthM']) {
    assert(Number.isFinite(report[key]), `${key} must be finite`);
  }
  for (const key of ['nanCount', 'negativeDepthCount']) {
    assert(Number.isInteger(report[key]) && report[key] >= 0, `${key} must be a nonnegative integer`);
  }
  assert(Array.isArray(report.failures), 'failures must be an array');
  assert(report.failures.length === report.failedCaseCount, 'failure list count mismatch');

  const completionFraction = report.completedCaseCount / report.requestedCaseCount;
  const checks = {
    completionFraction: completionFraction >= config.acceptance.completionFractionMin,
    nanCount: report.nanCount <= config.acceptance.nanCountMax,
    negativeDepthCount: report.negativeDepthCount <= config.acceptance.negativeDepthCountMax,
    maxCfl: report.maxCfl <= config.acceptance.maxCflMax,
    massBalance: Math.abs(report.maxAbsoluteMassBalanceError) <= config.acceptance.maxAbsoluteMassBalanceErrorMax,
    wallTime: report.wallSeconds <= tier.maxWallSeconds,
    memory: report.peakResidentMemoryMiB <= tier.maxResidentMemoryMiB,
    minimumDepth: report.minimumDepthM >= 0,
  };
  const passed = Object.values(checks).every(Boolean);
  const tierIndex = config.promotionOrder.indexOf(report.tierId);
  const nextTierId = passed && tierIndex >= 0 && tierIndex < config.promotionOrder.length - 1
    ? config.promotionOrder[tierIndex + 1]
    : null;

  return {
    schema: 'onga-stage18-pilot-evaluation-v1',
    tierId: report.tierId,
    passed,
    checks,
    completionFraction,
    nextTierId,
    automaticPromotionPerformed: false,
    full64CaseRunAuthorized: false,
    classification: 'synthetic_inference_runtime_and_numerical_stability_evidence_only',
  };
}
