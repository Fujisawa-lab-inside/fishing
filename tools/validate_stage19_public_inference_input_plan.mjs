import crypto from 'node:crypto';
import fs from 'node:fs/promises';

const planPath = process.argv[2] || 'config/stage19_public_inference_input_plan_v1.json';
const decisionPath = process.argv[3] || 'config/stage17_physical_data_acquisition_decision_record_v3.json';
const retirementPath = process.argv[4] || 'config/stage17_external_contact_retirement_v1.json';
const outputPath = process.argv[5] || 'stage19-public-inference-input-plan-validation.json';

function assert(condition, message) {
  if (!condition) throw new Error(`[stage19-public-inference-plan] ${message}`);
}

function sha256(text) {
  return crypto.createHash('sha256').update(text).digest('hex');
}

function sameRange(actual, expected, label) {
  assert(actual?.min === expected.min, `${label}.min changed`);
  assert(actual?.reference === expected.reference, `${label}.reference changed`);
  assert(actual?.max === expected.max, `${label}.max changed`);
}

function normalizedDepthFraction(x, sigma) {
  const edge = Math.exp(-0.5 / (sigma * sigma));
  return (Math.exp(-0.5 * (x / sigma) ** 2) - edge) / (1 - edge);
}

const planText = await fs.readFile(planPath, 'utf8');
const decisionText = await fs.readFile(decisionPath, 'utf8');
const retirementText = await fs.readFile(retirementPath, 'utf8');
const priorText = await fs.readFile('config/stage17_inferred_physical_prior_v1.json', 'utf8');
const retiredSubmissionText = await fs.readFile(
  'config/stage17_onga_office_request_submission_v1.json',
  'utf8',
);

const plan = JSON.parse(planText);
const decision = JSON.parse(decisionText);
const retirement = JSON.parse(retirementText);
const prior = JSON.parse(priorText);
const retiredSubmission = JSON.parse(retiredSubmissionText);

assert(plan.schema === 'onga-stage19-public-inference-input-plan-v1', 'plan schema mismatch');
assert(plan.status === 'visual_input_review_required_before_scenario_generation', 'plan status mismatch');
assert(decision.schema === 'onga-stage17-physical-data-acquisition-decision-record-v3',
  'decision schema mismatch');
assert(decision.optionId === 'public_database_and_declared_inference_only',
  'public-data and declared-inference route is not selected');
assert(decision.scope?.officialRequestPreparationAndSubmission === false,
  'official request must be disabled');
assert(decision.scope?.publicOfficialDatabaseAcquisition === true,
  'public official database acquisition must remain enabled');
assert(decision.scope?.declaredInferenceScenarioPreparation === true,
  'declared inference preparation must be enabled');
assert(decision.scope?.numericalScenarioRunEnablement === false,
  'the route decision must not enable a numerical run');
assert(decision.scope?.publicSimulatorConnection === false,
  'the public simulator must remain disconnected');

const decisionDigest = sha256(decisionText);
assert(decisionDigest === 'b8076332b89b33272af89c6d0fcc9182282ee59a9d06e9bf99fda8e31b2380c4',
  'decision digest changed');
assert(plan.governingRouteDecision?.sha256 === decisionDigest,
  'plan is not bound to the exact route decision');
assert(retirement.governingDecision?.sha256 === decisionDigest,
  'retirement is not bound to the exact route decision');
assert(retirement.schema === 'onga-stage17-external-contact-retirement-v1',
  'retirement schema mismatch');
assert(retirement.status === 'external_contact_disabled_by_requester',
  'external contact is not disabled');
assert(retirement.retiredSubmissionPacket?.sha256 === sha256(retiredSubmissionText),
  'retired submission digest mismatch');
assert(retirement.retiredSubmissionPacket?.mayBeSubmitted === false,
  'retired packet must not be submittable');
assert(retirement.externalContactPerformedBeforeRetirement === false,
  'the record must not claim prior external contact');
assert(retirement.externalContactPerformedByThisTransition === false,
  'the route transition must not perform external contact');
assert(retiredSubmission.submission?.externalContactPerformed === false,
  'retired submission packet claims external contact');

assert(plan.geometry?.approvedWaterPixelCount === 680633, 'water pixel count changed');
assert(plan.geometry?.metricMeshCellCount === 50129, 'metric mesh cell count changed');
assert(plan.geometry?.waterManifestSha256
  === '964eaa8d43607d0ac4cc6d81f37fa8a9ed8dc23563894ddce85b4252938fcbf7',
'water manifest digest changed');
assert(plan.geometry?.metricMeshPackageSha256
  === 'f18ac352604e286be395f7ced1580f654c00b29cf65f310fcbce38fb00219fe2',
'metric mesh package digest changed');
assert(plan.geometry?.frozen === true, 'geometry must remain frozen');

