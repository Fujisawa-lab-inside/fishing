import crypto from 'node:crypto';
import fs from 'node:fs/promises';

export const STAGE19_ENSEMBLE_SCHEMA = 'onga-stage19-provisional-inference-ensemble-v1';
export const RANGE_PATH = 'config/stage19_inferred_scenario_ranges_v1.json';
export const RANGE_SHA256 = 'b068800fbc7463e00d490f3cfcc0b80701d403b1de182f16f1f2bacf910448a4';
export const APPROVAL_PATH = 'config/stage19_inferred_scenario_ranges_approval_v1.json';
export const APPROVAL_SHA256 = 'c9459863e9eb812ca22b1d237f5242b7c2290b239d54eeed3be42c08db816ad4';
export const CASE_COUNT = 64;
export const ENSEMBLE_SEED = 20260714;

function assert(condition, message) {
  if (!condition) throw new Error(`[stage19-ensemble] ${message}`);
}

export function sha256(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

export function serialize(value) {
  return `${JSON.stringify(value, null, 2)}\n`;
}

function xorshift32(seed) {
  let state = seed >>> 0 || 0x9e3779b9;
  return () => {
    state ^= state << 13;
    state ^= state >>> 17;
    state ^= state << 5;
    return (state >>> 0) / 4294967296;
  };
}

function shuffle(values, random) {
  const out = [...values];
  for (let index = out.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(random() * (index + 1));
    [out[index], out[swapIndex]] = [out[swapIndex], out[index]];
  }
  return out;
}

function sampleRange(range, count, random) {
  assert(Number.isFinite(range?.min) && Number.isFinite(range?.reference)
    && Number.isFinite(range?.max), 'range must contain finite min/reference/max');
  assert(range.min <= range.reference && range.reference <= range.max,
    'range reference must lie within min/max');
  const units = shuffle(
    Array.from({length: count}, (_, index) => (index + random()) / count),
    random,
  );
  return units.map(unit => Number((range.min + unit * (range.max - range.min)).toFixed(8)));
}

function categorical(values, count, offset) {
  assert(Array.isArray(values) && values.length > 0, 'categorical values required');
  return Array.from({length: count}, (_, index) => values[(index + offset) % values.length]);
}

function boundary(ranges, id) {
  const result = ranges.boundaryCandidates.find(item => item.boundaryId === id);
  assert(result, `boundary ${id} missing`);
  return result;
}

export function validateInputs(ranges, rangesText, approval, approvalText) {
  assert(sha256(rangesText) === RANGE_SHA256, 'approved range digest changed');
  assert(sha256(approvalText) === APPROVAL_SHA256, 'range approval digest changed');
  assert(ranges.schema === 'onga-stage19-inferred-scenario-ranges-v1', 'range schema changed');
  assert(approval.schema === 'onga-stage19-inferred-scenario-ranges-approval-v1',
    'approval schema changed');
  assert(approval.status === 'approved_for_provisional_case_generation_only',
    'case generation is not approved');
  assert(approval.sourceStatement === 'この範囲と対応でよい．作業を進めてください．',
    'approval statement changed');
  assert(approval.approvedRanges?.sha256 === RANGE_SHA256,
    'approval is not bound to the exact ranges');
  assert(ranges.geometry?.approvedWaterPixelCount === 680633, 'water geometry changed');
  assert(ranges.geometry?.metricMeshCellCount === 50129, 'metric mesh changed');
  assert(ranges.geometry?.frozen === true, 'geometry must remain frozen');
  assert(ranges.bathymetryCandidates?.shapeFamily
    === 'smooth_symmetric_inverted_normal_distribution_like_trough',
  'shape family changed');
  assert(ranges.safeguards?.numericalRunEnabled === false,
    'range packet must not enable a numerical run');
  assert(approval.safeguards?.numericalRunEnabled === false,
    'approval must not enable a numerical run');
}

export function generateStage19Ensemble(ranges, rangesText, approval, approvalText, options = {}) {
  validateInputs(ranges, rangesText, approval, approvalText);
  const count = Number(options.count ?? CASE_COUNT);
  const seed = Number(options.seed ?? ENSEMBLE_SEED);
  assert(count === CASE_COUNT, 'ensemble must contain exactly 64 cases');
  assert(seed === ENSEMBLE_SEED, 'ensemble seed changed');

  const m = boundary(ranges, 'M');
  const n = boundary(ranges, 'N');
  const o = boundary(ranges, 'O');
  const g = boundary(ranges, 'G');
  const random = xorshift32(seed);
  const numeric = {
    mainstemMeanDepthM: sampleRange(ranges.bathymetryCandidates.mainstemMeanDepthM, count, random),
    tributaryMeanDepthM: sampleRange(ranges.bathymetryCandidates.tributaryMeanDepthM, count, random),
    manningOpenChannel: sampleRange(ranges.roughnessCandidates.openChannel, count, random),
    shallowMarginMultiplier: sampleRange(ranges.roughnessCandidates.shallowMarginMultiplier, count, random),
    structureVicinityMultiplier: sampleRange(ranges.roughnessCandidates.structureVicinityMultiplier, count, random),
    mouthPhaseShiftMinutes: sampleRange(m.parameters.phaseShiftMinutes, count, random),
    mouthAmplitudeMultiplier: sampleRange(m.parameters.amplitudeMultiplier, count, random),
    nishikawaDischargeM3S: sampleRange(n.parameters.dischargeM3S, count, random),
    ongaDischargeM3S: sampleRange(o.parameters.dischargeM3S, count, random),
    magarigawaDischargeM3S: sampleRange(g.parameters.dischargeM3S, count, random),
    barrageDischargeCoefficient: sampleRange(
      ranges.structureCandidates.barrage.effectiveDischargeCoefficient, count, random,
    ),
    fishwayDischargeCoefficient: sampleRange(
      ranges.structureCandidates.fishway.effectiveDischargeCoefficient, count, random,
    ),
    fishwayEffectiveAreaM2: sampleRange(
      ranges.structureCandidates.fishway.effectiveAreaM2, count, random,
    ),
  };
  const sigma = categorical(
    ranges.bathymetryCandidates.sigmaCandidates,
    count,
    seed % ranges.bathymetryCandidates.sigmaCandidates.length,
  );
  const barrageScenario = categorical(
    ranges.structureCandidates.barrage.scenarios,
    count,
    seed % ranges.structureCandidates.barrage.scenarios.length,
  );
  const fishwayMode = categorical(
    ranges.structureCandidates.fishway.modes,
    count,
    seed % ranges.structureCandidates.fishway.modes.length,
  );

  const cases = Array.from({length: count}, (_, index) => ({
    caseId: `stage19-${String(index + 1).padStart(4, '0')}`,
    bathymetry: {
      crossSectionFamily: ranges.bathymetryCandidates.shapeFamily,
      sigma: sigma[index],
      mainstemMeanDepthM: numeric.mainstemMeanDepthM[index],
      tributaryMeanDepthM: numeric.tributaryMeanDepthM[index],
      verticalDatum: 'relative_model_datum_only',
    },
    roughness: {
      manningOpenChannel: numeric.manningOpenChannel[index],
      shallowMarginMultiplier: numeric.shallowMarginMultiplier[index],
      structureVicinityMultiplier: numeric.structureVicinityMultiplier[index],
    },
    boundaries: {
      M: {
        phaseShiftMinutes: numeric.mouthPhaseShiftMinutes[index],
        amplitudeMultiplier: numeric.mouthAmplitudeMultiplier[index],
        meanOffsetM: null,
        datum: 'relative_model_datum_only',
      },
      N: {dischargeM3S: numeric.nishikawaDischargeM3S[index]},
      O: {dischargeM3S: numeric.ongaDischargeM3S[index]},
      G: {dischargeM3S: numeric.magarigawaDischargeM3S[index]},
    },
    barrage: {
      scenario: barrageScenario[index],
      effectiveDischargeCoefficient: numeric.barrageDischargeCoefficient[index],
    },
    fishway: {
      mode: fishwayMode[index],
      effectiveDischargeCoefficient: numeric.fishwayDischargeCoefficient[index],
      effectiveAreaM2: numeric.fishwayEffectiveAreaM2[index],
    },
    classification: 'provisional_public_data_and_declared_inference_not_observation',
  }));

  return {
    schema: STAGE19_ENSEMBLE_SCHEMA,
    version: 'stage19-provisional-inference-ensemble-v1',
    status: 'generated_not_assigned_to_solver',
    generatedFrom: {
      ranges: {path: RANGE_PATH, sha256: RANGE_SHA256},
      approval: {path: APPROVAL_PATH, sha256: APPROVAL_SHA256},
    },
    seed,
    count,
    samplingMethod: 'deterministic_stratified_marginals_with_categorical_rotation',
    geometry: ranges.geometry,
    sourceRoleBindings: Object.fromEntries(
      ranges.boundaryCandidates.map(item => [item.boundaryId, {
        mappingStatus: item.mappingStatus,
        candidateSourceIds: item.candidateSourceIds,
      }]),
    ),
    casesSha256: sha256(serialize(cases)),
    safeguards: {
      singleBestGuessForbidden: true,
      inferredValuesAreObservations: false,
      absoluteMouthOffsetAssigned: false,
      physicalValuesAssignedToSolver: false,
      numericalRunEnabled: false,
      providesExecutionAuthorization: false,
      physicalValidationClaimAllowed: false,
      publicSimulatorConnected: false,
    },
    cases,
  };
}

export async function loadStage19Inputs() {
  const [rangesText, approvalText] = await Promise.all([
    fs.readFile(RANGE_PATH, 'utf8'),
    fs.readFile(APPROVAL_PATH, 'utf8'),
  ]);
  const ranges = JSON.parse(rangesText);
  const approval = JSON.parse(approvalText);
  validateInputs(ranges, rangesText, approval, approvalText);
  return {ranges, rangesText, approval, approvalText};
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const outputPath = process.argv[2] ?? 'config/stage19_provisional_ensemble_cases_v1.json';
  const inputs = await loadStage19Inputs();
  const ensemble = generateStage19Ensemble(
    inputs.ranges,
    inputs.rangesText,
    inputs.approval,
    inputs.approvalText,
  );
  const serialized = serialize(ensemble);
  await fs.writeFile(outputPath, serialized, {encoding: 'utf8', flag: 'wx'});
  console.log(JSON.stringify({
    status: ensemble.status,
    outputPath,
    count: ensemble.count,
    seed: ensemble.seed,
    casesSha256: ensemble.casesSha256,
    ensembleSha256: sha256(serialized),
    numericalRunEnabled: false,
  }, null, 2));
}
