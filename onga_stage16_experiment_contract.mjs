export const STAGE16_EXPERIMENT_CONTRACT_VERSION = 'stage16-experiment-contract-v2';
export const APPROVED_WATER_AUTHORITY = Object.freeze({
  version: 'v4.8.0-candidate-r3',
  pixelCount: 680633,
});
export const AUDITED_PRODUCTION_MESH = Object.freeze({
  version: 'stage16-metric-fv-mesh-v2',
  canonical: false,
  status: 'linux_x86_64_pinned_awaiting_visual_review',
});

const PURPOSES = new Set(['synthetic_verification', 'physical_validation', 'public_production']);
const REQUIRED_BOUNDARIES = Object.freeze(['M', 'N', 'O', 'G']);

function assert(condition, message) {
  if (!condition) throw new Error(`[stage16-contract] ${message}`);
}

function finite(value, label) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) throw new TypeError(`${label} must be finite`);
  return numeric;
}

function nonempty(value, label) {
  const text = String(value ?? '').trim();
  if (!text) throw new TypeError(`${label} must be nonempty`);
  return text;
}

function clone(value) {
  return structuredClone(value);
}

function stableObject(value) {
  if (Array.isArray(value)) return value.map(stableObject);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.keys(value).sort().map(key => [key, stableObject(value[key])]),
    );
  }
  return value;
}

export function canonicalScenarioJson(value) {
  return JSON.stringify(stableObject(value));
}

export function fnv1a32(text) {
  let hash = 0x811c9dc5;
  for (const byte of new TextEncoder().encode(String(text))) {
    hash ^= byte;
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, '0');
}

function validateDataSource(source, label, { allowSynthetic }) {
  assert(source && typeof source === 'object', `${label} source is missing`);
  const kind = nonempty(source.kind, `${label}.kind`);
  const allowed = new Set(['synthetic', 'manual', 'file', 'public_api', 'observation', 'derived']);
  assert(allowed.has(kind), `${label}.kind is unsupported`);
  if (kind === 'synthetic') assert(allowSynthetic, `${label} cannot use synthetic data for this purpose`);
  if (kind !== 'synthetic') {
    nonempty(source.identifier, `${label}.identifier`);
    nonempty(source.checksum ?? source.version, `${label}.checksum_or_version`);
  }
  return Object.freeze({
    kind,
    identifier: source.identifier ?? null,
    checksum: source.checksum ?? null,
    version: source.version ?? null,
    timeRange: source.timeRange ?? null,
    notes: source.notes ?? null,
  });
}

function validateApprovals(approvals) {
  const names = [
    'geometryApproved',
    'governingEquationApproved',
    'physicalInputsApproved',
    'calibrationApproved',
    'publicReleaseApproved',
  ];
  assert(approvals && typeof approvals === 'object', 'approvals are missing');
  return Object.freeze(Object.fromEntries(names.map(name => [name, approvals[name] === true])));
}

