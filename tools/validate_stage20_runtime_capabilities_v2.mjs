#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const CONTRACT_PATH = path.join(ROOT, 'config/stage20_runtime_capabilities_v2.json');
const SCHEMA_PATH = path.join(ROOT, 'config/stage20_runtime_capabilities_v2.schema.json');
const ASSET_PATH = path.join(ROOT, 'config/stage20_runtime_assets_v2.json');
const FIXTURE_ROOT = path.join(ROOT, 'tests/fixtures/stage20-runtime-capabilities-v2');
const EXPECTED_MODES = Object.freeze([
  'synthetic',
  'r1c_saved_replay',
  'local_r1c_experiment',
  'f59_saved_replay',
  'fishing_decision_replay',
  'public_f59_viewer',
]);
const EXPECTED_LOCAL_ASSET_IDS = Object.freeze([
  'r1c_review_mesh',
  'r1c_initial_checkpoint',
  'r1c_diagnostic_replay_binary',
  'fishway_constant_weak_flow_coupling_candidate',
  'r1c_review_mesh_summary',
  'fishway_c2_storage_candidate',
  'physical_pilot_source_contract',
  'physical_pilot_source_mesh_manifest',
  'synthetic_mesh_binary',
  'onga_water_mask_manifest_r3',
  'onga_water_mask_rows_r3_0',
  'onga_water_mask_rows_r3_1',
  'onga_water_mask_rows_r3_2',
  'onga_water_mask_rows_r3_3',
  'physical_pilot_final_fields',
  'stage19_m_boundary_tide_candidate',
  'physical_pilot_report',
]);

function fail(code, message) {
  throw new Error(`${code}: ${message}`);
}

function requireCondition(condition, code, message) {
  if (!condition) fail(code, message);
}

function readJson(file) {
  const stat = fs.lstatSync(file);
  requireCondition(stat.isFile() && !stat.isSymbolicLink(), 'E_JSON_PATH', file);
  const value = JSON.parse(fs.readFileSync(file, 'utf8'));
  requireCondition(value && typeof value === 'object' && !Array.isArray(value), 'E_JSON_OBJECT', file);
  return value;
}

function validateContract(contract, assets) {
  requireCondition(contract.schema === 'onga-stage20-runtime-capabilities-v2' && contract.version === 2, 'E_SCHEMA', 'contract identity');
  requireCondition(contract.status === 'M0_CANDIDATE_NOT_PUBLIC_RUNTIME_AUTHORITY', 'E_STATUS', 'contract status');
  requireCondition(contract.defaultModeId === 'synthetic', 'E_DEFAULT_MODE', 'synthetic must remain default');
  requireCondition(Array.isArray(contract.modes) && contract.modes.length === EXPECTED_MODES.length, 'E_MODE_COUNT', 'exactly six modes required');
  requireCondition(Array.isArray(assets.assets), 'E_ASSET_LIST', 'asset registry assets');
  const assetIds = new Set(assets.assets.map(asset => asset.id));
  requireCondition(assetIds.size === assets.assets.length, 'E_ASSET_ID', 'asset ids must be unique');
  const assetById = new Map(assets.assets.map(asset => [asset.id, asset]));
  const seen = new Set();
  for (const mode of contract.modes) {
    requireCondition(mode && typeof mode === 'object' && !Array.isArray(mode), 'E_MODE_OBJECT', 'mode object required');
    requireCondition(EXPECTED_MODES.includes(mode.id) && !seen.has(mode.id), 'E_MODE_ID', String(mode.id));
    seen.add(mode.id);
    for (const field of ['calibrated', 'fieldPrediction', 'catchProbability', 'operationalFishingAdvice', 'safetyAuthority', 'publicRuntime']) {
      requireCondition(mode[field] === false, `E_FORBIDDEN_${field.toUpperCase()}`, `${mode.id}.${field} must be false`);
    }
    requireCondition(Array.isArray(mode.requiredAssets) && new Set(mode.requiredAssets).size === mode.requiredAssets.length, 'E_REQUIRED_ASSETS', mode.id);
    for (const assetId of mode.requiredAssets) {
      requireCondition(assetIds.has(assetId), 'E_UNKNOWN_ASSET', `${mode.id}: ${assetId}`);
      requireCondition(
        assetById.get(assetId).requiredByModes?.includes(mode.id),
        'E_ASSET_MODE_REVERSE_BINDING',
        `${mode.id}: ${assetId}`,
      );
    }
    requireCondition(Array.isArray(mode.limitationsJa) && mode.limitationsJa.length > 0, 'E_LIMITATIONS', mode.id);
    if (mode.id !== 'local_r1c_experiment') {
      requireCondition(mode.executionKind !== 'local_bounded_solver_explicit_only', 'E_NONLOCAL_EXECUTION', mode.id);
      requireCondition(mode.gateEffect !== 'explicit_run_updates_local_solver', 'E_NONLOCAL_GATE_EFFECT', mode.id);
    }
  }
  requireCondition([...seen].sort().join('\n') === [...EXPECTED_MODES].sort().join('\n'), 'E_MODE_SET', 'mode set changed');
  for (const asset of assets.assets) {
    requireCondition(
      Array.isArray(asset.requiredByModes)
        && new Set(asset.requiredByModes).size === asset.requiredByModes.length,
      'E_ASSET_REQUIRED_MODES',
      String(asset.id),
    );
    for (const modeId of asset.requiredByModes) {
      const mode = contract.modes.find(candidate => candidate.id === modeId);
      requireCondition(mode, 'E_ASSET_UNKNOWN_MODE', `${asset.id}: ${modeId}`);
      requireCondition(
        mode.requiredAssets.includes(asset.id),
        'E_MODE_ASSET_REVERSE_BINDING',
        `${asset.id}: ${modeId}`,
      );
    }
  }

  const local = contract.modes.find(mode => mode.id === 'local_r1c_experiment');
  requireCondition(local.executionKind === 'local_bounded_solver_explicit_only', 'E_LOCAL_EXECUTION_KIND', 'local execution must be explicit and bounded');
  requireCondition(local.gateEffect === 'explicit_run_updates_local_solver', 'E_LOCAL_GATE_EFFECT', 'local gates must affect only an explicit run');
  requireCondition(local.riverTideBoundaryPhysics === 'unconnected_fixed_local_conditions', 'E_LOCAL_BOUNDARY', 'river/tide must remain unconnected');
  requireCondition(local.fishwayRepresentation === 'local_uncalibrated_lumped_C2_1', 'E_LOCAL_FISHWAY', 'fishway must remain uncalibrated lumped C2.1');
  requireCondition(
    JSON.stringify(local.requiredAssets) === JSON.stringify(EXPECTED_LOCAL_ASSET_IDS),
    'E_LOCAL_ASSET_SET',
    'local runtime dependency closure changed',
  );

  const publicViewer = contract.modes.find(mode => mode.id === 'public_f59_viewer');
  requireCondition(publicViewer.availability === 'candidate_not_deployed' && publicViewer.publicRuntime === false, 'E_PUBLIC_VIEWER_AUTHORITY', 'public viewer remains undeployed candidate');
  const boundary = contract.authorityBoundary;
  requireCondition(boundary && Object.values(boundary).every(value => value === false), 'E_AUTHORITY_BOUNDARY', 'all authority flags must be false');
  return contract;
}

