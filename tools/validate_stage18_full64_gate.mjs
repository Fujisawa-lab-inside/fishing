import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

const GATE_PATH = 'config/stage18_full64_execution_gate_v1.json';
const RETIRED_AUTHORIZATION_PATH = 'config/stage18_full64_run_authorization_v1.json';
const CORRECTED_CONSTRAINTS_PATH = 'data/onga_stage16_mesh_constraints_v2.json';
const CORRECTED_EXECUTION_CONTRACT_PATH = 'config/stage18_full64_execution_contract_v2.json';
const CORRECTED_AUTHORIZATION_PATH = 'config/stage18_full64_run_authorization_v2.json';
const CORRECTED_DECISION_IMAGE_PATH = 'docs/visuals/stage18-v2-execution-decision.svg';
const RETIRED_AUTHORIZATION_SHA256 = 'dbe9b61c832a3d75a54acd5042b8a27843a9ea826be27b305aaaf8911a11932f';
const RETIRED_MESH_SUMMARY_SHA256 = 'f44b1317f469e34227e83cb0910db75d75404098f0927d93a8e3316ae92060f8';
const CORRECTED_AUTHORIZATION_SCHEMA = 'onga-stage18-full64-run-authorization-v2';
const CORRECTED_AUTHORIZATION_SOURCE_STATEMENT =
  '承認済み橋下補正v2上で、この判断資料に示された64条件×500ステップを、承認後24時間以内に一回限りの数値安定性確認として実行してよい。';
const EXPECTED_VISUAL_APPROVAL = Object.freeze({
  status: 'approved',
  approvedBy: 'Ryusuke Fujisawa',
  approvedDate: '2026-07-14',
  sourceStatement: 'この形でよい',
  scope: 'corrected_linux_mesh_geometry_only_no_numerical_execution_authorization',
  reviewedMeshVersion: 'stage16-metric-fv-mesh-v2',
  reviewedPackageSha256: 'f18ac352604e286be395f7ced1580f654c00b29cf65f310fcbce38fb00219fe2',
  comparisonImageSha256: '5d71c84aca13e264aa643b64161f17caa7fb36c31e0a3a987117bebe073aafda',
});

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function sha256(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

function equalJson(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function assertExactKeys(value, expected, label) {
  assert(value && typeof value === 'object' && !Array.isArray(value), `${label} must be an object`);
  assert(
    JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...expected].sort()),
    `${label} keys changed`,
  );
}

function parseExactUtcTimestamp(value, label) {
  assert(
    typeof value === 'string' && /^20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$/.test(value),
    `${label} must be an exact UTC timestamp`,
  );
  const milliseconds = Date.parse(value);
  assert(Number.isFinite(milliseconds), `${label} is invalid`);
  assert(
    new Date(milliseconds).toISOString().replace('.000Z', 'Z') === value,
    `${label} is not a canonical UTC timestamp`,
  );
  return milliseconds;
}

function validateAuthorizationValidityWindow(authorization, options = {}) {
  const issuedAt = parseExactUtcTimestamp(authorization.issuedAtUtc, 'authorization issuedAtUtc');
  const notAfter = parseExactUtcTimestamp(authorization.notAfterUtc, 'authorization notAfterUtc');
  const validitySeconds = (notAfter - issuedAt) / 1000;
  assert(validitySeconds > 0, 'authorization validity window must be positive');
  assert(validitySeconds <= 86400, 'authorization validity window exceeds 24 hours');
  if (options.enforceCurrentTime === true) {
    const now = Date.now();
    assert(now >= issuedAt, 'corrected v2 authorization is not valid yet');
    assert(now <= notAfter, 'corrected v2 authorization has expired');
  }
}

