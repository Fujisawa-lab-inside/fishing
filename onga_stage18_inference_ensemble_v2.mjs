import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import process from 'node:process';

export const STAGE18_INFERENCE_ENSEMBLE_V2_SCHEMA = 'onga-stage18-inference-ensemble-v2';
export const SOURCE_PRIOR_PATH = 'config/stage17_inferred_physical_prior_v1.json';
export const SOURCE_PRIOR_SHA256 = 'bc801566ff93f6d73ed01926fa9da195faf91d55dc5bd122905d0d5dd5e40a84';
export const SOURCE_V1_ENSEMBLE_SHA256 = '0a926fa20d6260a6cdb113b2a7d5be6807ca87f33350ce82be32ef9e13023ef2';
export const PARAMETER_CASES_SHA256 = 'f139f094c154e2c62c258bbe537b438b076bd47b2ae174242c968a6f7c2db317';
export const EXPECTED_ENSEMBLE_V2_SHA256 = 'ef0fc1cd8cba91ebbdcd0921260543f829c637b3c9508ea9c2dfeff5aa766684';

export const CORRECTED_V2_GEOMETRY = Object.freeze({
  waterAuthorityVersion: 'v4.8.0-candidate-r3',
  approvedWaterPixelCount: 680633,
  metricMeshCellCount: 50129,
  frozen: true,
});

const CASE_COUNT = 64;
const ENSEMBLE_SEED = 20260713;
const SAMPLING_METHOD = 'deterministic_stratified_marginals_with_categorical_rotation';

function assert(condition, message) {
  if (!condition) throw new Error(`[stage18-ensemble-v2] ${message}`);
}

