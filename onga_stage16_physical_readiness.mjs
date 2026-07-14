import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';

const READINESS_PROFILES = Object.freeze({
  'onga-stage16-physical-readiness-v1': Object.freeze({
    version: 'stage16-physical-readiness-v1',
    cellCount: 50333,
    approvedWaterPixelCount: 679791,
    manifest: '../data/stage16/onga_fv_metric_mesh_compact_manifest_v1.json',
  }),
  'onga-stage16-physical-readiness-v2': Object.freeze({
    version: 'stage16-physical-readiness-v2',
    cellCount: 50129,
    approvedWaterPixelCount: 680633,
    meshVersion: 'stage16-metric-fv-mesh-v2',
    artifactFile: 'onga_stage16_metric_fv_mesh_v2.npz',
    waterAuthorityVersion: 'v4.8.0-candidate-r3',
    waterManifest: '../data/onga_unified_water_manifest_r3.json',
    waterManifestSha256: '964eaa8d43607d0ac4cc6d81f37fa8a9ed8dc23563894ddce85b4252938fcbf7',
    waterRowChunks: Object.freeze([
      Object.freeze({
        path: '../data/onga_water_rows_r3_0.json',
        sha256: 'ecbedb7475c53357f60650e194b58e88f25f9cbc13aa6b6277ecb2293a0a47c0',
      }),
      Object.freeze({
        path: '../data/onga_water_rows_r3_1.json',
        sha256: 'ef373644c0b325d396ed8f03c1fcf6b4a34dfb8d4330e363e99118b5bdaa0ee8',
      }),
      Object.freeze({
        path: '../data/onga_water_rows_r3_2.json',
        sha256: '0bebd9f5b735bfc990f7d9e00b564e7d9a9aca64bb1b17006fe128bcd452f443',
      }),
      Object.freeze({
        path: '../data/onga_water_rows_r3_3.json',
        sha256: '9e55ca5fc0fddfbbfdd83d0dcea6b28ad41c91eb78adf5e39fc8eca1cf5ee48e',
      }),
    ]),
    constraints: '../data/onga_stage16_mesh_constraints_v2.json',
    constraintsSha256: '44c629ba6b7eb7bf0c43a1863de0c4835d8d331c0d230e50d891a0b23043fb33',
    packageSha256: 'f18ac352604e286be395f7ced1580f654c00b29cf65f310fcbce38fb00219fe2',
  }),
});

export const STAGE16_PHYSICAL_READINESS_VERSION = 'stage16-physical-readiness-v2';
export const STAGE16_PHYSICAL_READINESS_SCHEMAS = Object.freeze(Object.keys(READINESS_PROFILES));
const VERIFIED_CONFIGURATIONS = new WeakSet();

function assert(condition, message) {
  if (!condition) throw new Error(`[stage16-readiness] ${message}`);
}

function readinessProfile(config) {
  const profile = Object.hasOwn(READINESS_PROFILES, config?.schema)
    ? READINESS_PROFILES[config.schema]
    : null;
  assert(profile, `unsupported schema ${String(config?.schema)}`);
  return profile;
}

function deepFreeze(value) {
  if (!value || typeof value !== 'object' || Object.isFrozen(value)) return value;
  for (const child of Object.values(value)) deepFreeze(child);
  return Object.freeze(value);
}

function runtimeMeshPackageReady(mesh, profile) {
  const resource = mesh?.runtimePackage;
  return resource && typeof resource === 'object'
    && nonempty(resource.path)
    && resource.sha256 === profile.packageSha256
    && resource.approved === true;
}

function validateMeshIdentity(mesh, profile) {
  assert(Number(mesh?.cellCount) === profile.cellCount, 'mesh cell count mismatch');
  assert(Number(mesh?.approvedWaterPixelCount) === profile.approvedWaterPixelCount,
    'approved water pixel count mismatch');
  if (profile.version === 'stage16-physical-readiness-v1') {
    assert(mesh.manifest === profile.manifest, 'historical v1 mesh manifest mismatch');
    return;
  }
  assert(mesh.version === profile.meshVersion, 'mesh version mismatch');
  assert(mesh.artifactFile === profile.artifactFile, 'mesh artifact filename mismatch');
  assert(mesh.waterAuthorityVersion === profile.waterAuthorityVersion,
    'water-authority version mismatch');
  assert(mesh.waterManifest === profile.waterManifest, 'water manifest path mismatch');
  assert(mesh.waterManifestSha256 === profile.waterManifestSha256,
    'water manifest digest mismatch');
  assert(Array.isArray(mesh.waterRowChunks)
    && mesh.waterRowChunks.length === profile.waterRowChunks.length,
  'water row-chunk inventory mismatch');
  for (const [index, expected] of profile.waterRowChunks.entries()) {
    assert(mesh.waterRowChunks[index]?.path === expected.path,
      `water row chunk ${index} path mismatch`);
    assert(mesh.waterRowChunks[index]?.sha256 === expected.sha256,
      `water row chunk ${index} digest mismatch`);
  }
  assert(mesh.constraints === profile.constraints, 'mesh constraints path mismatch');
  assert(mesh.constraintsSha256 === profile.constraintsSha256,
    'mesh constraints digest mismatch');
  assert(mesh.packageSha256 === profile.packageSha256, 'mesh package digest mismatch');
  assert(mesh.runtimePackage === null || typeof mesh.runtimePackage === 'object',
    'runtime mesh package must be null or an object');
}