function validateCommonGate(gate) {
  assertExactKeys(gate, [
    'schema', 'state', 'enabled', 'replacementAuthorizationRequired',
    'activeAuthorization', 'retiredAuthorization', 'safeguards',
  ], 'execution gate');
  assert(gate.schema === 'onga-stage18-full64-execution-gate-v1', 'unsupported execution-gate schema');
  assert(typeof gate.enabled === 'boolean', 'execution-gate enabled flag must be boolean');
  assert(typeof gate.replacementAuthorizationRequired === 'boolean', 'replacement-authorization flag must be boolean');
  assertExactKeys(gate.retiredAuthorization, ['path', 'sha256', 'retiredDate', 'reason'], 'retired authorization');
  assert(gate.retiredAuthorization.path === RETIRED_AUTHORIZATION_PATH, 'retired authorization path changed');
  assert(gate.retiredAuthorization.sha256 === RETIRED_AUTHORIZATION_SHA256, 'retired authorization digest changed');
  assert(gate.retiredAuthorization.retiredDate === '2026-07-14', 'retirement date changed');
  assert(
    gate.retiredAuthorization.reason === 'canonical_water_geometry_and_metric_mesh_changed',
    'retirement reason changed',
  );
  assertExactKeys(gate.safeguards, [
    'consumeOneTimeAuthorizationAllowed', 'full64ExecutionAllowed', 'automaticActivationAllowed',
  ], 'execution-gate safeguards');
  assert(gate.safeguards.automaticActivationAllowed === false, 'automatic gate activation must remain forbidden');
}

function validatePendingGate(gate) {
  validateCommonGate(gate);
  assert(gate.state === 'awaiting_new_explicit_authorization', 'execution gate is not in the required pending state');
  assert(gate.enabled === false, 'pending execution gate must be disabled');
  assert(gate.replacementAuthorizationRequired === true, 'replacement authorization must be required');
  assert(gate.activeAuthorization === null, 'pending execution gate must not name an active authorization');
  assert(gate.safeguards.consumeOneTimeAuthorizationAllowed === false, 'pending gate must forbid authorization consumption');
  assert(gate.safeguards.full64ExecutionAllowed === false, 'pending gate must forbid full64 execution');
}

function validateActiveGateStructure(gate) {
  validateCommonGate(gate);
  assert(gate.state === 'authorized', 'execution gate is not active');
  assert(gate.enabled === true, 'execution gate is disabled');
  assert(gate.replacementAuthorizationRequired === false, 'replacement authorization is still required');
  assertExactKeys(gate.activeAuthorization, ['id', 'path', 'sha256'], 'active authorization');
  assert(/^[a-z0-9][a-z0-9._-]{7,127}$/.test(gate.activeAuthorization.id), 'active authorization ID is invalid');
  assert(
    gate.activeAuthorization.path === CORRECTED_AUTHORIZATION_PATH,
    'active authorization must be the corrected-v2 record',
  );
  assert(/^[a-f0-9]{64}$/.test(gate.activeAuthorization.sha256), 'active authorization SHA-256 is invalid');
  assert(gate.activeAuthorization.sha256 !== RETIRED_AUTHORIZATION_SHA256, 'retired authorization cannot be reactivated');
  assert(gate.safeguards.consumeOneTimeAuthorizationAllowed === true, 'active gate must explicitly allow one-time consumption');
  assert(gate.safeguards.full64ExecutionAllowed === true, 'active gate must explicitly allow full64 execution');
}

async function requireRetiredAuthorizationUnchanged(gate) {
  const payload = await fs.readFile(gate.retiredAuthorization.path);
  assert(sha256(payload) === RETIRED_AUTHORIZATION_SHA256, 'retired authorization bytes changed');
  const authorization = JSON.parse(payload.toString('utf8'));
  assert(authorization.authorized === true, 'retired authorization audit record changed');
  assert(
    authorization.meshExpected?.summarySha256 === RETIRED_MESH_SUMMARY_SHA256,
    'retired mesh binding changed',
  );
}

