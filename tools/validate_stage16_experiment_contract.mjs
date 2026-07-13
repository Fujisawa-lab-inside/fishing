import fs from 'node:fs/promises';
import {
  APPROVED_WATER_AUTHORITY,
  AUDITED_PRODUCTION_MESH,
  STAGE16_EXPERIMENT_CONTRACT_VERSION,
  canonicalScenarioJson,
  createRunManifest,
  validateExperimentScenario,
} from '../onga_stage16_experiment_contract.mjs';

const outputPath = process.argv[2] || 'stage16-experiment-contract-validation.json';

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

function syntheticSource(identifier) {
  return { kind: 'synthetic', identifier };
}

function baseScenario() {
  return {
    scenarioId: 'synthetic-contract-test',
    purpose: 'synthetic_verification',
    resultsLabel: 'synthetic_verification_only',
    geometry: {
      waterAuthorityVersion: APPROVED_WATER_AUTHORITY.version,
      waterPixelCount: APPROVED_WATER_AUTHORITY.pixelCount,
      meshVersion: 'synthetic-two-cell-v1',
      meshStatus: 'synthetic',
      bathymetry: syntheticSource('flat-bed'),
    },
    solver: {
      governingEquation: 'depth_averaged_shallow_water',
      modules: [
        { name: 'homogeneous-flux', version: 'v1' },
        { name: 'positivity', version: 'v1' },
      ],
    },
    inputs: {
      boundaries: {
        M: { mode: 'water_level', source: syntheticSource('M') },
        N: { mode: 'normal_discharge', source: syntheticSource('N') },
        O: { mode: 'normal_discharge', source: syntheticSource('O') },
        G: { mode: 'normal_discharge', source: syntheticSource('G') },
      },
      fishway: { mode: 'fixed_discharge', source: syntheticSource('fishway') },
      barrage: { mode: 'uniform_opening', source: syntheticSource('barrage') },
      roughness: syntheticSource('roughness'),
    },
    approvals: {
      geometryApproved: false,
      governingEquationApproved: false,
      physicalInputsApproved: false,
      calibrationApproved: false,
      publicReleaseApproved: false,
    },
    calibration: { performed: false, visualFitting: false },
    runtime: { publicRuntimeEnabled: false },
  };
}

const valid = validateExperimentScenario(baseScenario());
const manifestA = createRunManifest(baseScenario(), {
  codeCommit: '0123456789abcdef',
  createdAt: '2026-07-12T00:00:00.000Z',
});
const reordered = baseScenario();
reordered.inputs.boundaries = {
  G: reordered.inputs.boundaries.G,
  O: reordered.inputs.boundaries.O,
  M: reordered.inputs.boundaries.M,
  N: reordered.inputs.boundaries.N,
};
const manifestB = createRunManifest(reordered, {
  codeCommit: '0123456789abcdef',
  createdAt: '2026-07-12T00:00:00.000Z',
});

function rejected(mutator) {
  const scenario = baseScenario();
  mutator(scenario);
  try {
    validateExperimentScenario(scenario);
    return false;
  } catch (_) {
    return true;
  }
}

const wrongWaterRejected = rejected(scenario => {
  scenario.geometry.waterPixelCount = 680632;
});
const publicSyntheticRejected = rejected(scenario => {
  scenario.runtime.publicRuntimeEnabled = true;
});
const visualFittingRejected = rejected(scenario => {
  scenario.calibration.visualFitting = true;
});
const falsePhysicalLabelRejected = rejected(scenario => {
  scenario.resultsLabel = 'physical_prediction';
});
const physicalSyntheticSourceRejected = rejected(scenario => {
  scenario.purpose = 'physical_validation';
  scenario.resultsLabel = 'physical_validation_candidate';
  scenario.geometry.meshStatus = 'audited_production';
  scenario.approvals.geometryApproved = true;
  scenario.approvals.governingEquationApproved = true;
  scenario.approvals.physicalInputsApproved = true;
});
const unapprovedPublicRejected = rejected(scenario => {
  scenario.purpose = 'public_production';
  scenario.resultsLabel = 'public_prediction';
  scenario.geometry.meshStatus = 'audited_production';
  scenario.runtime.publicRuntimeEnabled = true;
});
const missingBoundaryRejected = rejected(scenario => {
  delete scenario.inputs.boundaries.O;
});

