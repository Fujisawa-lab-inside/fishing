import fs from 'node:fs/promises';

const recordPath = process.argv[2] || 'config/stage17_physical_data_acquisition_decision_record_v1.json';
const outputPath = process.argv[3] || 'stage17-acquisition-decision-validation.json';
const record = JSON.parse(await fs.readFile(recordPath, 'utf8'));

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

const checks = [
  check('schema', record.schema, 'onga-stage17-physical-data-acquisition-decision-record-v1',
    record.schema === 'onga-stage17-physical-data-acquisition-decision-record-v1'),
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
  check('geometry changes excluded', record.notApproved.some(item => item.includes('679791-pixel')), true,
    record.notApproved.some(item => item.includes('679791-pixel'))),
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