function validateApprovedCorrectedMeshConstraints(constraints) {
  assert(constraints.schema === 'onga-stage16-mesh-constraints-v2', 'corrected mesh constraints schema changed');
  assert(constraints.version === 'stage16-metric-fv-mesh-v2', 'corrected mesh version changed');
  assert(constraints.candidateStatus === 'approved_canonical', 'corrected mesh visual approval is not canonical');
  assert(equalJson(constraints.visualApproval, EXPECTED_VISUAL_APPROVAL), 'corrected mesh visual approval record changed');
  assert(
    constraints.visualApproval.reviewedPackageSha256 === constraints.canonicalProbe.packageSha256,
    'visual approval is not bound to the pinned Linux package',
  );
}

function validateDecisionImageBinding(decisionImage, decisionPayload) {
  assert(decisionImage.path === CORRECTED_DECISION_IMAGE_PATH, 'authorization decision-image path changed');
  assert(sha256(decisionPayload) === decisionImage.sha256, 'authorization decision-image digest mismatch');
}

async function requireActiveAuthorization(gate, options = {}) {
  validateActiveGateStructure(gate);
  const resolved = path.resolve(gate.activeAuthorization.path);
  const configRoot = `${path.resolve('config')}${path.sep}`;
  assert(resolved.startsWith(configRoot), 'active authorization escapes the config directory');
  const payload = await fs.readFile(resolved);
  assert(sha256(payload) === gate.activeAuthorization.sha256, 'active authorization digest mismatch');
  const authorization = JSON.parse(payload.toString('utf8'));
  const constraints = JSON.parse(await fs.readFile(CORRECTED_CONSTRAINTS_PATH, 'utf8'));
  const contractPayload = await fs.readFile(CORRECTED_EXECUTION_CONTRACT_PATH);
  const contract = JSON.parse(contractPayload.toString('utf8'));
  validateApprovedCorrectedMeshConstraints(constraints);
  validateCorrectedAuthorizationMetadata(
    authorization,
    contract,
    sha256(contractPayload),
    gate.activeAuthorization.id,
    options,
  );
  const decisionPath = path.resolve(authorization.decisionImage.path);
  const repositoryRoot = `${path.resolve('.')}${path.sep}`;
  assert(decisionPath.startsWith(repositoryRoot), 'authorization decision image escapes the repository');
  const decisionPayload = await fs.readFile(decisionPath);
  validateDecisionImageBinding(authorization.decisionImage, decisionPayload);
}

