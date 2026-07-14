import crypto from 'node:crypto';
import fs from 'node:fs/promises';

const rangesPath = process.argv[2] || 'config/stage19_inferred_scenario_ranges_v1.json';
const approvalPath = process.argv[3] || 'config/stage19_public_inference_shape_approval_v1.json';
const outputPath = process.argv[4] || 'stage19-inferred-scenario-ranges-validation.json';

function assert(condition, message) {
  if (!condition) throw new Error(`[stage19-inferred-ranges] ${message}`);
}

function sha256(text) {
  return crypto.createHash('sha256').update(text).digest('hex');
}

function sameRange(actual, expected, label) {
  assert(actual?.min === expected?.min, `${label}.min changed`);
  assert(actual?.reference === expected?.reference, `${label}.reference changed`);
  assert(actual?.max === expected?.max, `${label}.max changed`);
}

const rangesText = await fs.readFile(rangesPath, 'utf8');
const approvalText = await fs.readFile(approvalPath, 'utf8');
const planText = await fs.readFile('config/stage19_public_inference_input_plan_v1.json', 'utf8');
const priorText = await fs.readFile('config/stage17_inferred_physical_prior_v1.json', 'utf8');
const approvedVisual = await fs.readFile('docs/visuals/stage19-public-inference-input-decision.png');

const ranges = JSON.parse(rangesText);
const approval = JSON.parse(approvalText);
const plan = JSON.parse(planText);
const prior = JSON.parse(priorText);

assert(ranges.schema === 'onga-stage19-inferred-scenario-ranges-v1', 'range schema mismatch');
assert(ranges.status === 'visual_review_required_before_case_generation', 'range status mismatch');
assert(approval.schema === 'onga-stage19-public-inference-shape-approval-v1',
  'shape approval schema mismatch');
assert(approval.status === 'approved_for_provisional_scenario_family_only',
  'shape family has not been approved');
assert(approval.sourceStatement === 'この形でよい．作業を進めてください．',
  'shape approval statement changed');

const approvalDigest = sha256(approvalText);
const planDigest = sha256(planText);
assert(approvalDigest === '3d35faaee7f9c0bdb063c7b3914162a9e2ac3afeb92e159387c562596eb7abb2',
  'shape approval digest changed');
assert(planDigest === '6d6be78a4318cb3ceffc936c228a8e5a58eeb8f323b0d2c45acd5e831c488866',
  'public inference plan digest changed');
assert(ranges.shapeApproval?.sha256 === approvalDigest,
  'ranges are not bound to the exact shape approval');
assert(ranges.sourcePlan?.sha256 === planDigest,
  'ranges are not bound to the exact public inference plan');
assert(approval.approvedPlan?.sha256 === planDigest,
  'shape approval is not bound to the exact input plan');
assert(approval.approvedVisual?.sha256 === sha256(approvedVisual),
  'approved shape visual digest changed');

assert(ranges.geometry?.approvedWaterPixelCount === 680633, 'water pixel count changed');
assert(ranges.geometry?.metricMeshCellCount === 50129, 'mesh cell count changed');
assert(ranges.geometry?.frozen === true, 'geometry must remain frozen');
assert(ranges.bathymetryCandidates?.shapeFamily
  === 'smooth_symmetric_inverted_normal_distribution_like_trough',
'approved shape family changed');
assert(JSON.stringify(ranges.bathymetryCandidates?.sigmaCandidates)
  === JSON.stringify([0.28, 0.36, 0.46]), 'approved sigma candidates changed');

sameRange(ranges.bathymetryCandidates.mainstemMeanDepthM,
  prior.bathymetryPrior.mainstemMeanDepthM, 'mainstemMeanDepthM');
sameRange(ranges.bathymetryCandidates.tributaryMeanDepthM,
  prior.bathymetryPrior.tributaryMeanDepthM, 'tributaryMeanDepthM');
sameRange(ranges.roughnessCandidates.openChannel,
  prior.roughnessPrior.openChannel, 'openChannelManningN');
sameRange(ranges.roughnessCandidates.shallowMarginMultiplier,
  prior.roughnessPrior.shallowMarginMultiplier, 'shallowMarginMultiplier');
sameRange(ranges.roughnessCandidates.structureVicinityMultiplier,
  prior.roughnessPrior.structureVicinityMultiplier, 'structureVicinityMultiplier');

