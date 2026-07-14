import fs from 'node:fs/promises';
import {
  APPROVAL_SHA256,
  CASE_COUNT,
  ENSEMBLE_SEED,
  generateStage19Ensemble,
  loadStage19Inputs,
  serialize,
  sha256,
  STAGE19_ENSEMBLE_SCHEMA,
} from '../onga_stage19_provisional_ensemble.mjs';

const ensemblePath = process.argv[2] || 'config/stage19_provisional_ensemble_cases_v1.json';
const outputPath = process.argv[3] || 'stage19-provisional-ensemble-validation.json';

function assert(condition, message) {
  if (!condition) throw new Error(`[stage19-ensemble-validation] ${message}`);
}

function inRange(value, range) {
  return Number.isFinite(value) && value >= range.min && value <= range.max;
}

function fullStratifiedSpan(values, range, label) {
  assert(values.every(value => inRange(value, range)), `${label} contains an out-of-range value`);
  const binWidth = (range.max - range.min) / CASE_COUNT;
  assert(Math.min(...values) < range.min + binWidth + 1e-12,
    `${label} does not sample the lowest stratum`);
  assert(Math.max(...values) > range.max - binWidth - 1e-12,
    `${label} does not sample the highest stratum`);
}

function counts(values) {
  const result = {};
  for (const value of values) result[String(value)] = (result[String(value)] || 0) + 1;
  return result;
}

const inputs = await loadStage19Inputs();
const ensembleText = await fs.readFile(ensemblePath, 'utf8');
const ensemble = JSON.parse(ensembleText);
const regenerated = generateStage19Ensemble(
  inputs.ranges,
  inputs.rangesText,
  inputs.approval,
  inputs.approvalText,
);

assert(ensemble.schema === STAGE19_ENSEMBLE_SCHEMA, 'ensemble schema mismatch');
assert(ensemble.status === 'generated_not_assigned_to_solver', 'ensemble status mismatch');
assert(ensemble.count === CASE_COUNT && ensemble.cases.length === CASE_COUNT,
  'ensemble must contain exactly 64 cases');
assert(ensemble.seed === ENSEMBLE_SEED, 'ensemble seed changed');
assert(serialize(ensemble) === serialize(regenerated), 'ensemble is not deterministically reproducible');
assert(ensemble.generatedFrom?.approval?.sha256 === APPROVAL_SHA256,
  'ensemble approval binding changed');
assert(ensemble.casesSha256 === sha256(serialize(ensemble.cases)), 'case-array digest mismatch');
assert(ensemble.geometry?.approvedWaterPixelCount === 680633, 'water geometry changed');
assert(ensemble.geometry?.metricMeshCellCount === 50129, 'mesh geometry changed');
assert(ensemble.geometry?.frozen === true, 'geometry must remain frozen');

const visualBytes = await fs.readFile(inputs.approval.approvedVisual.path);
assert(sha256(visualBytes) === inputs.approval.approvedVisual.sha256,
  'approved range visual digest changed');

const cases = ensemble.cases;
assert(new Set(cases.map(item => item.caseId)).size === CASE_COUNT, 'case ids are not unique');
assert(cases.every(item => item.classification
  === 'provisional_public_data_and_declared_inference_not_observation'),
'a case is not explicitly classified as inference');
assert(cases.every(item => item.boundaries.M.meanOffsetM === null),
  'an absolute mouth offset was assigned');

const ranges = inputs.ranges;
const boundary = Object.fromEntries(ranges.boundaryCandidates.map(item => [item.boundaryId, item]));
const numericChecks = [
  ['mainstem depth', cases.map(item => item.bathymetry.mainstemMeanDepthM), ranges.bathymetryCandidates.mainstemMeanDepthM],
  ['tributary depth', cases.map(item => item.bathymetry.tributaryMeanDepthM), ranges.bathymetryCandidates.tributaryMeanDepthM],
  ['open-channel Manning n', cases.map(item => item.roughness.manningOpenChannel), ranges.roughnessCandidates.openChannel],
  ['shallow-margin multiplier', cases.map(item => item.roughness.shallowMarginMultiplier), ranges.roughnessCandidates.shallowMarginMultiplier],
  ['structure-vicinity multiplier', cases.map(item => item.roughness.structureVicinityMultiplier), ranges.roughnessCandidates.structureVicinityMultiplier],
  ['M phase', cases.map(item => item.boundaries.M.phaseShiftMinutes), boundary.M.parameters.phaseShiftMinutes],
  ['M amplitude', cases.map(item => item.boundaries.M.amplitudeMultiplier), boundary.M.parameters.amplitudeMultiplier],
  ['N discharge', cases.map(item => item.boundaries.N.dischargeM3S), boundary.N.parameters.dischargeM3S],
  ['O discharge', cases.map(item => item.boundaries.O.dischargeM3S), boundary.O.parameters.dischargeM3S],
  ['G discharge', cases.map(item => item.boundaries.G.dischargeM3S), boundary.G.parameters.dischargeM3S],
  ['barrage coefficient', cases.map(item => item.barrage.effectiveDischargeCoefficient), ranges.structureCandidates.barrage.effectiveDischargeCoefficient],
  ['fishway coefficient', cases.map(item => item.fishway.effectiveDischargeCoefficient), ranges.structureCandidates.fishway.effectiveDischargeCoefficient],
  ['fishway area', cases.map(item => item.fishway.effectiveAreaM2), ranges.structureCandidates.fishway.effectiveAreaM2],
];
for (const [label, values, range] of numericChecks) fullStratifiedSpan(values, range, label);

const sigmaCounts = counts(cases.map(item => item.bathymetry.sigma));
const barrageCounts = counts(cases.map(item => item.barrage.scenario));
const fishwayCounts = counts(cases.map(item => item.fishway.mode));
assert(Object.keys(sigmaCounts).length === 3, 'all three approved sigma values are required');
assert(Object.values(sigmaCounts).every(value => value >= 21 && value <= 22),
  'sigma rotation must be balanced 21/21/22');
assert(Object.values(barrageCounts).length === 4
  && Object.values(barrageCounts).every(value => value === 16),
'barrage scenarios must each occur 16 times');
assert(Object.values(fishwayCounts).length === 2
  && Object.values(fishwayCounts).every(value => value === 32),
'fishway modes must each occur 32 times');
assert(ensemble.sourceRoleBindings.G.mappingStatus === 'inference_only'
  && ensemble.sourceRoleBindings.G.candidateSourceIds.length === 0,
'G must remain inference-only');

for (const [key, expected] of Object.entries({
  inferredValuesAreObservations: false,
  absoluteMouthOffsetAssigned: false,
  physicalValuesAssignedToSolver: false,
  numericalRunEnabled: false,
  providesExecutionAuthorization: false,
  physicalValidationClaimAllowed: false,
  publicSimulatorConnected: false,
})) {
  assert(ensemble.safeguards?.[key] === expected, `safeguard ${key} changed`);
}

const report = {
  schema: 'onga-stage19-provisional-inference-ensemble-validation-v1',
  status: 'passed',
  ensembleSha256: sha256(ensembleText),
  casesSha256: ensemble.casesSha256,
  caseCount: ensemble.count,
  seed: ensemble.seed,
  sigmaCounts,
  barrageCounts,
  fishwayCounts,
  numericDimensionsWithFullStratifiedSpan: numericChecks.length,
  physicalValuesAssignedToSolver: false,
  numericalRunEnabled: false,
};

await fs.writeFile(outputPath, serialize(report), 'utf8');
console.log(JSON.stringify(report, null, 2));