function validateCorrectedAuthorizationMetadata(
  authorization,
  contract,
  contractSha256,
  authorizationId,
  options = {},
) {
  assertExactKeys(authorization, [
    'schema', 'authorizationId', 'authorized', 'oneTime', 'approvedBy',
    'approvedDate', 'issuedAtUtc', 'notAfterUtc', 'sourceStatement', 'scope', 'decisionImage',
    'executionContract', 'reviewedCodeCommit', 'geometry', 'meshExpected',
    'ensembleExpected', 'run', 'acceptance', 'safeguards',
  ], 'corrected authorization');
  assert(
    authorization.schema === CORRECTED_AUTHORIZATION_SCHEMA,
    'corrected v2 authorization schema required; reformatted or renamed v1 authorization is forbidden',
  );
  assert(authorization.authorized === true, 'corrected full64 authorization must be explicit');
  assert(authorization.oneTime === true, 'corrected full64 authorization must be one-time');
  assert(authorization.authorizationId === authorizationId, 'corrected authorization ID differs from the active gate');
  assert(authorization.approvedBy === 'Ryusuke Fujisawa', 'corrected authorization approver changed');
  assert(/^20[0-9]{2}-[0-9]{2}-[0-9]{2}$/.test(authorization.approvedDate || ''), 'corrected authorization date required');
  validateAuthorizationValidityWindow(authorization, options);
  assert(
    authorization.sourceStatement === CORRECTED_AUTHORIZATION_SOURCE_STATEMENT,
    'corrected authorization source statement must exactly match the visual execution decision',
  );
  assert(
    authorization.scope === 'exactly_64_corrected_geometry_v2_cases_for_runtime_and_numerical_stability_evidence',
    'corrected authorization scope changed',
  );
  assert(/^[a-f0-9]{40}$/.test(authorization.reviewedCodeCommit || ''), 'reviewed code commit is invalid');
  assertExactKeys(authorization.decisionImage, ['path', 'sha256'], 'authorization decision image');
  assert(authorization.decisionImage.path === CORRECTED_DECISION_IMAGE_PATH, 'authorization decision-image path changed');
  assert(/^[a-f0-9]{64}$/.test(authorization.decisionImage.sha256 || ''), 'authorization decision-image digest required');
  assert(equalJson(authorization.executionContract, {
    path: CORRECTED_EXECUTION_CONTRACT_PATH,
    sha256: contractSha256,
  }), 'authorization execution-contract binding changed');
  assert(contract.schema === 'onga-stage18-full64-execution-contract-v2', 'corrected execution-contract schema changed');
  assert(contract.status === 'awaiting_explicit_authorization', 'immutable execution-contract status changed');
  assert(contract.executionAuthorized === false && contract.authorization === null,
    'immutable execution contract must not self-authorize');
  assert(equalJson(contract.authorizationContract, {
    schema: CORRECTED_AUTHORIZATION_SCHEMA,
    path: CORRECTED_AUTHORIZATION_PATH,
    required: true,
    bindingField: 'executionContract',
    oneTime: true,
    requiredSourceStatement: CORRECTED_AUTHORIZATION_SOURCE_STATEMENT,
    maxValiditySeconds: 86400,
    scope: 'exactly_64_corrected_geometry_v2_cases_for_runtime_and_numerical_stability_evidence',
  }), 'immutable execution-contract authorization envelope changed');
  assert(contract.safeguards?.previousV1AuthorizationReusable === false,
    'immutable execution contract must reject previous v1 authorization reuse');
  assert(
    contract.visualDecision?.executionDecisionRequired === true
      && contract.visualDecision?.executionDecisionRecorded === false
      && contract.visualDecision?.executionDecisionImageRequired === true,
    'immutable execution contract must retain the pending visual execution decision',
  );
  for (const key of ['geometry', 'meshExpected', 'ensembleExpected', 'run', 'acceptance']) {
    assert(equalJson(authorization[key], contract[key]), `corrected authorization ${key} differs from contract`);
  }
  assertExactKeys(authorization.safeguards, [
    'automaticAdditionalRunsAllowed', 'automaticRetryAllowed',
    'inferredParametersAreObservations', 'physicalValidationClaimAllowed',
    'sensitivityClaimAllowed', 'publicSimulatorConnectionAllowed',
    'legacyFlowCalculationMayChange', 'failedCasesMayBeImputed',
  ], 'authorization safeguards');
  for (const [key, value] of Object.entries(authorization.safeguards)) {
    assert(value === false, `corrected authorization safeguard must remain false: ${key}`);
  }
}

async function assertReformattedRetiredAuthorizationRejected(contract, contractSha256) {
  const retiredText = await fs.readFile(RETIRED_AUTHORIZATION_PATH, 'utf8');
  const retired = JSON.parse(retiredText);
  const reformatted = `${JSON.stringify(retired, null, 4)}\n`;
  assert(sha256(reformatted) !== RETIRED_AUTHORIZATION_SHA256, 'reformatted retired fixture digest did not change');
  let rejection = '';
  try {
    validateCorrectedAuthorizationMetadata(
      retired,
      contract,
      contractSha256,
      'reformatted-retired-v1',
    );
  } catch (error) {
    rejection = String(error?.message || error);
  }
  assert(rejection.length > 0, 'renamed and reformatted retired v1 authorization satisfied corrected-v2 metadata');
}

