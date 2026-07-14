import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import process from 'node:process';

import { generateInferenceEnsemble as generateInferenceEnsembleV1 } from '../onga_stage18_inference_ensemble.mjs';
import {
  CORRECTED_V2_GEOMETRY,
  EXPECTED_ENSEMBLE_V2_SHA256,
  PARAMETER_CASES_SHA256,
  SOURCE_PRIOR_PATH,
  SOURCE_PRIOR_SHA256,
  SOURCE_V1_ENSEMBLE_SHA256,
  STAGE18_INFERENCE_ENSEMBLE_V2_SCHEMA,
  generateInferenceEnsembleV2,
  serializeInferenceEnsembleV2,
  serializeParameterCasesV2,
} from '../onga_stage18_inference_ensemble_v2.mjs';

const CONTRACT_PATH = 'config/stage18_full64_execution_contract_v2.json';
const CONSTRAINTS_PATH = 'data/onga_stage16_mesh_constraints_v2.json';
const WATER_MANIFEST_PATH = 'data/onga_unified_water_manifest_r3.json';
const FIXTURE_PATH = 'tools/stage18_inference_ensemble_v2_fixture.json';

const TOP_LEVEL_KEYS = Object.freeze([
  'schema',
  'status',
  'executionAuthorized',
  'authorization',
  'authorizationContract',
  'geometry',
  'meshExpected',
  'ensembleExpected',
  'run',
  'acceptance',
  'safeguards',
  'protectedPaths',
  'parameterCoverage',
  'outputs',
  'stopPolicy',
  'claimLimits',
  'visualDecision',
]);

const EXPECTED_ACCEPTANCE = Object.freeze({
  completionFractionMin: 1,
  nanCountMax: 0,
  negativeDepthCountMax: 0,
  maxCflMax: 0.95,
  maxAbsoluteMassBalanceErrorMax: 1e-8,
  maxWallSeconds: 3600,
  maxResidentMemoryMiB: 8192,
});

const EXPECTED_ACTIVE_PARAMETERS = Object.freeze([
  'bathymetry.mainstemMeanDepthM',
  'roughness.manningOpenChannel',
  'boundaries.M.phaseShiftMinutes',
  'fishway.mode',
  'fishway.effectiveDischargeCoefficient',
  'fishway.effectiveAreaM2',
  'barrage.scenario.closedVersusOpen',
]);

const EXPECTED_INACTIVE_PARAMETERS = Object.freeze([
  'bathymetry.crossSectionShape',
  'bathymetry.tributaryMeanDepthM',
  'bathymetry.thalwegOffsetFractionOfLocalWidth',
  'bathymetry.longitudinalSmoothingLengthM',
  'roughness.shallowMarginMultiplier',
  'roughness.structureVicinityMultiplier',
  'boundaries.M.amplitudeMultiplier',
  'boundaries.N.dischargeM3S',
  'boundaries.O.dischargeM3S',
  'boundaries.G.dischargeM3S',
  'barrage.effectiveDischargeCoefficient',
  'barrage.gateOpeningUncertaintyFraction',
  'barrage.scenario.openingMagnitude',
]);

const EXPECTED_PROTECTED_PATHS = Object.freeze([
  'index.html',
  'pc_full.html',
  'mobile_lite.html',
  'app.js',
  'assets/app.js',
  'OngaEstuarySimulator_Browser_Service_v4_6_PCFull_ConfluenceTracer.html',
  'OngaEstuarySimulator_Browser_Service_v4_6_MobileLite_ConfluenceTracer.html',
]);

const EXPECTED_PACKAGE_LAYOUT = Object.freeze({
  vertex_local_mm: { shape: [28411, 2], dtype: 'int32' },
  vertex_image_millipixel: { shape: [28411, 2], dtype: 'int32' },
  triangles: { shape: [50129, 3], dtype: 'int32' },
  internal_face_vertices: { shape: [71848, 2], dtype: 'int32' },
  internal_face_cells: { shape: [71848, 2], dtype: 'int32' },
  boundary_face_vertices: { shape: [6691, 2], dtype: 'int32' },
  boundary_face_cell: { shape: [6691], dtype: 'int32' },
  boundary_face_tag: { shape: [6691], dtype: 'uint8' },
  barrage_face_ids: { shape: [67], dtype: 'int32' },
  barrage_gate_id: { shape: [67], dtype: 'uint8' },
  fishway_cells: { shape: [2], dtype: 'int32' },
  fishway_components: { shape: [2], dtype: 'int32' },
});