function applyFixture(base, fixture) {
  const copy = structuredClone(base);
  const mode = copy.modes.find(candidate => candidate.id === fixture.mutation?.modeId);
  requireCondition(mode, 'E_FIXTURE_MODE', fixture.mutation?.modeId);
  requireCondition(typeof fixture.mutation.field === 'string', 'E_FIXTURE_FIELD', fixture.path || 'fixture');
  mode[fixture.mutation.field] = fixture.mutation.value;
  return copy;
}

const schema = readJson(SCHEMA_PATH);
requireCondition(schema?.properties?.schema?.const === 'onga-stage20-runtime-capabilities-v2', 'E_SCHEMA_DOCUMENT', 'schema contract identity');
for (const field of ['fieldPrediction', 'catchProbability', 'operationalFishingAdvice', 'safetyAuthority', 'publicRuntime']) {
  requireCondition(schema?.$defs?.mode?.properties?.[field]?.const === false, 'E_SCHEMA_CLAIM', field);
}
const assets = readJson(ASSET_PATH);
requireCondition(assets.schema === 'onga-stage20-runtime-assets-v2' && assets.version === 2, 'E_ASSET_SCHEMA', 'asset registry identity');
const contract = validateContract(readJson(CONTRACT_PATH), assets);

const fixtureNames = fs.readdirSync(FIXTURE_ROOT).filter(name => name.endsWith('.json')).sort();
requireCondition(fixtureNames.length >= 4, 'E_FIXTURE_COUNT', 'at least four negative fixtures required');
for (const name of fixtureNames) {
  const fixture = readJson(path.join(FIXTURE_ROOT, name));
  requireCondition(fixture.schema === 'onga-stage20-runtime-capability-negative-fixture-v1', 'E_FIXTURE_SCHEMA', name);
  let rejected = false;
  try {
    validateContract(applyFixture(contract, fixture), assets);
  } catch (error) {
    rejected = String(error?.message || error).startsWith(`${fixture.expectedError}:`);
  }
  requireCondition(rejected, 'E_FIXTURE_NOT_REJECTED', name);
}

console.log(JSON.stringify({
  schema: 'onga-stage20-runtime-capabilities-v2-validation',
  status: 'PASS_RUNTIME_CAPABILITY_CONTRACT_V2',
  modeCount: contract.modes.length,
  negativeFixtureCount: fixtureNames.length,
  authorityGranted: false,
}, null, 2));
