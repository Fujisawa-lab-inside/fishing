import fs from 'node:fs/promises';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const path = process.argv[2] ?? 'config/stage18_production_mesh_pilot_v1.json';
const config = JSON.parse(await fs.readFile(path, 'utf8'));

assert(config.schema === 'onga-stage18-production-mesh-pilot-v1', 'unsupported schema');
assert(config.purpose === 'synthetic_inference_runtime_and_numerical_stability_pilot_only', 'purpose changed');
assert(config.geometry?.approvedWaterPixelCount === 679791, 'approved water geometry changed');
assert(config.geometry?.metricMeshCellCount === 50333, 'metric mesh changed');
assert(config.geometry?.frozen === true, 'geometry must remain frozen');

const expectedOrder = ['smoke', 'screening', 'pilot'];
assert(JSON.stringify(config.promotionOrder) === JSON.stringify(expectedOrder), 'promotion order changed');
assert(Array.isArray(config.tiers) && config.tiers.length === 3, 'three pilot tiers required');
let previousCases = 0;
let previousSteps = 0;
for (let i = 0; i < config.tiers.length; i += 1) {
  const tier = config.tiers[i];
  assert(tier.id === expectedOrder[i], `unexpected tier ${tier.id}`);
  for (const key of ['caseCount', 'maxSteps', 'maxWallSeconds', 'maxResidentMemoryMiB']) {
    assert(Number.isInteger(tier[key]) && tier[key] > 0, `${tier.id}.${key} must be a positive integer`);
  }
  assert(tier.caseCount > previousCases, 'case counts must increase');
  assert(tier.maxSteps > previousSteps, 'step limits must increase');
  assert(tier.caseCount <= 16, 'pilot must not silently become the full 64-case run');
  previousCases = tier.caseCount;
  previousSteps = tier.maxSteps;
}

const requiredDiagnostics = new Set([
  'completedCaseCount', 'failedCaseCount', 'wallSeconds', 'peakResidentMemoryMiB',
  'maxCfl', 'maxAbsoluteMassBalanceError', 'minimumDepthM', 'nanCount', 'negativeDepthCount',
]);
assert(requiredDiagnostics.size === config.requiredDiagnostics.length, 'diagnostic list has duplicates or omissions');
for (const name of config.requiredDiagnostics) assert(requiredDiagnostics.has(name), `unsupported diagnostic ${name}`);

const acceptance = config.acceptance;
assert(acceptance.completionFractionMin >= 0.95 && acceptance.completionFractionMin <= 1, 'completion threshold too weak');
assert(acceptance.nanCountMax === 0, 'NaN must remain forbidden');
assert(acceptance.negativeDepthCountMax === 0, 'negative depth must remain forbidden');
assert(acceptance.maxCflMax > 0 && acceptance.maxCflMax <= 1, 'CFL threshold invalid');
assert(acceptance.maxAbsoluteMassBalanceErrorMax > 0 && acceptance.maxAbsoluteMassBalanceErrorMax <= 1e-8, 'mass-balance threshold too weak');

const safeguards = config.safeguards;
for (const key of [
  'physicalValidationClaimAllowed', 'publicSimulatorConnectionAllowed', 'visualFittingAllowed',
  'physicalRunEnabled', 'automaticTierPromotionAllowed', 'failedCasesMayBeImputed',
]) assert(safeguards[key] === false, `${key} must remain false`);
assert(config.full64CaseRun?.enabled === false, 'full 64-case run must remain disabled');
assert(config.full64CaseRun?.requiresPilotAcceptance === true, 'pilot acceptance must be required');
assert(config.full64CaseRun?.requiresExplicitHumanApproval === true, 'explicit human approval must be required');

const report = {
  schema: 'onga-stage18-production-mesh-pilot-validation-v1',
  status: 'pass',
  tierIds: config.tiers.map(tier => tier.id),
  maximumPilotCaseCount: Math.max(...config.tiers.map(tier => tier.caseCount)),
  geometry: config.geometry,
  full64CaseRunEnabled: config.full64CaseRun.enabled,
};
await fs.writeFile('stage18-production-mesh-pilot-validation.json', `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify(report));