async function sha256File(filePath) {
  const content = await fs.readFile(filePath);
  return crypto.createHash('sha256').update(content).digest('hex');
}

async function validateReferencedV2Files(config, configPath) {
  if (config.schema !== 'onga-stage16-physical-readiness-v2') return;
  const profile = readinessProfile(config);
  const configDirectory = path.dirname(path.resolve(configPath));
  for (const [pathKey, digestKey, label] of [
    ['waterManifest', 'waterManifestSha256', 'water manifest'],
    ['constraints', 'constraintsSha256', 'mesh constraints'],
  ]) {
    const sourcePath = path.resolve(configDirectory, config.mesh[pathKey]);
    const digest = await sha256File(sourcePath);
    assert(digest === config.mesh[digestKey], `${label} source digest mismatch`);
  }
  const manifestPath = path.resolve(configDirectory, config.mesh.waterManifest);
  const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
  const expectedManifestChunks = profile.waterRowChunks
    .map(resource => `./data/${path.basename(resource.path)}`);
  assert(manifest.version === profile.waterAuthorityVersion,
    'water manifest source version mismatch');
  assert(Number(manifest.pixelCount) === profile.approvedWaterPixelCount,
    'water manifest source pixel count mismatch');
  assert(Array.isArray(manifest.chunks)
    && manifest.chunks.length === expectedManifestChunks.length
    && manifest.chunks.every((value, index) => value === expectedManifestChunks[index]),
  'water manifest row-chunk references mismatch');
  for (const [index, resource] of config.mesh.waterRowChunks.entries()) {
    const sourcePath = path.resolve(configDirectory, resource.path);
    const digest = await sha256File(sourcePath);
    assert(digest === resource.sha256, `water row chunk ${index} source digest mismatch`);
  }
  if (config.mesh.runtimePackage !== null) {
    const resource = config.mesh.runtimePackage;
    assert(runtimeMeshPackageReady(config.mesh, readinessProfile(config)),
      'runtime mesh package approval or digest mismatch');
    const sourcePath = path.resolve(configDirectory, resource.path);
    const digest = await sha256File(sourcePath);
    assert(digest === resource.sha256, 'runtime mesh package source digest mismatch');
  }
}

function finiteOrNull(value, label) {
  if (value === null || value === undefined) return null;
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) throw new TypeError(`${label} must be finite or null`);
  return numeric;
}

function nonempty(value) {
  return typeof value === 'string' && value.trim().length > 0;
}

function blocker(code, path, message, options = null) {
  return Object.freeze({ code, path, message, options });
}

function dataSourceReady(source) {
  return source && typeof source === 'object'
    && nonempty(source.id)
    && nonempty(source.provenance)
    && source.approved === true;
}

function resourceReady(resource, expectedCellCount = null) {
  if (!resource || typeof resource !== 'object' || !nonempty(resource.path)) return false;
  if (expectedCellCount !== null && Number(resource.cellCount) !== Number(expectedCellCount)) return false;
  return resource.approved === true;
}

function validateBoundaryModes(boundaries) {
  const allowed = {
    M: new Set(['water_level_time_series', 'normal_discharge', 'radiation', 'coupled_external_series']),
    N: new Set(['normal_discharge', 'water_level', 'time_series_discharge', 'estimated_discharge']),
    O: new Set(['normal_discharge', 'water_level', 'time_series_discharge', 'estimated_discharge']),
    G: new Set(['normal_discharge', 'water_level', 'time_series_discharge', 'estimated_discharge']),
  };
  for (const id of ['M', 'N', 'O', 'G']) {
    assert(boundaries?.[id], `boundary ${id} is missing`);
    assert(allowed[id].has(boundaries[id].selectedMode), `boundary ${id} mode is unsupported`);
  }
}

