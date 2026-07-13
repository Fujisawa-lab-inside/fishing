import fs from 'node:fs/promises';

function assert(condition, message) {
  if (!condition) throw new Error(message);
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
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

function stratifiedUnitSamples(count, random) {
  return shuffle(Array.from({ length: count }, (_, i) => (i + random()) / count), random);
}

function mapRange(unit, range) {
  assert(Number.isFinite(range.min) && Number.isFinite(range.max), 'range must have finite min/max');
  assert(range.max >= range.min, 'range max must be >= min');
  return range.min + unit * (range.max - range.min);
}

function rounded(value, digits = 8) {
  return Number(value.toFixed(digits));
}

function categoricalSequence(values, count, offset = 0) {
  assert(Array.isArray(values) && values.length > 0, 'categorical values required');
  return Array.from({ length: count }, (_, i) => values[(i + offset) % values.length]);
}

export function validatePrior(prior) {
  assert(prior?.schema === 'onga-stage17-inferred-physical-prior-v1', 'unsupported prior schema');
  assert(prior?.geometry?.approvedWaterPixelCount === 679791, 'approved water geometry changed');
  assert(prior?.geometry?.metricMeshCellCount === 50333, 'metric mesh changed');
  assert(prior?.geometry?.frozen === true, 'geometry must remain frozen');
  assert(prior?.inferencePolicy?.singleBestGuessForbidden === true, 'single best guess must remain forbidden');
  assert(prior?.inferencePolicy?.ensembleRequired === true, 'ensemble must remain required');
  assert(prior?.inferencePolicy?.physicalValidationClaimAllowed === false, 'physical validation claim must remain disabled');
  assert(prior?.inferencePolicy?.publicSimulatorConnectionAllowed === false, 'public connection must remain disabled');
  assert(prior?.inferencePolicy?.visualFittingForbidden === true, 'visual fitting must remain forbidden');
  assert(prior?.approval?.physicalRunEnabled === false, 'physical run must remain disabled');
  return true;
}

export function generateInferenceEnsemble(prior, options = {}) {
  validatePrior(prior);
  const count = Number(options.count ?? 64);
  const seed = Number(options.seed ?? 20260713);
  assert(Number.isInteger(count) && count >= 16 && count <= 4096, 'count must be an integer in [16,4096]');
  assert(Number.isInteger(seed) && seed >= 0 && seed <= 0xffffffff, 'seed must be uint32');

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

  const shapes = categoricalSequence(prior.bathymetryPrior.crossSectionShape, count, seed % prior.bathymetryPrior.crossSectionShape.length);
  const barrageScenarios = categoricalSequence(prior.barragePrior.requiredScenarios, count, seed % prior.barragePrior.requiredScenarios.length);
  const fishwayModes = categoricalSequence(['disabled', 'head_difference_relation'], count, seed % 2);

  const cases = Array.from({ length: count }, (_, index) => ({
    caseId: `stage18-${String(index + 1).padStart(4, '0')}`,
    bathymetry: {
      crossSectionShape: shapes[index],
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

  return {
    schema: 'onga-stage18-inference-ensemble-v1',
    generatedFrom: prior.schema,
    seed,
    count,
    samplingMethod: 'deterministic_stratified_marginals_with_categorical_rotation',
    governingEquation: prior.governingEquation,
    geometry: prior.geometry,
    requiredOutputs: prior.requiredOutputs,
    safeguards: {
      singleBestGuessForbidden: true,
      physicalValidationClaimAllowed: false,
      publicSimulatorConnectionAllowed: false,
      visualFittingForbidden: true,
      physicalRunEnabled: false,
    },
    cases,
  };
}

export async function loadPrior(path = 'config/stage17_inferred_physical_prior_v1.json') {
  const prior = JSON.parse(await fs.readFile(path, 'utf8'));
  validatePrior(prior);
  return prior;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const priorPath = process.argv[2] ?? 'config/stage17_inferred_physical_prior_v1.json';
  const outputPath = process.argv[3] ?? 'stage18-inference-ensemble.json';
  const count = Number(process.argv[4] ?? 64);
  const seed = Number(process.argv[5] ?? 20260713);
  const prior = await loadPrior(priorPath);
  const ensemble = generateInferenceEnsemble(prior, { count, seed });
  await fs.writeFile(outputPath, `${JSON.stringify(ensemble, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify({ outputPath, count, seed, status: 'generated' }));
}