export function sha256Text(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

export function serializeInferenceEnsembleV2(value) {
  return `${JSON.stringify(value, null, 2)}\n`;
}

export function serializeParameterCasesV2(cases) {
  return `${JSON.stringify(cases, null, 2)}\n`;
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

function stratifiedUnitSamples(count, random) {
  return shuffle(Array.from({ length: count }, (_, index) => (index + random()) / count), random);
}

function mapRange(unit, range) {
  assert(Number.isFinite(range?.min) && Number.isFinite(range?.max), 'range must have finite min/max');
  assert(range.max >= range.min, 'range max must be greater than or equal to min');
  return range.min + unit * (range.max - range.min);
}

function rounded(value, digits = 8) {
  return Number(value.toFixed(digits));
}

function categoricalSequence(values, count, offset = 0) {
  assert(Array.isArray(values) && values.length > 0, 'categorical values are required');
  return Array.from({ length: count }, (_, index) => values[(index + offset) % values.length]);
}

export function validateSourcePriorV1(prior, sourceText) {
  assert(typeof sourceText === 'string', 'exact source-prior bytes are required');
  assert(sha256Text(sourceText) === SOURCE_PRIOR_SHA256, 'source-prior SHA-256 changed');
  assert(prior?.schema === 'onga-stage17-inferred-physical-prior-v1', 'unsupported source-prior schema');
  assert(prior?.geometry?.approvedWaterPixelCount === 679791, 'source-prior water geometry changed');
  assert(prior?.geometry?.metricMeshCellCount === 50333, 'source-prior metric mesh changed');
  assert(prior?.geometry?.frozen === true, 'source-prior geometry must remain frozen');
  assert(prior?.governingEquation === 'depth_averaged_shallow_water', 'governing equation changed');
  assert(prior?.inferencePolicy?.singleBestGuessForbidden === true, 'single best guess must remain forbidden');
  assert(prior?.inferencePolicy?.ensembleRequired === true, 'ensemble must remain required');
  assert(prior?.inferencePolicy?.physicalValidationClaimAllowed === false, 'physical-validation claim must remain disabled');
  assert(prior?.inferencePolicy?.publicSimulatorConnectionAllowed === false, 'public connection must remain disabled');
  assert(prior?.inferencePolicy?.visualFittingForbidden === true, 'visual fitting must remain forbidden');
  assert(prior?.approval?.physicalRunEnabled === false, 'source prior must not authorize physical execution');
  return true;
}

function generateParameterCases(prior, count, seed) {
  const random = xorshift32(seed);
  const numericParameters = {
    mainstemMeanDepthM: prior.bathymetryPrior.mainstemMeanDepthM,
    tributaryMeanDepthM: prior.bathymetryPrior.tributaryMeanDepthM,
    thalwegOffsetFractionOfLocalWidth: prior.bathymetryPrior.thalwegOffsetFractionOfLocalWidth,
    longitudinalSmoothingLengthM: prior.bathymetryPrior.longitudinalSmoothingLengthM,
    manningOpenChannel: prior.roughnessPrior.openChannel,
    shallowMarginMultiplier: prior.roughnessPrior.shallowMarginMultiplier,
    structureVicinityMultiplier: prior.roughnessPrior.structureVicinityMultiplier,
    mouthPhaseShiftMinutes: prior.boundaryPrior.M.phaseShiftMinutes,
    mouthAmplitudeMultiplier: prior.boundaryPrior.M.amplitudeMultiplier,
    nishikawaDischargeM3S: prior.boundaryPrior.N.referenceDischargeM3S,
    ongaDischargeM3S: prior.boundaryPrior.O.referenceDischargeM3S,
    magarigawaDischargeM3S: prior.boundaryPrior.G.referenceDischargeM3S,
    fishwayDischargeCoefficient: prior.fishwayPrior.effectiveDischargeCoefficient,
    fishwayEffectiveAreaM2: prior.fishwayPrior.effectiveAreaM2,
    barrageDischargeCoefficient: prior.barragePrior.effectiveDischargeCoefficient,
  };
  const sampled = Object.fromEntries(Object.entries(numericParameters).map(([name, range]) => [
    name,
    stratifiedUnitSamples(count, random).map(unit => rounded(mapRange(unit, range))),
  ]));
  const crossSectionShapes = categoricalSequence(
    prior.bathymetryPrior.crossSectionShape,
    count,
    seed % prior.bathymetryPrior.crossSectionShape.length,
  );
  const barrageScenarios = categoricalSequence(
    prior.barragePrior.requiredScenarios,
    count,
    seed % prior.barragePrior.requiredScenarios.length,
  );
  const fishwayModes = categoricalSequence(['disabled', 'head_difference_relation'], count, seed % 2);

  return Array.from({ length: count }, (_, index) => ({
    caseId: `stage18-${String(index + 1).padStart(4, '0')}`,
    bathymetry: {
      crossSectionShape: crossSectionShapes[index],
      mainstemMeanDepthM: sampled.mainstemMeanDepthM[index],
      tributaryMeanDepthM: sampled.tributaryMeanDepthM[index],
      thalwegOffsetFractionOfLocalWidth: sampled.thalwegOffsetFractionOfLocalWidth[index],
      longitudinalSmoothingLengthM: sampled.longitudinalSmoothingLengthM[index],
      verticalDatum: 'relative_model_datum_only',
    },
    roughness: {
      manningOpenChannel: sampled.manningOpenChannel[index],
      shallowMarginMultiplier: sampled.shallowMarginMultiplier[index],
      structureVicinityMultiplier: sampled.structureVicinityMultiplier[index],
    },
    boundaries: {
      M: {
        phaseShiftMinutes: sampled.mouthPhaseShiftMinutes[index],
        amplitudeMultiplier: sampled.mouthAmplitudeMultiplier[index],
        datum: 'relative_model_datum_only',
      },
      N: { dischargeM3S: sampled.nishikawaDischargeM3S[index] },
      O: { dischargeM3S: sampled.ongaDischargeM3S[index] },
      G: { dischargeM3S: sampled.magarigawaDischargeM3S[index] },
    },
    fishway: {
      mode: fishwayModes[index],
      effectiveDischargeCoefficient: sampled.fishwayDischargeCoefficient[index],
      effectiveAreaM2: sampled.fishwayEffectiveAreaM2[index],
    },
    barrage: {
      scenario: barrageScenarios[index],
      effectiveDischargeCoefficient: sampled.barrageDischargeCoefficient[index],
      gateOpeningUncertaintyFraction: prior.barragePrior.gateOpeningUncertaintyFraction,
    },
    classification: 'provisional_inference_case_not_observation',
  }));
}

export function generateInferenceEnsembleV2(prior, options = {}) {
  const sourceText = options.sourceText;
  validateSourcePriorV1(prior, sourceText);
  const count = Number(options.count ?? CASE_COUNT);
  const seed = Number(options.seed ?? ENSEMBLE_SEED);
  assert(count === CASE_COUNT, 'v2 execution ensemble must contain exactly 64 cases');
  assert(seed === ENSEMBLE_SEED, 'v2 execution ensemble seed changed');

  const cases = generateParameterCases(prior, count, seed);
  assert(sha256Text(serializeParameterCasesV2(cases)) === PARAMETER_CASES_SHA256,
    'parameter cases differ from the frozen v1 deterministic cases');

  return {
    schema: STAGE18_INFERENCE_ENSEMBLE_V2_SCHEMA,
    generatedFrom: prior.schema,
    sourcePrior: {
      path: SOURCE_PRIOR_PATH,
      sha256: SOURCE_PRIOR_SHA256,
    },
    parameterCaseInheritance: {
      sourceEnsembleSchema: 'onga-stage18-inference-ensemble-v1',
      sourceEnsembleSerializedSha256: SOURCE_V1_ENSEMBLE_SHA256,
      casesSha256: PARAMETER_CASES_SHA256,
      policy: 'parameter_cases_identical_geometry_rebound_only',
    },
    seed,
    count,
    samplingMethod: SAMPLING_METHOD,
    governingEquation: prior.governingEquation,
    geometry: CORRECTED_V2_GEOMETRY,
    requiredOutputs: prior.requiredOutputs,
    safeguards: {
      singleBestGuessForbidden: true,
      physicalValidationClaimAllowed: false,
      publicSimulatorConnectionAllowed: false,
      visualFittingForbidden: true,
      physicalRunEnabled: false,
      providesExecutionAuthorization: false,
    },
    cases,
  };
}

export async function loadSourcePriorV1(filePath = SOURCE_PRIOR_PATH) {
  const sourceText = await fs.readFile(filePath, 'utf8');
  const prior = JSON.parse(sourceText);
  validateSourcePriorV1(prior, sourceText);
  return { prior, sourceText };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const sourcePriorPath = process.argv[2] ?? SOURCE_PRIOR_PATH;
  const outputPath = process.argv[3] ?? 'stage18-inference-ensemble-v2.json';
  const { prior, sourceText } = await loadSourcePriorV1(sourcePriorPath);
  const ensemble = generateInferenceEnsembleV2(prior, { sourceText });
  const serialized = serializeInferenceEnsembleV2(ensemble);
  assert(sha256Text(serialized) === EXPECTED_ENSEMBLE_V2_SHA256, 'serialized v2 ensemble identity changed');
  await fs.writeFile(outputPath, serialized, { encoding: 'utf8', flag: 'wx' });
  console.log(JSON.stringify({
    outputPath,
    schema: ensemble.schema,
    count: ensemble.count,
    seed: ensemble.seed,
    sha256: sha256Text(serialized),
    executionAuthorized: false,
  }));
}
