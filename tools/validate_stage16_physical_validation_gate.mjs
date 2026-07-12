import fs from 'node:fs/promises';
import {
  assertStage16PhysicalValidationReady,
  governingEquationSelectionReport,
  loadStage16PhysicalValidationGateInputs,
  stage16PhysicalValidationGateReport,
} from '../onga_stage16_physical_validation_gate.mjs';

const outputPath = process.argv[2] || 'stage16-physical-validation-gate-validation.json';

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
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

const inputs = await loadStage16PhysicalValidationGateInputs();
const current = stage16PhysicalValidationGateReport(inputs);
const currentCodes = new Set(current.blockers.map(item => item.code));

const missingRecord = governingEquationSelectionReport({
  decisionInput: inputs.decisionInput,
  decisionRecord: null,
  readinessConfig: inputs.readinessConfig,
});
const tamperedRecord = clone(inputs.decisionRecord);
tamperedRecord.governingEquation = 'scalar_conservative_skeleton';
const tamperedRecordReport = governingEquationSelectionReport({
  decisionInput: inputs.decisionInput,
  decisionRecord: tamperedRecord,
  readinessConfig: inputs.readinessConfig,
});
const tamperedReadiness = clone(inputs.readinessConfig);
tamperedReadiness.governingEquation.selected = 'scalar_conservative_skeleton';
const tamperedReadinessReport = governingEquationSelectionReport({
  decisionInput: inputs.decisionInput,
  decisionRecord: inputs.decisionRecord,
  readinessConfig: tamperedReadiness,
});
const provenanceMismatch = clone(inputs.readinessConfig);
provenanceMismatch.governingEquation.approvedBy = 'different-approver';
const provenanceMismatchReport = governingEquationSelectionReport({
  decisionInput: inputs.decisionInput,
  decisionRecord: inputs.decisionRecord,
  readinessConfig: provenanceMismatch,
});

const fixture = clone(inputs.readinessConfig);
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
const complete = stage16PhysicalValidationGateReport({
  ...inputs,
  readinessConfig: fixture,
});

const currentAssertRejected = expectThrow(() => assertStage16PhysicalValidationReady(inputs));
const completeAssertAccepted = assertStage16PhysicalValidationReady({
  ...inputs,
  readinessConfig: fixture,
}).ready;

const checks = [
  check('committed equation selection is ready', current.equationSelection.ready, true,
    current.equationSelection.ready),
  check('selected equation is shallow water', current.equationSelection.selectedEquation,
    'depth_averaged_shallow_water',
    current.equationSelection.selectedEquation === 'depth_averaged_shallow_water'),
  check('recorded option is A', current.equationSelection.decisionOption,
    'adopt_depth_averaged_shallow_water_for_validation',
    current.equationSelection.decisionOption === 'adopt_depth_averaged_shallow_water_for_validation'),
  check('committed physical inputs remain blocked', current.physicalInputs.ready, false,
    !current.physicalInputs.ready),
  check('combined gate remains blocked', current.ready, false, !current.ready),
  check('bathymetry blocker retained', currentCodes.has('BATHYMETRY_MODE_UNASSIGNED'), true,
    currentCodes.has('BATHYMETRY_MODE_UNASSIGNED')),
  check('physical-run blocker retained', currentCodes.has('PHYSICAL_RUN_DISABLED'), true,
    currentCodes.has('PHYSICAL_RUN_DISABLED')),
  check('current assert-ready rejects', currentAssertRejected, true, currentAssertRejected),
  check('missing record rejected', missingRecord.ready, false,
    !missingRecord.ready && missingRecord.blockers.some(item => item.code === 'GOVERNING_EQUATION_DECISION_INVALID')),
  check('tampered equation record rejected', tamperedRecordReport.ready, false,
    !tamperedRecordReport.ready
      && tamperedRecordReport.blockers.some(item => item.code === 'GOVERNING_EQUATION_RECORD_MISMATCH')),
  check('readiness equation mismatch rejected', tamperedReadinessReport.ready, false,
    !tamperedReadinessReport.ready
      && tamperedReadinessReport.blockers.some(item => item.code === 'READINESS_GOVERNING_EQUATION_MISMATCH')),
  check('approval provenance mismatch rejected', provenanceMismatchReport.ready, false,
    !provenanceMismatchReport.ready
      && provenanceMismatchReport.blockers.some(item => item.code === 'READINESS_DECISION_PROVENANCE_MISMATCH')),
  check('complete in-memory fixture passes combined gate', complete.ready, true, complete.ready),
  check('complete fixture assert-ready accepts', completeAssertAccepted, true, completeAssertAccepted),
  check('approved water geometry remains frozen', current.safeguards.approvedWaterGeometryChanged, false,
    current.safeguards.approvedWaterGeometryChanged === false),
  check('legacy flow calculation remains frozen', current.safeguards.legacyFlowCalculationChanged, false,
    current.safeguards.legacyFlowCalculationChanged === false),
  check('public simulator remains disconnected', current.safeguards.publicSimulatorConnected, false,
    current.safeguards.publicSimulatorConnected === false),
];

const report = {
  schema: 'onga-stage16-physical-validation-gate-validation-v1',
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  current: {
    ready: current.ready,
    equationSelectionReady: current.equationSelection.ready,
    physicalInputsReady: current.physicalInputs.ready,
    blockerCount: current.blockerCount,
    blockerCodes: current.blockers.map(item => item.code),
  },
  completeVerificationFixture: {
    ready: complete.ready,
    committed: false,
    purpose: 'validator-only fixture，not an approved physical model input',
  },
  checks,
};

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
