import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

const GATE_PATH = 'config/stage18_full64_execution_gate_v1.json';
const RETIRED_AUTHORIZATION_PATH = 'config/stage18_full64_run_authorization_v1.json';
const CORRECTED_CONSTRAINTS_PATH = 'data/onga_stage16_mesh_constraints_v2.json';
const RETIRED_AUTHORIZATION_SHA256 = 'dbe9b61c832a3d75a54acd5042b8a27843a9ea826be27b305aaaf8911a11932f';
const RETIRED_MESH_SUMMARY_SHA256 = 'f44b1317f469e34227e83cb0910db75d75404098f0927d93a8e3316ae92060f8';
const CORRECTED_AUTHORIZATION_SCHEMA = 'onga-stage18-full64-run-authorization-v2';
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
    /^config\/stage18_full64_run_authorization_v[2-9][0-9]*\.json$/.test(gate.activeAuthorization.path),
    'active authorization must be a new versioned record',
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

async function requireActiveAuthorization(gate) {
  validateActiveGateStructure(gate);
  const resolved = path.resolve(gate.activeAuthorization.path);
  const configRoot = `${path.resolve('config')}${path.sep}`;
  assert(resolved.startsWith(configRoot), 'active authorization escapes the config directory');
  const payload = await fs.readFile(resolved);
  assert(sha256(payload) === gate.activeAuthorization.sha256, 'active authorization digest mismatch');
  const authorization = JSON.parse(payload.toString('utf8'));
  const constraints = JSON.parse(await fs.readFile(CORRECTED_CONSTRAINTS_PATH, 'utf8'));
  validateApprovedCorrectedMeshConstraints(constraints);
  validateCorrectedAuthorizationMetadata(authorization, constraints);
}

function validateCorrectedAuthorizationMetadata(authorization, constraints) {
  assert(
    authorization.schema === CORRECTED_AUTHORIZATION_SCHEMA,
    'corrected v2 authorization schema required; reformatted or renamed v1 authorization is forbidden',
  );
  assert(authorization.authorized === true, 'corrected full64 authorization must be explicit');
  assert(authorization.approvedBy === 'Ryusuke Fujisawa', 'corrected authorization approver changed');
  assert(/^20[0-9]{2}-[0-9]{2}-[0-9]{2}$/.test(authorization.approvedDate || ''), 'corrected authorization date required');
  assert(typeof authorization.sourceStatement === 'string' && authorization.sourceStatement.length > 0, 'corrected authorization source statement required');
  assert(
    authorization.scope === 'exactly_64_corrected_geometry_v2_cases_for_runtime_and_numerical_stability_evidence',
    'corrected authorization scope changed',
  );
  assertExactKeys(authorization.geometry, ['approvedWaterPixelCount', 'metricMeshCellCount', 'frozen'], 'corrected geometry');
  assert(equalJson(authorization.geometry, {
    approvedWaterPixelCount: 680633,
    metricMeshCellCount: 50129,
    frozen: true,
  }), 'corrected geometry identity mismatch');

  const expectedCounts = Object.fromEntries(
    ['vertices', 'cells', 'internalFaces', 'boundaryFaces', 'barrageFaces']
      .map(key => [key, constraints.expected[key]]),
  );
  const expectedMesh = {
    version: constraints.version,
    artifactFile: constraints.artifactFile,
    waterAuthority: constraints.waterAuthority,
    counts: expectedCounts,
    meshArrayHashes: constraints.expected.meshArrayHashes,
    packageArrayHashes: constraints.expected.packageArrayHashes,
    packageSha256: constraints.canonicalProbe.packageSha256,
    sourceProbe: constraints.canonicalProbe,
  };
  assertExactKeys(authorization.meshExpected, Object.keys(expectedMesh), 'corrected mesh identity');
  assert(equalJson(authorization.meshExpected, expectedMesh), 'corrected Linux mesh identity mismatch');
  assert(authorization.run?.caseCount === 64, 'corrected authorization must remain exactly 64 cases');
  assert(
    authorization.safeguards?.automaticAdditionalRunsAllowed === false,
    'corrected authorization must forbid automatic additional runs',
  );
}

async function assertReformattedRetiredAuthorizationRejected(gate) {
  const fixturePath = 'config/stage18_full64_run_authorization_v999999.json';
  const retired = JSON.parse(await fs.readFile(RETIRED_AUTHORIZATION_PATH, 'utf8'));
  const reformatted = `${JSON.stringify(retired, null, 4)}\n`;
  assert(sha256(reformatted) !== RETIRED_AUTHORIZATION_SHA256, 'reformatted retired fixture digest did not change');
  await fs.writeFile(fixturePath, reformatted, { flag: 'wx' });
  try {
    const candidate = structuredClone(gate);
    candidate.state = 'authorized';
    candidate.enabled = true;
    candidate.replacementAuthorizationRequired = false;
    candidate.activeAuthorization = {
      id: 'reformatted-retired-v1',
      path: fixturePath,
      sha256: sha256(reformatted),
    };
    candidate.safeguards.consumeOneTimeAuthorizationAllowed = true;
    candidate.safeguards.full64ExecutionAllowed = true;
    let rejection = '';
    try {
      await requireActiveAuthorization(candidate);
    } catch (error) {
      rejection = String(error?.message || error);
    }
    assert(
      rejection.includes('corrected v2 authorization schema required'),
      'renamed and reformatted retired v1 authorization was not rejected by schema identity',
    );
  } finally {
    await fs.unlink(fixturePath);
  }
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
    !/^\s*(?:run:\s*)?(?:python\s+)?tools\/run_stage18_full64\.py(?:\s|$)/m.test(workflow),
    'validation workflow must never execute the full64 runner',
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

const requireActive = process.argv.slice(2).includes('--require-active');
const gate = JSON.parse(await fs.readFile(GATE_PATH, 'utf8'));
const correctedConstraints = JSON.parse(await fs.readFile(CORRECTED_CONSTRAINTS_PATH, 'utf8'));
await requireRetiredAuthorizationUnchanged(gate);
validateApprovedCorrectedMeshConstraints(correctedConstraints);

if (requireActive) {
  await requireActiveAuthorization(gate);
  console.log(JSON.stringify({ state: gate.state, authorizationId: gate.activeAuthorization.id }));
} else {
  validatePendingGate(gate);
  const rejectedUnsafeMutations = validatePendingMutationRejection(gate);
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
  await assertReformattedRetiredAuthorizationRejected(gate);
  const report = {
    schema: 'onga-stage18-full64-execution-gate-validation-v1',
    status: 'passed',
    state: gate.state,
    full64ExecutionAllowed: false,
    retiredAuthorizationSha256: RETIRED_AUTHORIZATION_SHA256,
    rejectedUnsafeMutations,
    verified: [
      'retired authorization bytes and old mesh binding remain unchanged',
      'corrected Linux v2 package is canonical only for the exact recorded visual approval',
      'replacement explicit authorization is required',
      'authorization consumption and full64 execution remain disabled',
      'pending state cannot satisfy the active gate',
      'validation workflow cannot invoke full64 or retired-mesh success artifact tests',
      'superseded v1 full64 workflow is read-only and rejection-only',
      'superseded v1 pilot workflow cannot generate a mesh or invoke numerical cases',
      'superseded r2/v1 mesh workflow is read-only and cannot regenerate or push repository data',
      'renaming and reformatting retired v1 authorization cannot satisfy the corrected v2 gate',
    ],
  };
  await fs.writeFile('stage18-full64-gate-validation.json', `${JSON.stringify(report, null, 2)}\n`);
  console.log(JSON.stringify(report));
}