function validateStaticFutureActivePath(gate, contract, contractSha256, decisionPayload) {
  const authorizationId = 'stage18-v2-static-fixture';
  const activeGate = structuredClone(gate);
  activeGate.state = 'authorized';
  activeGate.enabled = true;
  activeGate.replacementAuthorizationRequired = false;
  activeGate.activeAuthorization = {
    id: authorizationId,
    path: CORRECTED_AUTHORIZATION_PATH,
    sha256: '0'.repeat(64),
  };
  activeGate.safeguards.consumeOneTimeAuthorizationAllowed = true;
  activeGate.safeguards.full64ExecutionAllowed = true;
  validateActiveGateStructure(activeGate);

  const authorization = {
    schema: CORRECTED_AUTHORIZATION_SCHEMA,
    authorizationId,
    authorized: true,
    oneTime: true,
    approvedBy: 'Ryusuke Fujisawa',
    approvedDate: '2026-07-14',
    issuedAtUtc: '2026-07-14T00:00:00Z',
    notAfterUtc: '2026-07-15T00:00:00Z',
    sourceStatement: CORRECTED_AUTHORIZATION_SOURCE_STATEMENT,
    scope: 'exactly_64_corrected_geometry_v2_cases_for_runtime_and_numerical_stability_evidence',
    decisionImage: {
      path: CORRECTED_DECISION_IMAGE_PATH,
      sha256: sha256(decisionPayload),
    },
    executionContract: {
      path: CORRECTED_EXECUTION_CONTRACT_PATH,
      sha256: contractSha256,
    },
    reviewedCodeCommit: '0'.repeat(40),
    geometry: structuredClone(contract.geometry),
    meshExpected: structuredClone(contract.meshExpected),
    ensembleExpected: structuredClone(contract.ensembleExpected),
    run: structuredClone(contract.run),
    acceptance: structuredClone(contract.acceptance),
    safeguards: {
      automaticAdditionalRunsAllowed: false,
      automaticRetryAllowed: false,
      inferredParametersAreObservations: false,
      physicalValidationClaimAllowed: false,
      sensitivityClaimAllowed: false,
      publicSimulatorConnectionAllowed: false,
      legacyFlowCalculationMayChange: false,
      failedCasesMayBeImputed: false,
    },
  };
  const validateFixture = value => {
    validateCorrectedAuthorizationMetadata(value, contract, contractSha256, authorizationId);
    validateDecisionImageBinding(value.decisionImage, decisionPayload);
  };
  validateFixture(authorization);

  const unsafeMutations = [
    value => { value.schema = 'onga-stage18-full64-run-authorization-v1'; },
    value => { value.authorized = false; },
    value => { value.oneTime = false; },
    value => { value.issuedAtUtc = '2026-07-14T00:00:00+00:00'; },
    value => { value.notAfterUtc = '2026-07-13T23:59:59Z'; },
    value => { value.notAfterUtc = '2026-07-15T00:00:01Z'; },
    value => { value.sourceStatement = '進めてください'; },
    value => { value.decisionImage.path = 'docs/visuals/other.svg'; },
    value => { value.decisionImage.sha256 = 'f'.repeat(64); },
    value => { value.executionContract.sha256 = 'f'.repeat(64); },
    value => { value.reviewedCodeCommit = 'not-a-commit'; },
    value => { value.geometry.metricMeshCellCount = 50333; },
    value => { value.safeguards.automaticRetryAllowed = true; },
    value => { value.unreviewedExtension = true; },
  ];
  let rejected = 0;
  for (const mutate of unsafeMutations) {
    const candidate = structuredClone(authorization);
    mutate(candidate);
    try {
      validateFixture(candidate);
    } catch {
      rejected += 1;
    }
  }
  assert(rejected === unsafeMutations.length, 'unsafe future-active authorization fixtures were not all rejected');
  return rejected;
}

function validatePendingMutationRejection(gate) {
  const mutations = [
    value => { value.enabled = true; },
    value => { value.state = 'authorized'; },
    value => { value.replacementAuthorizationRequired = false; },
    value => { value.activeAuthorization = {}; },
    value => { value.retiredAuthorization.sha256 = '0'.repeat(64); },
    value => { value.safeguards.consumeOneTimeAuthorizationAllowed = true; },
    value => { value.safeguards.full64ExecutionAllowed = true; },
    value => { value.safeguards.automaticActivationAllowed = true; },
  ];
  let rejected = 0;
  for (const mutate of mutations) {
    const candidate = structuredClone(gate);
    mutate(candidate);
    try {
      validatePendingGate(candidate);
    } catch {
      rejected += 1;
    }
  }
  assert(rejected === mutations.length, 'unsafe pending-gate mutations were not all rejected');
  return rejected;
}