export function validatePhysicalReadinessConfiguration(config) {
  assert(config && typeof config === 'object', 'configuration must be an object');
  const profile = readinessProfile(config);
  validateMeshIdentity(config.mesh, profile);
  assert(config.governingEquation?.selected === 'depth_averaged_shallow_water',
    'selected governing equation mismatch');
  assert(config.governingEquation?.selectionApproved === true,
    'governing-equation selection must remain approved');
  assert(config.bathymetry?.units === 'm', 'bathymetry units must be m');
  assert(config.roughness?.parameter === 'Manning_n', 'roughness parameter must be Manning_n');
  assert(config.roughness?.units === 's/m^(1/3)', 'roughness units mismatch');
  validateBoundaryModes(config.boundaries);
  assert(new Set(['fixed_discharge', 'time_series_discharge', 'head_difference_relation', 'disabled'])
    .has(config.fishway?.selectedMode), 'fishway mode is unsupported');
  assert(new Set(['uniform_opening', 'eight_gate_individual_opening', 'measured_gate_time_series', 'fully_closed'])
    .has(config.barrage?.selectedMode), 'barrage mode is unsupported');
  assert(config.safeguards?.approvedWaterGeometryChanged === false,
    'approved water geometry must remain unchanged');
  assert(config.safeguards?.legacyFlowCalculationChanged === false,
    'legacy flow calculation must remain unchanged');
  assert(config.safeguards?.publicSimulatorConnected === false,
    'unapproved readiness configuration must not connect to the public simulator');
  return true;
}

