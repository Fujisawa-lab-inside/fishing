import fs from 'node:fs/promises';
import {
  assertPhysicalSimulationReady,
  loadPhysicalReadinessConfiguration,
  physicalReadinessReport,
  validatePhysicalReadinessConfiguration,
} from '../onga_stage16_physical_readiness.mjs';

const configPath = process.argv[2] || 'config/onga_stage16_physical_readiness_v1.json';
const outputPath = process.argv[3] || 'stage16-physical-readiness-validation.json';

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function approvedSource(id) {
  return { id, provenance: `verification fixture ${id}`, approved: true };
}

function approvedResource(path, cellCount = null) {
  return { path, approved: true, ...(cellCount === null ? {} : { cellCount }) };
}

function expectThrow(fn) {
  try {
    fn();
    return false;
  } catch (_) {
    return true;
  }
}

const template = await loadPhysicalReadinessConfiguration(configPath);
const templateReport = physicalReadinessReport(template);
const templateCodes = new Set(templateReport.blockers.map(item => item.code));
const mandatoryTemplateCodes = [
  'BATHYMETRY_MODE_UNASSIGNED',
  'BATHYMETRY_SOURCE_UNAPPROVED',
  'BATHYMETRY_DATUM_UNASSIGNED',
  'ROUGHNESS_MODE_UNASSIGNED',
  'INITIAL_STATE_UNASSIGNED',
  'BOUNDARY_M_SOURCE_UNAPPROVED',
  'BOUNDARY_N_SOURCE_UNAPPROVED',
  'BOUNDARY_O_SOURCE_UNAPPROVED',
  'BOUNDARY_G_SOURCE_UNAPPROVED',
  'FISHWAY_SOURCE_UNAPPROVED',
  'BARRAGE_OPERATION_SOURCE_UNAPPROVED',
  'PHYSICAL_CONFIGURATION_NOT_APPROVED',
  'PHYSICAL_RUN_DISABLED',
];

const fixture = clone(template);
fixture.status = 'verification_fixture_complete';
fixture.bathymetry = {
  ...fixture.bathymetry,
  mode: 'per_cell',
  dataSource: approvedSource('bathymetry-fixture'),
  verticalDatum: 'fixture-datum',
  uncertaintyM: 0.1,
  cellFieldResource: approvedResource('fixture://bathymetry', 50333),
};
fixture.roughness = {
  ...fixture.roughness,
  mode: 'constant',
  dataSource: approvedSource('roughness-fixture'),
  constantValue: 0.03,
};
fixture.initialState = {
  ...fixture.initialState,
  mode: 'constant_water_surface',
  waterSurfaceDatum: 'fixture-datum',
  waterSurfaceM: 2,
  velocityMode: 'zero',
};
for (const id of ['M', 'N', 'O', 'G']) {
  fixture.boundaries[id].dataSource = approvedSource(`boundary-${id}-fixture`);
  fixture.boundaries[id].resource = approvedResource(`fixture://boundary-${id}`);
}
fixture.boundaries.M.verticalDatum = 'fixture-datum';
fixture.fishway = {
  ...fixture.fishway,
  dataSource: approvedSource('fishway-fixture'),
  dischargeM3S: 0.1,
};
fixture.barrage = {
  ...fixture.barrage,
  operationDataSource: approvedSource('barrage-operation-fixture'),
  openingFraction: 0.4,
  dischargeCoefficient: 0.7,
  effectiveGeometrySource: approvedSource('barrage-geometry-fixture'),
};
fixture.approval = {
  status: 'approved',
  approvedBy: 'verification-fixture',
  approvedAt: '2000-01-01T00:00:00Z',
  scope: 'syntactic readiness verification only',
};
fixture.simulation.physicalRunEnabled = true;
fixture.safeguards.physicalValuesAssigned = true;
const fixtureReport = physicalReadinessReport(fixture);
const fixtureAsserted = assertPhysicalSimulationReady(fixture).ready;