const physicalScenario = baseScenario();
physicalScenario.scenarioId = 'approved-physical-contract-test';
physicalScenario.purpose = 'physical_validation';
physicalScenario.resultsLabel = 'physical_validation_candidate';
physicalScenario.geometry.meshStatus = 'audited_production';
physicalScenario.geometry.bathymetry = {
  kind: 'observation',
  identifier: 'survey-file',
  checksum: 'sha256:test',
};
for (const id of ['M', 'N', 'O', 'G']) {
  physicalScenario.inputs.boundaries[id].source = {
    kind: 'observation',
    identifier: `${id}-observations`,
    version: 'test-v1',
  };
}
physicalScenario.inputs.fishway.source = {
  kind: 'manual', identifier: 'fishway-test', version: 'test-v1',
};
physicalScenario.inputs.barrage.source = {
  kind: 'manual', identifier: 'barrage-test', version: 'test-v1',
};
physicalScenario.inputs.roughness = {
  kind: 'derived', identifier: 'roughness-zones', version: 'test-v1',
};
physicalScenario.approvals.geometryApproved = true;
physicalScenario.approvals.governingEquationApproved = true;
physicalScenario.approvals.physicalInputsApproved = true;
physicalScenario.geometry.meshVersion = AUDITED_PRODUCTION_MESH.version;
let physicalPendingMeshRejected = false;
try {
  validateExperimentScenario(physicalScenario);
} catch (error) {
  physicalPendingMeshRejected = String(error).includes('corrected production mesh is canonical');
}

const checks = [
  check('synthetic scenario accepted', valid.purpose, 'synthetic_verification',
    valid.purpose === 'synthetic_verification'),
  check('frozen water pixel count', valid.geometry.waterPixelCount, 680633,
    valid.geometry.waterPixelCount === 680633),
  check('synthetic run executable', manifestA.executable, true, manifestA.executable),
  check('canonical hash independent of object key order', manifestB.scenarioHash, manifestA.scenarioHash,
    manifestA.scenarioHash === manifestB.scenarioHash),
  check('wrong water authority rejected', wrongWaterRejected, true, wrongWaterRejected),
  check('synthetic public runtime rejected', publicSyntheticRejected, true, publicSyntheticRejected),
  check('visual fitting rejected', visualFittingRejected, true, visualFittingRejected),
  check('synthetic physical label rejected', falsePhysicalLabelRejected, true, falsePhysicalLabelRejected),
  check('physical run with synthetic sources rejected', physicalSyntheticSourceRejected, true,
    physicalSyntheticSourceRejected),
  check('unapproved public run rejected', unapprovedPublicRejected, true, unapprovedPublicRejected),
  check('missing O boundary rejected', missingBoundaryRejected, true, missingBoundaryRejected),
  check('physical validation blocked pending canonical mesh', physicalPendingMeshRejected, true,
    physicalPendingMeshRejected),
  check('production mesh remains noncanonical', AUDITED_PRODUCTION_MESH.canonical, false,
    AUDITED_PRODUCTION_MESH.canonical === false),
  check('contract version', valid.contractVersion, STAGE16_EXPERIMENT_CONTRACT_VERSION,
    valid.contractVersion === STAGE16_EXPERIMENT_CONTRACT_VERSION),
];

const report = {
  schema: 'onga-stage16-experiment-contract-validation-v1',
  moduleVersion: STAGE16_EXPERIMENT_CONTRACT_VERSION,
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  checks,
  safeguards: {
    connectedToPublicSimulator: false,
    modifiesApprovedWaterGeometry: false,
    physicalValuesAssigned: false,
    calibrationPerformed: false,
    physicalExecutionBlockedPendingCanonicalMesh: true,
  },
};

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
