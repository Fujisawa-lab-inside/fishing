import fs from 'node:fs/promises';

const recordPath = process.argv[2] || 'config/stage17_physical_data_acquisition_decision_record_v2.json';
const outputPath = process.argv[3] || 'stage17-acquisition-decision-validation.json';
const record = JSON.parse(await fs.readFile(recordPath, 'utf8'));

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

const checks = [
  check('schema', record.schema, 'onga-stage17-physical-data-acquisition-decision-record-v2',
    record.schema === 'onga-stage17-physical-data-acquisition-decision-record-v2'),
  check('v1 route decision digest retained', record.supersedes?.sha256,
    '5e66568e5dbc1cda32af371f66b9521a5c5d21679e2ddea523383c2a24b68be5',
    record.supersedes?.sha256 === '5e66568e5dbc1cda32af371f66b9521a5c5d21679e2ddea523383c2a24b68be5'),
  check('route A selected', record.optionId, 'parallel_official_request_and_public_database_acquisition',
    record.optionId === 'parallel_official_request_and_public_database_acquisition'),
  check('approver recorded', record.approvedBy, 'nonempty', typeof record.approvedBy === 'string' && record.approvedBy.trim().length > 0),
  check('approval time valid', record.approvedAt, 'ISO-8601', Number.isFinite(Date.parse(record.approvedAt))),
  check('explicit source statement', record.sourceStatement, 'A案で作業を進めてください',
    record.sourceStatement === 'A案で作業を進めてください'),
  check('official request allowed', record.scope?.officialRequestPreparationAndSubmission, true,
    record.scope?.officialRequestPreparationAndSubmission === true),
  check('public database acquisition allowed', record.scope?.publicOfficialDatabaseAcquisition, true,
    record.scope?.publicOfficialDatabaseAcquisition === true),
  check('solver assignment prohibited', record.scope?.automaticSolverAssignment, false,
    record.scope?.automaticSolverAssignment === false),
  check('physical run disabled', record.scope?.physicalRunEnablement, false,
    record.scope?.physicalRunEnablement === false),
  check('public simulator disconnected', record.scope?.publicSimulatorConnection, false,
    record.scope?.publicSimulatorConnection === false),
  check('corrected water identity rebound', record.geometryBinding?.approvedWaterPixelCount, 680633,
    record.geometryBinding?.waterAuthorityVersion === 'v4.8.0-candidate-r3'
      && record.geometryBinding?.approvedWaterPixelCount === 680633
      && record.geometryBinding?.waterManifestSha256
        === '964eaa8d43607d0ac4cc6d81f37fa8a9ed8dc23563894ddce85b4252938fcbf7'),
  check('corrected mesh identity rebound', record.geometryBinding?.metricMeshCellCount, 50129,
    record.geometryBinding?.metricMeshVersion === 'stage16-metric-fv-mesh-v2'
      && record.geometryBinding?.metricMeshCellCount === 50129
      && record.geometryBinding?.metricMeshPackageSha256
        === 'f18ac352604e286be395f7ced1580f654c00b29cf65f310fcbce38fb00219fe2'),
  check('geometry changes excluded', record.notApproved.some(item => item.includes('680633-pixel')), true,
    record.notApproved.some(item => item.includes('680633-pixel'))),
  check('boundary auto-assignment excluded', record.notApproved.some(item => item.includes('M, N, O, or G')), true,
    record.notApproved.some(item => item.includes('M, N, O, or G'))),
];

const report = {
  schema: 'onga-stage17-acquisition-decision-validation-v1',
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  optionId: record.optionId,
  safeguards: {
    physicalValuesAssigned: false,
    physicalRunEnabled: false,
    publicSimulatorConnected: false,
    approvedWaterGeometryChanged: false,
    externalContactCompletedByThisValidator: false
  },
  checks
};

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