assert(plan.publicEvidence.length === 6, 'expected six public evidence entries');
const evidenceIds = new Set(plan.publicEvidence.map(item => item.id));
assert(evidenceIds.size === plan.publicEvidence.length, 'public evidence ids must be unique');
for (const item of plan.publicEvidence) {
  assert(typeof item.url === 'string' && item.url.startsWith('https://'),
    `public evidence ${item.id} must use https`);
  assert(typeof item.useStatus === 'string' && item.useStatus.length > 0,
    `public evidence ${item.id} must declare useStatus`);
}
const jma = plan.publicEvidence.find(item => item.id === 'jma_hakata_2026_astronomical_tide');
assert(jma?.facts?.kind === 'astronomical_tide_prediction',
  'JMA tide must remain classified as prediction');
assert(jma?.useStatus === 'secondary_shape_reference_only_not_observed_onga_mouth_level',
  'JMA tide use expanded beyond secondary reference');
const barrage = plan.publicEvidence.find(item => item.id === 'mlit_onga_barrage_gate_public_facts');
assert(barrage?.useStatus === 'published_structure_inventory_not_effective_hydraulic_parameter',
  'published gate dimensions must not become effective hydraulic parameters');

assert(sha256(priorText) === plan.inferenceScenario?.sourcePrior?.sha256,
  'source-prior digest mismatch');
sameRange(plan.inferenceScenario.bathymetry.mainstemMeanDepthM,
  prior.bathymetryPrior.mainstemMeanDepthM, 'mainstemMeanDepthM');
sameRange(plan.inferenceScenario.bathymetry.tributaryMeanDepthM,
  prior.bathymetryPrior.tributaryMeanDepthM, 'tributaryMeanDepthM');
sameRange(plan.inferenceScenario.roughness.manningOpenChannel,
  prior.roughnessPrior.openChannel, 'manningOpenChannel');
sameRange(plan.inferenceScenario.boundaries.M.phaseShiftMinutes,
  prior.boundaryPrior.M.phaseShiftMinutes, 'M.phaseShiftMinutes');
sameRange(plan.inferenceScenario.boundaries.M.amplitudeMultiplier,
  prior.boundaryPrior.M.amplitudeMultiplier, 'M.amplitudeMultiplier');
sameRange(plan.inferenceScenario.boundaries.N.referenceDischargeM3S,
  prior.boundaryPrior.N.referenceDischargeM3S, 'N.referenceDischargeM3S');
sameRange(plan.inferenceScenario.boundaries.O.referenceDischargeM3S,
  prior.boundaryPrior.O.referenceDischargeM3S, 'O.referenceDischargeM3S');
sameRange(plan.inferenceScenario.boundaries.G.referenceDischargeM3S,
  prior.boundaryPrior.G.referenceDischargeM3S, 'G.referenceDischargeM3S');

const bathymetry = plan.inferenceScenario.bathymetry;
assert(bathymetry.crossSectionFamily
  === 'smooth_symmetric_inverted_normal_distribution_like_trough',
'cross-section family mismatch');
assert(JSON.stringify(bathymetry.sigmaCandidates) === JSON.stringify([0.28, 0.36, 0.46]),
  'sigma candidate set changed');
for (const sigma of bathymetry.sigmaCandidates) {
  assert(normalizedDepthFraction(0, sigma) === 1, `centre depth must be one for sigma ${sigma}`);
  assert(Math.abs(normalizedDepthFraction(1, sigma)) < 1e-12,
    `shore depth must be zero for sigma ${sigma}`);
  let previous = normalizedDepthFraction(0, sigma);
  for (let index = 1; index <= 100; index += 1) {
    const current = normalizedDepthFraction(index / 100, sigma);
    assert(current <= previous + 1e-12, `profile must shallow monotonically for sigma ${sigma}`);
    previous = current;
  }
}
assert(bathymetry.mapPreviewUsesNormalizedDepthFractionOnly === true,
  'map preview must remain normalized');
assert(bathymetry.absoluteDepthAssignmentApproved === false,
  'absolute depth assignment must remain unapproved');
assert(plan.inferenceScenario.singleBestGuessForbidden === true,
  'single best guess must remain forbidden');
assert(plan.inferenceScenario.ensembleRequired === true,
  'ensemble must remain required');

const safeguards = plan.safeguards;
for (const key of [
  'externalContactPerformed',
  'approvedWaterGeometryChanged',
  'metricMeshChanged',
  'absolutePhysicalValuesAssignedToSolver',
  'numericalRunEnabled',
  'physicalValidationClaimAllowed',
  'publicSimulatorConnected',
]) {
  assert(safeguards?.[key] === false, `safeguard ${key} must remain false`);
}
assert(safeguards.visualFittingToDesiredFlowForbidden === true,
  'visual fitting to a desired flow must remain forbidden');

const report = {
  schema: 'onga-stage19-public-inference-input-plan-validation-v1',
  status: 'passed',
  route: decision.optionId,
  publicEvidenceCount: plan.publicEvidence.length,
  unresolvedPublicInputCount: plan.publiclyUnresolvedInputs.length,
  visualDecisionRequired: true,
  numericalRunEnabled: false,
  externalContactPerformed: false,
  physicalValidationReady: false,
  publicSimulatorConnected: false,
};

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
console.log(JSON.stringify(report, null, 2));
