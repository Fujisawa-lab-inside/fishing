import fs from 'node:fs/promises';
import { generateInferenceEnsemble, loadPrior } from '../onga_stage18_inference_ensemble.mjs';

function check(name, ok, value = null) {
  return { name, ok: Boolean(ok), value };
}

function inRange(value, range) {
  return Number.isFinite(value) && value >= range.min && value <= range.max;
}

function stableJson(value) {
  return JSON.stringify(value);
}

const prior = await loadPrior();
const first = generateInferenceEnsemble(prior, { count: 64, seed: 20260713 });
const second = generateInferenceEnsemble(prior, { count: 64, seed: 20260713 });
const different = generateInferenceEnsemble(prior, { count: 64, seed: 20260714 });

const cases = first.cases;
const barrageSet = new Set(cases.map(item => item.barrage.scenario));
const shapeSet = new Set(cases.map(item => item.bathymetry.crossSectionShape));
const fishwaySet = new Set(cases.map(item => item.fishway.mode));

const allWithinBounds = cases.every(item =>
  inRange(item.bathymetry.mainstemMeanDepthM, prior.bathymetryPrior.mainstemMeanDepthM)
  && inRange(item.bathymetry.tributaryMeanDepthM, prior.bathymetryPrior.tributaryMeanDepthM)
  && inRange(item.bathymetry.thalwegOffsetFractionOfLocalWidth, prior.bathymetryPrior.thalwegOffsetFractionOfLocalWidth)
  && inRange(item.bathymetry.longitudinalSmoothingLengthM, prior.bathymetryPrior.longitudinalSmoothingLengthM)
  && inRange(item.roughness.manningOpenChannel, prior.roughnessPrior.openChannel)
  && inRange(item.roughness.shallowMarginMultiplier, prior.roughnessPrior.shallowMarginMultiplier)
  && inRange(item.roughness.structureVicinityMultiplier, prior.roughnessPrior.structureVicinityMultiplier)
  && inRange(item.boundaries.M.phaseShiftMinutes, prior.boundaryPrior.M.phaseShiftMinutes)
  && inRange(item.boundaries.M.amplitudeMultiplier, prior.boundaryPrior.M.amplitudeMultiplier)
  && inRange(item.boundaries.N.dischargeM3S, prior.boundaryPrior.N.referenceDischargeM3S)
  && inRange(item.boundaries.O.dischargeM3S, prior.boundaryPrior.O.referenceDischargeM3S)
  && inRange(item.boundaries.G.dischargeM3S, prior.boundaryPrior.G.referenceDischargeM3S)
  && inRange(item.fishway.effectiveDischargeCoefficient, prior.fishwayPrior.effectiveDischargeCoefficient)
  && inRange(item.fishway.effectiveAreaM2, prior.fishwayPrior.effectiveAreaM2)
  && inRange(item.barrage.effectiveDischargeCoefficient, prior.barragePrior.effectiveDischargeCoefficient)
);

const uniqueIds = new Set(cases.map(item => item.caseId));
const noObservationClaims = cases.every(item => item.classification === 'provisional_inference_case_not_observation');
const safeguards = first.safeguards;

const checks = [
  check('schema', first.schema === 'onga-stage18-inference-ensemble-v1', first.schema),
  check('case count', cases.length === 64, cases.length),
  check('deterministic for same seed', stableJson(first) === stableJson(second)),
  check('different seed changes ensemble', stableJson(first) !== stableJson(different)),
  check('all numeric values within declared prior bounds', allWithinBounds),
  check('all case ids unique', uniqueIds.size === cases.length, uniqueIds.size),
  check('all cross-section families represented', prior.bathymetryPrior.crossSectionShape.every(value => shapeSet.has(value)), [...shapeSet]),
  check('all required barrage scenarios represented', prior.barragePrior.requiredScenarios.every(value => barrageSet.has(value)), [...barrageSet]),
  check('fishway disabled scenario represented', fishwaySet.has('disabled'), [...fishwaySet]),
  check('fishway active scenario represented', fishwaySet.has('head_difference_relation'), [...fishwaySet]),
  check('approved water geometry frozen', first.geometry.approvedWaterPixelCount === 679791 && first.geometry.frozen === true, first.geometry),
  check('metric mesh frozen', first.geometry.metricMeshCellCount === 50333, first.geometry.metricMeshCellCount),
  check('single best guess forbidden', safeguards.singleBestGuessForbidden === true),
  check('physical validation claim disabled', safeguards.physicalValidationClaimAllowed === false),
  check('public simulator connection disabled', safeguards.publicSimulatorConnectionAllowed === false),
  check('visual fitting forbidden', safeguards.visualFittingForbidden === true),
  check('physical run disabled', safeguards.physicalRunEnabled === false),
  check('no case is labelled observation', noObservationClaims),
  check('required uncertainty outputs preserved', prior.requiredOutputs.every(name => first.requiredOutputs.includes(name)), first.requiredOutputs),
];

const report = {
  schema: 'onga-stage18-inference-ensemble-validation-v1',
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  generatedAt: new Date().toISOString(),
  summary: {
    caseCount: cases.length,
    seed: first.seed,
    crossSectionShapes: [...shapeSet],
    barrageScenarios: [...barrageSet],
    fishwayModes: [...fishwaySet],
  },
  checks,
};

await fs.writeFile('stage18-inference-ensemble-validation.json', `${JSON.stringify(report, null, 2)}\n`, 'utf8');
await fs.writeFile('stage18-inference-ensemble-sample.json', `${JSON.stringify(first, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