export function validateExperimentScenario(candidate) {
  assert(candidate && typeof candidate === 'object', 'scenario must be an object');
  const purpose = nonempty(candidate.purpose, 'purpose');
  assert(PURPOSES.has(purpose), `unsupported purpose ${purpose}`);
  const allowSynthetic = purpose === 'synthetic_verification';

  const geometry = candidate.geometry;
  assert(geometry && typeof geometry === 'object', 'geometry is missing');
  assert(geometry.waterAuthorityVersion === APPROVED_WATER_AUTHORITY.version,
    'water authority version differs from the approved frozen version');
  assert(Number(geometry.waterPixelCount) === APPROVED_WATER_AUTHORITY.pixelCount,
    `water pixel count differs from ${APPROVED_WATER_AUTHORITY.pixelCount}`);
  const meshVersion = nonempty(geometry.meshVersion, 'geometry.meshVersion');
  const meshStatus = nonempty(geometry.meshStatus, 'geometry.meshStatus');
  assert(new Set(['synthetic', 'candidate', 'audited_production']).has(meshStatus),
    'geometry.meshStatus is unsupported');
  if (!allowSynthetic) {
    assert(AUDITED_PRODUCTION_MESH.canonical === true,
      'physical runs are blocked until the corrected production mesh is canonical and visually approved');
    assert(meshVersion === AUDITED_PRODUCTION_MESH.version, 'physical run mesh version is not canonical');
    assert(meshStatus === 'audited_production', 'physical runs require an audited production mesh');
  }
  const bathymetry = validateDataSource(geometry.bathymetry, 'geometry.bathymetry', { allowSynthetic });
  if (!allowSynthetic) assert(bathymetry.kind !== 'derived' || candidate.approvals?.geometryApproved === true,
    'derived physical bathymetry requires geometry approval');

  const solver = candidate.solver;
  assert(solver && typeof solver === 'object', 'solver is missing');
  const governingEquation = nonempty(solver.governingEquation, 'solver.governingEquation');
  assert(new Set(['scalar_conservative_skeleton', 'depth_averaged_shallow_water']).has(governingEquation),
    'unsupported governing equation');
  assert(Array.isArray(solver.modules) && solver.modules.length > 0, 'solver.modules are missing');
  const modules = solver.modules.map((module, index) => Object.freeze({
    name: nonempty(module.name, `solver.modules[${index}].name`),
    version: nonempty(module.version, `solver.modules[${index}].version`),
  }));

  const inputs = candidate.inputs;
  assert(inputs && typeof inputs === 'object', 'inputs are missing');
  const boundaries = {};
  for (const id of REQUIRED_BOUNDARIES) {
    assert(inputs.boundaries?.[id], `boundary ${id} input is missing`);
    boundaries[id] = Object.freeze({
      mode: nonempty(inputs.boundaries[id].mode, `inputs.boundaries.${id}.mode`),
      source: validateDataSource(inputs.boundaries[id].source, `inputs.boundaries.${id}`, { allowSynthetic }),
    });
  }
  const fishway = Object.freeze({
    mode: nonempty(inputs.fishway?.mode, 'inputs.fishway.mode'),
    source: validateDataSource(inputs.fishway?.source, 'inputs.fishway', { allowSynthetic }),
  });
  const barrage = Object.freeze({
    mode: nonempty(inputs.barrage?.mode, 'inputs.barrage.mode'),
    source: validateDataSource(inputs.barrage?.source, 'inputs.barrage', { allowSynthetic }),
  });
  const roughness = validateDataSource(inputs.roughness, 'inputs.roughness', { allowSynthetic });

  const approvals = validateApprovals(candidate.approvals);
  const calibration = candidate.calibration ?? {};
  assert(calibration.visualFitting !== true, 'visual fitting is prohibited');
  if (calibration.performed === true) {
    assert(!allowSynthetic, 'synthetic verification may not be labelled as calibration');
    assert(approvals.calibrationApproved, 'calibration requires explicit approval');
    validateDataSource(calibration.observations, 'calibration.observations', { allowSynthetic: false });
  }

  const runtime = candidate.runtime ?? {};
  const publicRuntimeEnabled = runtime.publicRuntimeEnabled === true;
  if (purpose === 'synthetic_verification') {
    assert(!publicRuntimeEnabled, 'synthetic verification may not enable the public runtime');
    assert(candidate.resultsLabel !== 'physical_prediction', 'synthetic results may not be labelled physical predictions');
  }
  if (purpose === 'physical_validation') {
    assert(approvals.geometryApproved, 'physical validation requires geometry approval');
    assert(approvals.governingEquationApproved, 'physical validation requires governing-equation approval');
    assert(approvals.physicalInputsApproved, 'physical validation requires physical-input approval');
    assert(!publicRuntimeEnabled, 'physical validation must remain outside the public runtime');
  }
  if (purpose === 'public_production') {
    assert(approvals.geometryApproved, 'public production requires geometry approval');
    assert(approvals.governingEquationApproved, 'public production requires governing-equation approval');
    assert(approvals.physicalInputsApproved, 'public production requires physical-input approval');
    assert(approvals.calibrationApproved, 'public production requires calibration approval');
    assert(approvals.publicReleaseApproved, 'public production requires public-release approval');
    assert(publicRuntimeEnabled, 'public production must explicitly enable the public runtime');
  }

  return Object.freeze({
    schema: 'onga-stage16-experiment-scenario-v1',
    contractVersion: STAGE16_EXPERIMENT_CONTRACT_VERSION,
    scenarioId: nonempty(candidate.scenarioId, 'scenarioId'),
    purpose,
    resultsLabel: nonempty(candidate.resultsLabel, 'resultsLabel'),
    geometry: Object.freeze({
      waterAuthorityVersion: APPROVED_WATER_AUTHORITY.version,
      waterPixelCount: APPROVED_WATER_AUTHORITY.pixelCount,
      meshVersion,
      meshStatus,
      bathymetry,
    }),
    solver: Object.freeze({ governingEquation, modules: Object.freeze(modules) }),
    inputs: Object.freeze({
      boundaries: Object.freeze(boundaries),
      fishway,
      barrage,
      roughness,
    }),
    approvals,
    calibration: Object.freeze({
      performed: calibration.performed === true,
      visualFitting: false,
      observations: calibration.observations ?? null,
    }),
    runtime: Object.freeze({ publicRuntimeEnabled }),
  });
}

export function createRunManifest(scenario, metadata = {}) {
  const validated = validateExperimentScenario(scenario);
  const scenarioJson = canonicalScenarioJson(validated);
  return Object.freeze({
    schema: 'onga-stage16-run-manifest-v1',
    contractVersion: STAGE16_EXPERIMENT_CONTRACT_VERSION,
    scenario: validated,
    scenarioHash: `fnv1a32:${fnv1a32(scenarioJson)}`,
    codeCommit: nonempty(metadata.codeCommit ?? 'uncommitted', 'metadata.codeCommit'),
    createdAt: nonempty(metadata.createdAt ?? new Date().toISOString(), 'metadata.createdAt'),
    executable: validated.purpose === 'synthetic_verification'
      || (validated.approvals.geometryApproved
        && validated.approvals.governingEquationApproved
        && validated.approvals.physicalInputsApproved),
  });
}

export const Stage16ExperimentContract = Object.freeze({
  version: STAGE16_EXPERIMENT_CONTRACT_VERSION,
  approvedWaterAuthority: APPROVED_WATER_AUTHORITY,
  auditedProductionMesh: AUDITED_PRODUCTION_MESH,
  canonicalScenarioJson,
  fnv1a32,
  validateExperimentScenario,
  createRunManifest,
});