const EXPECTED_OUTPUTS = Object.freeze({
  successRequired: [
    'execution-receipt.json',
    'onga_stage16_metric_fv_mesh_v2.npz',
    'stage16_metric_mesh_summary.json',
    'ensemble-v2.json',
    'full64-progress.json',
    'full64-report.json',
    'full64-fields.npz',
    'full64-evaluation.json',
    'full64-statistics.npz',
    'full64-statistics-summary.json',
    'full64-depth-median.png',
    'full64-velocity-median.png',
    'full64-wet-probability.png',
    'full64-direction-agreement.png',
    'full64-direction-support.png',
    'full64-judgment.svg',
    'full64-visual-manifest.json',
  ],
  diagnosticBestEffortIfStoppedAfterAuthorization: [
    'execution-receipt.json', 'full64-progress.json', 'full64-diagnostic-stop.svg',
  ],
  partialFieldArtifactAllowed: false,
  successArtifactPrefix: 'stage18-full64-v2-results-',
  diagnosticArtifactPrefix: 'stage18-full64-v2-diagnostics-',
});

function assert(condition, message) {
  if (!condition) throw new Error(`[stage18-contract-v2] ${message}`);
}

function equalJson(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function assertExactKeys(value, expected, label) {
  assert(value && typeof value === 'object' && !Array.isArray(value), `${label} must be an object`);
  assert(equalJson(Object.keys(value).sort(), [...expected].sort()), `${label} keys changed`);
}

function sha256(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

function clone(value) {
  return structuredClone(value);
}

function validatePendingContract(contract, context) {
  assertExactKeys(contract, TOP_LEVEL_KEYS, 'execution contract');
  assert(contract.schema === 'onga-stage18-full64-execution-contract-v2', 'unsupported execution-contract schema');
  assert(contract.status === 'awaiting_explicit_authorization', 'execution contract must remain pending');
  assert(contract.executionAuthorized === false, 'pending contract must not authorize execution');
  assert(contract.authorization === null, 'pending contract must not contain an active authorization');

  assert(equalJson(contract.authorizationContract, {
    schema: 'onga-stage18-full64-run-authorization-v2',
    path: 'config/stage18_full64_run_authorization_v2.json',
    required: true,
    bindingField: 'executionContract',
    oneTime: true,
    requiredSourceStatement: '承認済み橋下補正v2上で、この判断資料に示された64条件×500ステップを、承認後24時間以内に一回限りの数値安定性確認として実行してよい。',
    maxValiditySeconds: 86400,
    scope: 'exactly_64_corrected_geometry_v2_cases_for_runtime_and_numerical_stability_evidence',
  }), 'authorization-contract envelope changed');

  assert(equalJson(contract.geometry, CORRECTED_V2_GEOMETRY), 'corrected v2 geometry changed');
  const mesh = contract.meshExpected;
  assertExactKeys(mesh, [
    'version', 'candidateStatus', 'artifactFile', 'constraints', 'waterAuthority',
    'counts', 'meshArrayHashes', 'packageArrays', 'packageSha256', 'sourceProbe',
    'visualApproval',
  ], 'mesh expectation');
  assert(mesh.version === context.constraints.version, 'mesh version differs from corrected constraints');
  assert(mesh.candidateStatus === 'approved_canonical', 'mesh is not approved canonical');
  assert(mesh.candidateStatus === context.constraints.candidateStatus, 'mesh candidate status changed');
  assert(mesh.artifactFile === context.constraints.artifactFile, 'mesh artifact filename changed');
  assert(equalJson(mesh.constraints, { path: CONSTRAINTS_PATH, sha256: context.constraintsSha256 }),
    'mesh constraints identity changed');
  assert(equalJson(mesh.waterAuthority, {
    version: context.constraints.waterAuthority.version,
    pixelCount: context.constraints.waterAuthority.pixelCount,
    manifest: context.constraints.waterAuthority.manifest,
    manifestSha256: context.waterManifestSha256,
  }), 'water authority identity changed');
  assert(context.waterManifest.version === contract.geometry.waterAuthorityVersion, 'water manifest version changed');
  assert(context.waterManifest.pixelCount === contract.geometry.approvedWaterPixelCount, 'water manifest pixel count changed');

  const expectedCounts = Object.fromEntries(
    ['vertices', 'cells', 'internalFaces', 'boundaryFaces', 'barrageFaces']
      .map(key => [key, context.constraints.expected[key]]),
  );
  assert(equalJson(mesh.counts, expectedCounts), 'corrected mesh counts changed');
  assert(mesh.counts.cells === contract.geometry.metricMeshCellCount, 'geometry and mesh cell counts differ');
  assert(equalJson(mesh.meshArrayHashes, context.constraints.expected.meshArrayHashes), 'mesh array hashes changed');
  assertExactKeys(mesh.packageArrays, Object.keys(context.constraints.expected.packageArrayHashes), 'mesh package arrays');
  for (const [name, expectedHash] of Object.entries(context.constraints.expected.packageArrayHashes)) {
    const item = mesh.packageArrays[name];
    assert(equalJson({ shape: item.shape, dtype: item.dtype }, EXPECTED_PACKAGE_LAYOUT[name]),
      `${name} layout changed`);
    assert(item.sha256 === expectedHash, `${name} package hash changed`);
  }
  assert(mesh.packageSha256 === context.constraints.canonicalProbe.packageSha256, 'mesh package SHA-256 changed');
  assert(equalJson(mesh.sourceProbe, context.constraints.canonicalProbe), 'mesh source probe changed');
  assert(equalJson(mesh.visualApproval, context.constraints.visualApproval), 'mesh visual approval changed');
  assert(mesh.visualApproval.scope === 'corrected_linux_mesh_geometry_only_no_numerical_execution_authorization',
    'geometry approval scope must exclude numerical execution');
  assert(mesh.visualApproval.reviewedPackageSha256 === mesh.packageSha256,
    'visual approval is not bound to the exact Linux package');

  const ensembleExpected = contract.ensembleExpected;
  assertExactKeys(ensembleExpected, [
    'schema', 'generatedFrom', 'sourcePrior', 'parameterCaseInheritance', 'seed',
    'caseCount', 'samplingMethod', 'governingEquation', 'geometry', 'serialization',
    'sha256',
  ], 'ensemble expectation');
  assert(ensembleExpected.schema === STAGE18_INFERENCE_ENSEMBLE_V2_SCHEMA, 'v2 ensemble schema changed');
  assert(ensembleExpected.generatedFrom === context.prior.schema, 'v2 ensemble prior schema changed');
  assert(equalJson(ensembleExpected.sourcePrior, { path: SOURCE_PRIOR_PATH, sha256: SOURCE_PRIOR_SHA256 }),
    'v2 ensemble source prior changed');
  assert(equalJson(ensembleExpected.parameterCaseInheritance, context.ensembleV2.parameterCaseInheritance),
    'v1 parameter-case inheritance record changed');
  assert(ensembleExpected.seed === 20260713, 'v2 ensemble seed changed');
  assert(ensembleExpected.caseCount === 64, 'v2 ensemble case count changed');
  assert(ensembleExpected.samplingMethod === context.ensembleV2.samplingMethod, 'sampling method changed');
  assert(ensembleExpected.governingEquation === 'depth_averaged_shallow_water', 'governing equation changed');
  assert(equalJson(ensembleExpected.geometry, CORRECTED_V2_GEOMETRY), 'v2 ensemble geometry changed');
  assert(ensembleExpected.serialization === 'JSON.stringify(value,null,2)+LF', 'ensemble serialization changed');
  assert(ensembleExpected.sha256 === EXPECTED_ENSEMBLE_V2_SHA256, 'contract ensemble digest changed');
  assert(ensembleExpected.sha256 === context.ensembleV2Sha256, 'generated v2 ensemble digest mismatch');

  assert(equalJson(contract.run, {
    purpose: 'offline_runtime_and_numerical_stability_evidence_only',
    resultsClassification: 'provisional_full64_runtime_and_numerical_stability_evidence_only',
    caseCount: 64,
    ensembleSeed: 20260713,
    maxStepsPerCase: 500,
    comparisonBasis: 'equal_step_count_not_equal_simulated_time',
    checkpointCompletedCaseCounts: [1, 4, 16, 64],
  }), 'run limits changed');
  assert(equalJson(contract.acceptance, EXPECTED_ACCEPTANCE), 'acceptance thresholds changed');
  assert(equalJson(contract.parameterCoverage, {
    active: EXPECTED_ACTIVE_PARAMETERS,
    inactive: EXPECTED_INACTIVE_PARAMETERS,
  }), 'parameter coverage changed');
  assert(equalJson(contract.protectedPaths, EXPECTED_PROTECTED_PATHS), 'protected paths changed');

  const falseSafeguards = [
    'geometryApprovalIsExecutionAuthorization',
    'physicalExecutionAuthorized',
    'full64ExecutionAllowed',
    'automaticActivationAllowed',
    'automaticAdditionalRunsAllowed',
    'automaticRetryAllowed',
    'previousV1AuthorizationReusable',
    'inferredParametersAreObservations',
    'physicalValidationClaimAllowed',
    'sensitivityClaimAllowed',
    'publicSimulatorConnectionAllowed',
    'publicRuntimeEnabled',
    'legacyFlowCalculationMayChange',
    'failedCasesMayBeImputed',
  ];
  assertExactKeys(contract.safeguards, falseSafeguards, 'safeguards');
  for (const key of falseSafeguards) assert(contract.safeguards[key] === false, `${key} must remain false`);

  assert(equalJson(contract.stopPolicy, {
    immediateStopOnAnyCaseFailure: true,
    immediateStopOnNan: true,
    immediateStopOnNegativeDepth: true,
    immediateStopOnCflExceedance: true,
    immediateStopOnMassBalanceExceedance: true,
    immediateStopOnWallTimeExceedance: true,
    immediateStopOnMemoryExceedance: true,
    failedCasesMayBeImputed: false,
  }), 'fail-fast stop policy changed');

  assertExactKeys(contract.claimLimits, [
    'physicalValidationClaimAllowed',
    'sensitivityClaimAllowed',
    'inferredParametersMayBeCalledObservations',
    'publicSimulatorConnectionAllowed',
    'commonPhysicalTimeComparisonAllowed',
    'absoluteWaterSurfaceElevationClaimAllowed',
  ], 'claim limits');
  for (const [key, value] of Object.entries(contract.claimLimits)) assert(value === false, `${key} must remain false`);

  assert(equalJson(contract.visualDecision, {
    geometryDecisionRecorded: true,
    geometrySourceStatement: 'この形でよい',
    geometryDecisionScope: mesh.visualApproval.scope,
    executionDecisionRequired: true,
    executionDecisionRecorded: false,
    executionDecisionImageRequired: true,
    executionDecisionImageSha256: null,
  }), 'visual-decision contract changed');

  assert(equalJson(contract.outputs, EXPECTED_OUTPUTS), 'output contract changed');
  return true;
}

const [contractText, constraintsText, waterManifestText, priorText, fixtureText] = await Promise.all([
  fs.readFile(CONTRACT_PATH, 'utf8'),
  fs.readFile(CONSTRAINTS_PATH, 'utf8'),
  fs.readFile(WATER_MANIFEST_PATH, 'utf8'),
  fs.readFile(SOURCE_PRIOR_PATH, 'utf8'),
  fs.readFile(FIXTURE_PATH, 'utf8'),
]);
const contract = JSON.parse(contractText);
const constraints = JSON.parse(constraintsText);
const waterManifest = JSON.parse(waterManifestText);
const prior = JSON.parse(priorText);
const fixture = JSON.parse(fixtureText);

assert(sha256(priorText) === SOURCE_PRIOR_SHA256, 'source-prior bytes changed');
const ensembleV1 = generateInferenceEnsembleV1(prior, { count: 64, seed: 20260713 });
const ensembleV1Text = `${JSON.stringify(ensembleV1, null, 2)}\n`;
assert(sha256(ensembleV1Text) === SOURCE_V1_ENSEMBLE_SHA256, 'frozen v1 ensemble identity changed');
const ensembleV2 = generateInferenceEnsembleV2(prior, { sourceText: priorText });
const ensembleV2Text = serializeInferenceEnsembleV2(ensembleV2);
const ensembleV2Sha256 = sha256(ensembleV2Text);
assert(ensembleV2Sha256 === EXPECTED_ENSEMBLE_V2_SHA256, 'generated v2 ensemble identity changed');
assert(equalJson(ensembleV2.cases, ensembleV1.cases), 'v2 parameter cases differ from v1');
assert(sha256(serializeParameterCasesV2(ensembleV2.cases)) === PARAMETER_CASES_SHA256,
  'v2 parameter-case digest changed');
assert(!equalJson(ensembleV2.geometry, ensembleV1.geometry), 'v2 geometry was not rebound');
assert(equalJson(ensembleV2.geometry, CORRECTED_V2_GEOMETRY), 'v2 corrected geometry mismatch');
assert(ensembleV2.safeguards.physicalRunEnabled === false, 'v2 ensemble enabled physical execution');
assert(ensembleV2.safeguards.providesExecutionAuthorization === false, 'v2 ensemble granted execution authorization');

assert(fixture.schema === 'onga-stage18-inference-ensemble-v2-fixture-v1', 'unsupported ensemble fixture schema');
assert(equalJson(fixture.sourcePrior, { path: SOURCE_PRIOR_PATH, sha256: SOURCE_PRIOR_SHA256 }),
  'fixture source prior changed');
assert(equalJson(fixture.sourceV1Ensemble, {
  schema: 'onga-stage18-inference-ensemble-v1', sha256: SOURCE_V1_ENSEMBLE_SHA256,
}), 'fixture v1 ensemble identity changed');
assert(fixture.parameterCases.count === 64 && fixture.parameterCases.seed === 20260713,
  'fixture case count or seed changed');
assert(fixture.parameterCases.sha256 === PARAMETER_CASES_SHA256, 'fixture parameter-case digest changed');
assert(equalJson(fixture.parameterCases.first, ensembleV2.cases[0]), 'fixture first case changed');
assert(equalJson(fixture.parameterCases.last, ensembleV2.cases.at(-1)), 'fixture last case changed');
assert(fixture.ensembleV2.sha256 === ensembleV2Sha256, 'fixture v2 ensemble digest changed');
assert(equalJson(fixture.correctedGeometry, CORRECTED_V2_GEOMETRY), 'fixture corrected geometry changed');
assert(fixture.safeguards.physicalRunEnabled === false, 'fixture enabled physical execution');
assert(fixture.safeguards.providesExecutionAuthorization === false, 'fixture granted execution authorization');

const context = {
  constraints,
  constraintsSha256: sha256(constraintsText),
  waterManifest,
  waterManifestSha256: sha256(waterManifestText),
  prior,
  ensembleV2,
  ensembleV2Sha256,
};
validatePendingContract(contract, context);

const unsafeMutations = [
  value => { value.status = 'authorized'; },
  value => { value.executionAuthorized = true; },
  value => { value.authorization = {}; },
  value => { value.authorizationContract.maxValiditySeconds = 86401; },
  value => { value.geometry.metricMeshCellCount = 50333; },
  value => { value.meshExpected.packageSha256 = '0'.repeat(64); },
  value => { value.meshExpected.packageArrays.triangles.shape = [50333, 3]; },
  value => { value.ensembleExpected.sha256 = '0'.repeat(64); },
  value => { value.run.caseCount = 63; },
  value => { value.acceptance.maxCflMax = 1; },
  value => { value.safeguards.previousV1AuthorizationReusable = true; },
  value => { value.stopPolicy.immediateStopOnNan = false; },
  value => { value.claimLimits.physicalValidationClaimAllowed = true; },
  value => { value.visualDecision.executionDecisionRecorded = true; },
  value => { value.outputs.successRequired.pop(); },
  value => { value.meshExpected.unreviewedExtension = true; },
  value => { value.ensembleExpected.unreviewedExtension = true; },
];
let rejectedUnsafeMutations = 0;
for (const mutate of unsafeMutations) {
  const candidate = clone(contract);
  mutate(candidate);
  try {
    validatePendingContract(candidate, context);
  } catch {
    rejectedUnsafeMutations += 1;
  }
}
assert(rejectedUnsafeMutations === unsafeMutations.length, 'unsafe contract mutations were not all rejected');

const report = {
  schema: 'onga-stage18-full64-execution-contract-v2-validation-v1',
  status: 'passed',
  full64Executed: false,
  executionAuthorized: false,
  contractSha256: sha256(contractText),
  ensembleV2Sha256,
  parameterCasesSha256: PARAMETER_CASES_SHA256,
  sourceV1EnsembleSha256: SOURCE_V1_ENSEMBLE_SHA256,
  rejectedUnsafeMutations,
  verified: [
    'corrected approved Linux v2 mesh identity and visual-approval scope',
    'exact v1 parameter cases inherited with geometry rebound only',
    'deterministic 64-case v2 ensemble serialization digest',
    'pending execution state with no active authorization',
    'one-time v2 authorization envelope required',
    'fail-fast numerical stop policy and no failed-case imputation',
    'physical-validation, sensitivity, public-runtime, and automatic-run claims disabled',
    'success, diagnostic, and protected-surface contracts',
  ],
};
const outputPath = process.argv[2] ?? 'stage18-full64-execution-contract-v2-validation.json';
await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
console.log(JSON.stringify(report));