async function assertValidationWorkflowCannotRunFull64() {
  const workflow = await fs.readFile('.github/workflows/stage18-full64-validation.yml', 'utf8');
  assert(
    !/^\s*(?:run:\s*)?(?:python(?:3)?\s+)?tools\/run_stage18_full64\.py(?:\s|$)/m.test(workflow),
    'validation workflow must never execute the full64 runner',
  );
  assert(
    !/^\s*(?:run:\s*)?(?:python(?:3)?\s+)?tools\/run_stage18_full64_v2\.py(?:\s|$)/m.test(workflow),
    'validation workflow must never execute the corrected-v2 full64 runner',
  );
  assert(
    !/^\s*run:\s*python tools\/validate_stage18_full64_artifacts\.py\s*$/m.test(workflow),
    'pending validation must not require retired-mesh success artifacts',
  );
}

async function assertRetiredFull64WorkflowCannotRun() {
  const workflow = await fs.readFile('.github/workflows/stage18-full64-run.yml', 'utf8');
  assert(workflow.includes('reject-superseded-v1-full64'), 'retired full64 rejection job is missing');
  assert(workflow.includes('Reject superseded v1 full64 run'), 'retired full64 rejection step is missing');
  assert(workflow.includes('contents: read'), 'retired full64 workflow must be read-only');
  assert(workflow.includes('exit 1'), 'retired full64 workflow must fail explicitly');
  assert(!workflow.includes('run_stage18_full64.py'), 'retired full64 workflow must not invoke its runner');
  assert(!workflow.includes('generate_stage16_metric_mesh.py'), 'retired full64 workflow must not generate a mesh');
  assert(!workflow.includes('actions/checkout@'), 'retired full64 workflow must reject before checkout');
}

async function assertRetiredPilotCannotRun() {
  const workflow = (await fs.readFile('.github/workflows/stage18-production-pilot-run.yml', 'utf8')).replaceAll('\r\n', '\n');
  const expected = `name: Stage 18 superseded production mesh pilot

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  reject-superseded-v1-pilot:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - name: Reject superseded v1 geometry pilot
        run: |
          echo 'The v1 production-mesh pilot is retired after the Ashiya bridge geometry correction.' >&2
          echo 'Create a separate v2 pilot contract after visual approval; this workflow cannot run numerical cases.' >&2
          exit 1
`;
  assert(workflow === expected, 'retired pilot must remain the exact rejection-only definition');
}

async function assertRetiredMeshGeneratorCannotWrite() {
  const workflow = (await fs.readFile('.github/workflows/stage16-metric-mesh-generation.yml', 'utf8')).replaceAll('\r\n', '\n');
  const expected = `name: Stage 16 superseded metric mesh generation

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  reject-superseded-v1-generation:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - name: Reject superseded r2/v1 mesh generation
        run: |
          echo 'The r2/v1 metric-mesh generator is retired after the Ashiya bridge geometry correction.' >&2
          echo 'Use the separately reviewed r3/v2 Linux artifact flow; this workflow cannot modify repository data.' >&2
          exit 1
`;
  assert(workflow === expected, 'retired mesh generator must remain the exact read-only rejection definition');
}

const cliArgs = process.argv.slice(2);
let requireActive = false;
let outputPath = 'stage18-full64-gate-validation.json';
for (let index = 0; index < cliArgs.length; index += 1) {
  const argument = cliArgs[index];
  if (argument === '--require-active') {
    requireActive = true;
  } else if (argument === '--output') {
    index += 1;
    assert(index < cliArgs.length && !cliArgs[index].startsWith('--'), '--output requires a path');
    outputPath = cliArgs[index];
  } else {
    throw new Error(`unsupported argument: ${argument}`);
  }
}
const gate = JSON.parse(await fs.readFile(GATE_PATH, 'utf8'));
const correctedConstraints = JSON.parse(await fs.readFile(CORRECTED_CONSTRAINTS_PATH, 'utf8'));
await requireRetiredAuthorizationUnchanged(gate);
validateApprovedCorrectedMeshConstraints(correctedConstraints);