export function physicalReadinessReport(config) {
  validatePhysicalReadinessConfiguration(config);
  const profile = readinessProfile(config);
  const blockers = [];
  const cellCount = Number(config.mesh.cellCount);

  if (profile.version === 'stage16-physical-readiness-v1') blockers.push(blocker(
    'HISTORICAL_READINESS_SCHEMA_NOT_EXECUTABLE',
    'schema',
    'Historical v1 readiness data may be audited but can never authorize physical execution.',
  ));

  const runtimeMeshPackageVerified = profile.version === 'stage16-physical-readiness-v2'
    && VERIFIED_CONFIGURATIONS.has(config)
    && runtimeMeshPackageReady(config.mesh, profile);
  if (profile.version === 'stage16-physical-readiness-v2'
    && !runtimeMeshPackageVerified) blockers.push(blocker(
    'MESH_RUNTIME_PACKAGE_UNVERIFIED',
    'mesh.runtimePackage',
    'The exact canonical v2 mesh package must be present, hash-verified, and approved before physical execution.',
  ));

  const bathymetryModes = new Set(['per_cell', 'surveyed_bathymetry', 'authoritative_cross_sections', 'hydrographic_raster']);
  if (!bathymetryModes.has(config.bathymetry.mode)) {
    blockers.push(blocker(
      'BATHYMETRY_MODE_UNASSIGNED',
      'bathymetry.mode',
      'A physical bathymetry source and mapping mode must be selected.',
      config.deferredOptions?.bathymetry ?? null,
    ));
  }
  if (!dataSourceReady(config.bathymetry.dataSource)) {
    blockers.push(blocker(
      'BATHYMETRY_SOURCE_UNAPPROVED',
      'bathymetry.dataSource',
      'Bathymetry provenance and approval are required.',
    ));
  }
  if (!nonempty(config.bathymetry.verticalDatum)) {
    blockers.push(blocker(
      'BATHYMETRY_DATUM_UNASSIGNED',
      'bathymetry.verticalDatum',
      'Bathymetry vertical datum must be declared before water levels can be combined with bed elevation.',
    ));
  }
  if (config.bathymetry.mode === 'per_cell'
    && !resourceReady(config.bathymetry.cellFieldResource, cellCount)) {
    blockers.push(blocker(
      'BATHYMETRY_CELL_FIELD_MISSING',
      'bathymetry.cellFieldResource',
      `An approved ${cellCount}-cell bathymetry field is required for per-cell mode.`,
    ));
  }

  const roughnessModes = new Set(['constant', 'per_cell', 'zones']);
  if (!roughnessModes.has(config.roughness.mode)) {
    blockers.push(blocker(
      'ROUGHNESS_MODE_UNASSIGNED',
      'roughness.mode',
      'A Manning roughness representation must be selected.',
      config.deferredOptions?.roughness ?? null,
    ));
  }
  if (!dataSourceReady(config.roughness.dataSource)) {
    blockers.push(blocker(
      'ROUGHNESS_SOURCE_UNAPPROVED',
      'roughness.dataSource',
      'Roughness provenance and approval are required.',
    ));
  }
  if (config.roughness.mode === 'constant') {
    const value = finiteOrNull(config.roughness.constantValue, 'roughness.constantValue');
    if (!(value > 0)) blockers.push(blocker(
      'ROUGHNESS_CONSTANT_MISSING',
      'roughness.constantValue',
      'A positive Manning n is required for constant roughness mode.',
    ));
  }
  if (config.roughness.mode === 'per_cell'
    && !resourceReady(config.roughness.cellFieldResource, cellCount)) {
    blockers.push(blocker(
      'ROUGHNESS_CELL_FIELD_MISSING',
      'roughness.cellFieldResource',
      `An approved ${cellCount}-cell roughness field is required for per-cell mode.`,
    ));
  }
  if (config.roughness.mode === 'zones' && !resourceReady(config.roughness.zoneResource)) {
    blockers.push(blocker(
      'ROUGHNESS_ZONE_RESOURCE_MISSING',
      'roughness.zoneResource',
      'An approved roughness-zone resource is required for zonal mode.',
    ));
  }

  if (config.initialState?.mode === 'unassigned') blockers.push(blocker(
    'INITIAL_STATE_UNASSIGNED',
    'initialState.mode',
    'Initial water surface and velocity state must be selected.',
  ));
  if (!nonempty(config.initialState?.waterSurfaceDatum)) blockers.push(blocker(
    'INITIAL_DATUM_UNASSIGNED',
    'initialState.waterSurfaceDatum',
    'Initial water-surface datum must be declared.',
  ));
  if (nonempty(config.initialState?.waterSurfaceDatum)
    && nonempty(config.bathymetry.verticalDatum)
    && config.initialState.waterSurfaceDatum !== config.bathymetry.verticalDatum) {
    blockers.push(blocker(
      'VERTICAL_DATUM_MISMATCH',
      'initialState.waterSurfaceDatum',
      'Initial water surface and bathymetry use different vertical datums.',
    ));
  }

  for (const id of ['M', 'N', 'O', 'G']) {
    const boundary = config.boundaries[id];
    if (!dataSourceReady(boundary.dataSource)) blockers.push(blocker(
      `BOUNDARY_${id}_SOURCE_UNAPPROVED`,
      `boundaries.${id}.dataSource`,
      `Boundary ${id} requires an approved data source.`,
      id === 'M' ? config.deferredOptions?.MBoundary ?? null : config.deferredOptions?.NOGBoundaries ?? null,
    ));
    if (!resourceReady(boundary.resource)) blockers.push(blocker(
      `BOUNDARY_${id}_RESOURCE_MISSING`,
      `boundaries.${id}.resource`,
      `Boundary ${id} requires an approved value or time-series resource.`,
    ));
  }
  if (config.boundaries.M.selectedMode === 'water_level_time_series') {
    if (!nonempty(config.boundaries.M.verticalDatum)) blockers.push(blocker(
      'BOUNDARY_M_DATUM_UNASSIGNED',
      'boundaries.M.verticalDatum',
      'M water-level series requires a declared vertical datum.',
    ));
    if (nonempty(config.boundaries.M.verticalDatum)
      && nonempty(config.bathymetry.verticalDatum)
      && config.boundaries.M.verticalDatum !== config.bathymetry.verticalDatum) {
      blockers.push(blocker(
        'BOUNDARY_M_DATUM_MISMATCH',
        'boundaries.M.verticalDatum',
        'M water level and bathymetry use different vertical datums.',
      ));
    }
  }

  if (config.fishway.selectedMode !== 'disabled') {
    if (!dataSourceReady(config.fishway.dataSource)) blockers.push(blocker(
      'FISHWAY_SOURCE_UNAPPROVED',
      'fishway.dataSource',
      'Fishway operation or hydraulic parameters require approved provenance.',
      config.deferredOptions?.fishway ?? null,
    ));
    if (config.fishway.selectedMode === 'fixed_discharge') {
      const discharge = finiteOrNull(config.fishway.dischargeM3S, 'fishway.dischargeM3S');
      if (!(discharge >= 0)) blockers.push(blocker(
        'FISHWAY_FIXED_DISCHARGE_MISSING',
        'fishway.dischargeM3S',
        'A nonnegative fishway discharge is required for fixed-discharge mode.',
      ));
    } else if (!resourceReady(config.fishway.resource)) {
      blockers.push(blocker(
        'FISHWAY_RESOURCE_MISSING',
        'fishway.resource',
        'The selected fishway mode requires an approved resource.',
      ));
    }
  }

  if (!dataSourceReady(config.barrage.operationDataSource)) blockers.push(blocker(
    'BARRAGE_OPERATION_SOURCE_UNAPPROVED',
    'barrage.operationDataSource',
    'Barrage operation requires approved provenance.',
    config.deferredOptions?.barrage ?? null,
  ));
  if (config.barrage.selectedMode === 'uniform_opening') {
    const opening = finiteOrNull(config.barrage.openingFraction, 'barrage.openingFraction');
    if (!(opening >= 0 && opening <= 1)) blockers.push(blocker(
      'BARRAGE_UNIFORM_OPENING_MISSING',
      'barrage.openingFraction',
      'Uniform opening fraction must be in [0, 1].',
    ));
  }
  if (new Set(['eight_gate_individual_opening', 'measured_gate_time_series'])
    .has(config.barrage.selectedMode) && !resourceReady(config.barrage.gatewiseResource)) {
    blockers.push(blocker(
      'BARRAGE_GATEWISE_RESOURCE_MISSING',
      'barrage.gatewiseResource',
      'The selected barrage mode requires an approved eight-gate resource.',
    ));
  }
  if (config.barrage.selectedMode !== 'fully_closed') {
    const coefficient = finiteOrNull(config.barrage.dischargeCoefficient, 'barrage.dischargeCoefficient');
    if (!(coefficient > 0)) blockers.push(blocker(
      'BARRAGE_COEFFICIENT_MISSING',
      'barrage.dischargeCoefficient',
      'A positive discharge coefficient is required for an open barrage model.',
    ));
    if (!dataSourceReady(config.barrage.effectiveGeometrySource)) blockers.push(blocker(
      'BARRAGE_GEOMETRY_SOURCE_UNAPPROVED',
      'barrage.effectiveGeometrySource',
      'Effective gate geometry requires approved provenance.',
    ));
  }

  if (config.approval?.status !== 'approved'
    || !nonempty(config.approval.approvedBy)
    || !nonempty(config.approval.approvedAt)
    || !nonempty(config.approval.scope)) {
    blockers.push(blocker(
      'PHYSICAL_CONFIGURATION_NOT_APPROVED',
      'approval',
      'Explicit approval of data sources，modes，values，and scope is required.',
    ));
  }
  if (config.simulation?.physicalRunEnabled !== true) blockers.push(blocker(
    'PHYSICAL_RUN_DISABLED',
    'simulation.physicalRunEnabled',
    'Physical execution remains disabled until all inputs and approval are complete.',
  ));

  const ready = blockers.length === 0;
  return Object.freeze({
    version: profile.version,
    ready,
    blockerCount: blockers.length,
    blockers: Object.freeze(blockers),
    summary: Object.freeze({
      bathymetryAssigned: bathymetryModes.has(config.bathymetry.mode),
      roughnessAssigned: roughnessModes.has(config.roughness.mode),
      boundarySourcesAssigned: ['M', 'N', 'O', 'G'].every(id => dataSourceReady(config.boundaries[id].dataSource)),
      fishwayAssigned: config.fishway.selectedMode === 'disabled' || dataSourceReady(config.fishway.dataSource),
      barrageAssigned: dataSourceReady(config.barrage.operationDataSource),
      runtimeMeshPackageVerified,
      explicitlyApproved: config.approval?.status === 'approved',
      physicalRunEnabled: config.simulation?.physicalRunEnabled === true,
    }),
  });
}

export function assertPhysicalSimulationReady(config) {
  assert(config?.schema === 'onga-stage16-physical-readiness-v2',
    'physical execution requires the current v2 readiness schema');
  assert(VERIFIED_CONFIGURATIONS.has(config),
    'physical execution requires a deeply frozen configuration loaded with verified referenced files');
  const report = physicalReadinessReport(config);
  if (!report.ready) {
    const codes = report.blockers.map(item => item.code).join(', ');
    throw new Error(`[stage16-readiness] physical simulation is not ready: ${codes}`);
  }
  return report;
}

export async function loadPhysicalReadinessConfiguration(
  configPath = 'config/onga_stage16_physical_readiness_v2.json',
) {
  const config = JSON.parse(await fs.readFile(configPath, 'utf8'));
  validatePhysicalReadinessConfiguration(config);
  await validateReferencedV2Files(config, configPath);
  const frozen = deepFreeze(config);
  VERIFIED_CONFIGURATIONS.add(frozen);
  return frozen;
}