const datumMismatch = clone(fixture);
datumMismatch.boundaries.M.verticalDatum = 'different-fixture-datum';
const datumMismatchReport = physicalReadinessReport(datumMismatch);
const datumMismatchDetected = datumMismatchReport.blockers
  .some(item => item.code === 'BOUNDARY_M_DATUM_MISMATCH');

const disabledRun = clone(fixture);
disabledRun.simulation.physicalRunEnabled = false;
const disabledRunReport = physicalReadinessReport(disabledRun);
const disabledRunDetected = disabledRunReport.blockers.some(item => item.code === 'PHYSICAL_RUN_DISABLED');

const missingApproval = clone(fixture);
missingApproval.approval.status = 'not_requested';
const missingApprovalReport = physicalReadinessReport(missingApproval);
const missingApprovalDetected = missingApprovalReport.blockers
  .some(item => item.code === 'PHYSICAL_CONFIGURATION_NOT_APPROVED');

const badGeometry = clone(template);
badGeometry.safeguards.approvedWaterGeometryChanged = true;
const geometryChangeRejected = expectThrow(() => validatePhysicalReadinessConfiguration(badGeometry));

const badOpening = clone(fixture);
badOpening.barrage.openingFraction = 1.1;
const badOpeningReport = physicalReadinessReport(badOpening);
const badOpeningDetected = badOpeningReport.blockers.some(item => item.code === 'BARRAGE_UNIFORM_OPENING_MISSING');

const unapprovedResource = clone(fixture);
unapprovedResource.bathymetry.cellFieldResource.approved = false;
const unapprovedResourceReport = physicalReadinessReport(unapprovedResource);
const unapprovedResourceDetected = unapprovedResourceReport.blockers
  .some(item => item.code === 'BATHYMETRY_CELL_FIELD_MISSING');

const templateAssertRejected = expectThrow(() => assertPhysicalSimulationReady(template));
const checks = [
  check('template configuration valid', true, true, validatePhysicalReadinessConfiguration(template)),
  check('template physical simulation blocked', templateReport.ready, false, !templateReport.ready),
  check('template blocker count', templateReport.blockerCount, '>0', templateReport.blockerCount > 0),
  check('mandatory decisions reported', mandatoryTemplateCodes.every(code => templateCodes.has(code)), true,
    mandatoryTemplateCodes.every(code => templateCodes.has(code))),
  check('template assert-ready rejects', templateAssertRejected, true, templateAssertRejected),
  check('complete in-memory fixture ready', fixtureReport.ready, true, fixtureReport.ready),
  check('complete fixture blocker count', fixtureReport.blockerCount, 0, fixtureReport.blockerCount === 0),
  check('assert-ready accepts complete fixture', fixtureAsserted, true, fixtureAsserted),
  check('vertical datum mismatch detected', datumMismatchDetected, true, datumMismatchDetected),
  check('physical-run disable detected', disabledRunDetected, true, disabledRunDetected),
  check('missing explicit approval detected', missingApprovalDetected, true, missingApprovalDetected),
  check('approved geometry mutation rejected', geometryChangeRejected, true, geometryChangeRejected),
  check('out-of-range barrage opening detected', badOpeningDetected, true, badOpeningDetected),
  check('unapproved cell field detected', unapprovedResourceDetected, true, unapprovedResourceDetected),
  check('template public simulator disconnected', template.safeguards.publicSimulatorConnected, false,
    template.safeguards.publicSimulatorConnected === false),
  check('template physical run disabled', template.simulation.physicalRunEnabled, false,
    template.simulation.physicalRunEnabled === false),
];

const report = {
  schema: 'onga-stage16-physical-readiness-validation-v1',
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  template: {
    ready: templateReport.ready,
    blockerCount: templateReport.blockerCount,
    blockerCodes: templateReport.blockers.map(item => item.code),
  },
  verificationFixture: {
    ready: fixtureReport.ready,
    blockerCount: fixtureReport.blockerCount,
    committed: false,
    purpose: 'validator-only fixture，not a physical model input',
  },
  safeguards: template.safeguards,
  checks,
};

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