if (requireActive) {
  await requireActiveAuthorization(gate, { enforceCurrentTime: true });
  const report = {
    schema: 'onga-stage18-full64-execution-gate-validation-v1',
    status: 'passed',
    state: gate.state,
    full64ExecutionAllowed: true,
    full64Executed: false,
    authorizationId: gate.activeAuthorization.id,
    authorizationSha256: gate.activeAuthorization.sha256,
    retiredAuthorizationSha256: RETIRED_AUTHORIZATION_SHA256,
    verified: [
      'retired authorization bytes and old mesh binding remain unchanged',
      'active gate names only the exact corrected-v2 authorization path and digest',
      'authorization schema, immutable contract, and one-time scope agree exactly',
      'authorization is bound to the exact visual decision path, bytes, and source statement',
      'authorization is currently within its exact UTC validity window of at most 24 hours',
      'previous v1 authorization reuse, automatic retry, and additional runs remain forbidden',
      'this validation did not start a numerical case',
    ],
  };
  await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`);
  console.log(JSON.stringify(report));
} else {
  validatePendingGate(gate);
  const rejectedUnsafeMutations = validatePendingMutationRejection(gate);
  const contractPayload = await fs.readFile(CORRECTED_EXECUTION_CONTRACT_PATH);
  const contract = JSON.parse(contractPayload.toString('utf8'));
  const decisionPayload = await fs.readFile(CORRECTED_DECISION_IMAGE_PATH);
  const rejectedUnsafeActiveFixtures = validateStaticFutureActivePath(
    gate,
    contract,
    sha256(contractPayload),
    decisionPayload,
  );
  let pendingRejectedAsActive = false;
  try {
    validateActiveGateStructure(gate);
  } catch {
    pendingRejectedAsActive = true;
  }
  assert(pendingRejectedAsActive, 'pending gate was accepted as active');
  await assertValidationWorkflowCannotRunFull64();
  await assertRetiredFull64WorkflowCannotRun();
  await assertRetiredPilotCannotRun();
  await assertRetiredMeshGeneratorCannotWrite();
  await assertReformattedRetiredAuthorizationRejected(contract, sha256(contractPayload));
  const report = {
    schema: 'onga-stage18-full64-execution-gate-validation-v1',
    status: 'passed',
    state: gate.state,
    full64ExecutionAllowed: false,
    full64Executed: false,
    retiredAuthorizationSha256: RETIRED_AUTHORIZATION_SHA256,
    rejectedUnsafeMutations,
    rejectedUnsafeActiveFixtures,
    verified: [
      'retired authorization bytes and old mesh binding remain unchanged',
      'corrected Linux v2 package is canonical only for the exact recorded visual approval',
      'replacement explicit authorization is required',
      'authorization consumption and full64 execution remain disabled',
      'pending state cannot satisfy the active gate',
      'future active gate and exact corrected-v2 authorization schema are statically validated without an authorization file',
      'authorization is bound to the exact visual decision path, bytes, and source statement',
      'future authorization timestamps must be canonical UTC with a positive validity window of at most 24 hours',
      'validation workflow cannot invoke full64 or retired-mesh success artifact tests',
      'superseded v1 full64 workflow is read-only and rejection-only',
      'superseded v1 pilot workflow cannot generate a mesh or invoke numerical cases',
      'superseded r2/v1 mesh workflow is read-only and cannot regenerate or push repository data',
      'renaming and reformatting retired v1 authorization cannot satisfy the corrected v2 gate',
    ],
  };
  await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`);
  console.log(JSON.stringify(report));
}
