import fs from 'node:fs/promises';

const path = process.argv[2] || 'config/stage17_inferred_physical_prior_v1.json';
const output = process.argv[3] || 'stage17-inferred-physical-prior-validation.json';
const config = JSON.parse(await fs.readFile(path, 'utf8'));

function rangeOk(value) {
  return value && Number.isFinite(value.min) && Number.isFinite(value.reference)
    && Number.isFinite(value.max) && value.min <= value.reference && value.reference <= value.max;
}

const checks = [
  ['schema', config.schema === 'onga-stage17-inferred-physical-prior-v1'],
  ['shallow water selected', config.governingEquation === 'depth_averaged_shallow_water'],
  ['water geometry frozen', config.geometry?.approvedWaterPixelCount === 679791 && config.geometry?.frozen === true],
  ['mesh frozen', config.geometry?.metricMeshCellCount === 50333],
  ['single guess forbidden', config.inferencePolicy?.singleBestGuessForbidden === true],
  ['ensemble required', config.inferencePolicy?.ensembleRequired === true],
  ['physical validation claim forbidden', config.inferencePolicy?.physicalValidationClaimAllowed === false],
  ['public connection forbidden', config.inferencePolicy?.publicSimulatorConnectionAllowed === false],
  ['visual fitting forbidden', config.inferencePolicy?.visualFittingForbidden === true],
  ['mainstem depth range valid', rangeOk(config.bathymetryPrior?.mainstemMeanDepthM)],
  ['tributary depth range valid', rangeOk(config.bathymetryPrior?.tributaryMeanDepthM)],
  ['roughness range valid', rangeOk(config.roughnessPrior?.openChannel)],
  ['M amplitude range valid', rangeOk(config.boundaryPrior?.M?.amplitudeMultiplier)],
  ['N discharge range valid', rangeOk(config.boundaryPrior?.N?.referenceDischargeM3S)],
  ['O discharge range valid', rangeOk(config.boundaryPrior?.O?.referenceDischargeM3S)],
  ['G discharge range valid', rangeOk(config.boundaryPrior?.G?.referenceDischargeM3S)],
  ['fishway disabled scenario required', config.fishwayPrior?.disabledScenarioRequired === true],
  ['barrage closed scenario required', config.barragePrior?.requiredScenarios?.includes('fully_closed')],
  ['uncertainty outputs required', ['velocity_interquartile_range','flow_direction_agreement_fraction','parameter_sensitivity_ranking'].every(x => config.requiredOutputs?.includes(x))],
  ['physical run remains disabled', config.approval?.physicalRunEnabled === false],
];

const report = {
  schema: 'onga-stage17-inferred-physical-prior-validation-v1',
  status: checks.every(([, ok]) => ok) ? 'passed' : 'failed',
  checks: checks.map(([name, ok]) => ({ name, ok })),
  safeguards: {
    physicalValidationClaimAllowed: false,
    publicSimulatorConnected: false,
    geometryChanged: false,
    singleBestGuessAllowed: false,
  },
};

await fs.writeFile(output, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