const boundaries = new Map(ranges.boundaryCandidates.map(item => [item.boundaryId, item]));
assert(boundaries.size === 4, 'exactly four boundary candidates are required');
for (const id of ['M', 'N', 'O', 'G']) assert(boundaries.has(id), `boundary ${id} missing`);
const m = boundaries.get('M');
const n = boundaries.get('N');
const o = boundaries.get('O');
const g = boundaries.get('G');

sameRange(m.parameters.phaseShiftMinutes, prior.boundaryPrior.M.phaseShiftMinutes,
  'M.phaseShiftMinutes');
sameRange(m.parameters.amplitudeMultiplier, prior.boundaryPrior.M.amplitudeMultiplier,
  'M.amplitudeMultiplier');
assert(m.parameters.meanOffsetM === null, 'M absolute offset must remain unassigned');
assert(m.mappingStatus === 'candidate_not_selected', 'M source must remain a candidate');
assert(JSON.stringify(m.candidateSourceIds) === JSON.stringify(['jma_hakata_2026_astronomical_tide']),
  'M candidate mapping changed');

sameRange(n.parameters.dischargeM3S, prior.boundaryPrior.N.referenceDischargeM3S,
  'N.dischargeM3S');
sameRange(o.parameters.dischargeM3S, prior.boundaryPrior.O.referenceDischargeM3S,
  'O.dischargeM3S');
sameRange(g.parameters.dischargeM3S, prior.boundaryPrior.G.referenceDischargeM3S,
  'G.dischargeM3S');
assert(JSON.stringify(n.candidateSourceIds) === JSON.stringify(['mlit_gion_bridge_station_metadata']),
  'N candidate mapping changed');
assert(JSON.stringify(o.candidateSourceIds) === JSON.stringify([
  'mlit_nakama_station_metadata',
  'mlit_karakuma_station_metadata',
]), 'O candidate mapping changed');
assert(g.mappingStatus === 'inference_only', 'G must remain inference-only');
assert(g.candidateSourceIds.length === 0, 'G must not claim a direct public station');
for (const boundary of [m, n, o]) {
  assert(boundary.mappingStatus === 'candidate_not_selected',
    `${boundary.boundaryId} source mapping must remain a candidate`);
}

assert(JSON.stringify(ranges.structureCandidates.barrage.scenarios)
  === JSON.stringify(prior.barragePrior.requiredScenarios), 'barrage scenarios changed');
sameRange(ranges.structureCandidates.barrage.effectiveDischargeCoefficient,
  prior.barragePrior.effectiveDischargeCoefficient, 'barrageCoefficient');
assert(JSON.stringify(ranges.structureCandidates.fishway.modes)
  === JSON.stringify(['disabled', 'head_difference_relation_ensemble']), 'fishway modes changed');
sameRange(ranges.structureCandidates.fishway.effectiveDischargeCoefficient,
  prior.fishwayPrior.effectiveDischargeCoefficient, 'fishwayCoefficient');
sameRange(ranges.structureCandidates.fishway.effectiveAreaM2,
  prior.fishwayPrior.effectiveAreaM2, 'fishwayAreaM2');

for (const section of [
  ranges.bathymetryCandidates,
  ranges.roughnessCandidates,
  ranges.structureCandidates,
]) {
  assert(section.approvedForCaseGeneration === false,
    'candidate ranges must remain unapproved before visual review');
}
for (const boundary of [m, n, o, g]) {
  assert(boundary.limitations?.length > 0, `${boundary.boundaryId} limitations missing`);
}

for (const key of [
  'externalContactPerformed',
  'physicalValuesAssignedToSolver',
  'casesGenerated',
  'numericalRunEnabled',
  'publicSimulatorConnected',
  'physicalValidationClaimAllowed',
]) {
  assert(ranges.safeguards?.[key] === false, `safeguard ${key} must remain false`);
}

const report = {
  schema: 'onga-stage19-inferred-scenario-ranges-validation-v1',
  status: 'passed',
  approvedShapeFamilyLocked: true,
  candidateBoundaryMappings: {M: 1, N: 1, O: 2, G: 0},
  gBoundaryInferenceOnly: true,
  absoluteMouthOffsetAssigned: false,
  candidateRangesApproved: false,
  casesGenerated: false,
  numericalRunEnabled: false,
};

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
console.log(JSON.stringify(report, null, 2));
