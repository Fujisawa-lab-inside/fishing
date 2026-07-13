import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

const GATE_PATH = 'config/stage18_full64_execution_gate_v1.json';
const RETIRED_AUTHORIZATION_PATH = 'config/stage18_full64_run_authorization_v1.json';
const RETIRED_AUTHORIZATION_SHA256 = 'dbe9b61c832a3d75a54acd5042b8a27843a9ea826be27b305aaaf8911a11932f';
const RETIRED_MESH_SUMMARY_SHA256 = 'f44b1317f469e34227e83cb0910db75d75404098f0927d93a8e3316ae92060f8';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function sha256(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
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

async function requireActiveAuthorization(gate) {
  validateActiveGateStructure(gate);
  const resolved = path.resolve(gate.activeAuthorization.path);
  const configRoot = `${path.resolve('config')}${path.sep}`;
  assert(resolved.startsWith(configRoot), 'active authorization escapes the config directory');
  const payload = await fs.readFile(resolved);
  assert(sha256(payload) === gate.activeAuthorization.sha256, 'active authorization digest mismatch');
  const authorization = JSON.parse(payload.toString('utf8'));
  const { validateFull64Authorization } = await import('../onga_stage18_full64_evaluator.mjs');
  assert(validateFull64Authorization(authorization), 'active authorization validation failed');
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

const requireActive = process.argv.slice(2).includes('--require-active');
const gate = JSON.parse(await fs.readFile(GATE_PATH, 'utf8'));
await requireRetiredAuthorizationUnchanged(gate);

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
  const report = {
    schema: 'onga-stage18-full64-execution-gate-validation-v1',
    status: 'passed',
    state: gate.state,
    full64ExecutionAllowed: false,
    retiredAuthorizationSha256: RETIRED_AUTHORIZATION_SHA256,
    rejectedUnsafeMutations,
    verified: [
      'retired authorization bytes and old mesh binding remain unchanged',
      'replacement explicit authorization is required',
      'authorization consumption and full64 execution remain disabled',
      'pending state cannot satisfy the active gate',
      'validation workflow cannot invoke full64 or retired-mesh success artifact tests',
    ],
  };
  await fs.writeFile('stage18-full64-gate-validation.json', `${JSON.stringify(report, null, 2)}\n`);
  console.log(JSON.stringify(report));
}
