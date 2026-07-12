import fs from 'node:fs/promises';

export const STAGE16_PHYSICAL_READINESS_VERSION = 'stage16-physical-readiness-v1';

function assert(condition, message) {
  if (!condition) throw new Error(`[stage16-readiness] ${message}`);
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
  assert(config.schema === 'onga-stage16-physical-readiness-v1', 'schema mismatch');
  assert(Number(config.mesh?.cellCount) === 50333, 'mesh cell count mismatch');
  assert(Number(config.mesh?.approvedWaterPixelCount) === 679791, 'approved water pixel count mismatch');
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
  const blockers = [];
  const cellCount = Number(config.mesh.cellCount);

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
    version: STAGE16_PHYSICAL_READINESS_VERSION,
    ready,
    blockerCount: blockers.length,
    blockers: Object.freeze(blockers),
    summary: Object.freeze({
      bathymetryAssigned: bathymetryModes.has(config.bathymetry.mode),
      roughnessAssigned: roughnessModes.has(config.roughness.mode),
      boundarySourcesAssigned: ['M', 'N', 'O', 'G'].every(id => dataSourceReady(config.boundaries[id].dataSource)),
      fishwayAssigned: config.fishway.selectedMode === 'disabled' || dataSourceReady(config.fishway.dataSource),
      barrageAssigned: dataSourceReady(config.barrage.operationDataSource),
      explicitlyApproved: config.approval?.status === 'approved',
      physicalRunEnabled: config.simulation?.physicalRunEnabled === true,
    }),
  });
}

export function assertPhysicalSimulationReady(config) {
  const report = physicalReadinessReport(config);
  if (!report.ready) {
    const codes = report.blockers.map(item => item.code).join(', ');
    throw new Error(`[stage16-readiness] physical simulation is not ready: ${codes}`);
  }
  return report;
}

export async function loadPhysicalReadinessConfiguration(
  path = 'config/onga_stage16_physical_readiness_v1.json',
) {
  const config = JSON.parse(await fs.readFile(path, 'utf8'));
  validatePhysicalReadinessConfiguration(config);
  return Object.freeze(config);
}
