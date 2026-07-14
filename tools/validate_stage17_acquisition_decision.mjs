import crypto from 'node:crypto';
import fs from 'node:fs/promises';

const recordPath = process.argv[2]
  || 'config/stage17_physical_data_acquisition_decision_record_v3.json';
const outputPath = process.argv[3] || 'stage17-acquisition-decision-validation.json';
const record = JSON.parse(await fs.readFile(recordPath, 'utf8'));
const previousText = await fs.readFile(
  'config/stage17_physical_data_acquisition_decision_record_v2.json',
  'utf8',
);

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

const previousSha256 = crypto.createHash('sha256').update(previousText).digest('hex');
const checks = [
  check('schema', record.schema, 'onga-stage17-physical-data-acquisition-decision-record-v3',
    record.schema === 'onga-stage17-physical-data-acquisition-decision-record-v3'),
  check('v2 route decision digest retained', record.supersedes?.sha256,
    'd4aab0086540f4bfc7cb0696753dc5efec59e0e0bad7d2214fce9afc6574fe28',
    record.supersedes?.path === 'config/stage17_physical_data_acquisition_decision_record_v2.json'
      && record.supersedes?.sha256 === previousSha256
      && previousSha256 === 'd4aab0086540f4bfc7cb0696753dc5efec59e0e0bad7d2214fce9afc6574fe28'),
  check('public-data and declared-inference route selected', record.optionId,
    'public_database_and_declared_inference_only',
    record.optionId === 'public_database_and_declared_inference_only'),
  check('approver recorded', record.approvedBy, 'nonempty',
    typeof record.approvedBy === 'string' && record.approvedBy.trim().length > 0),
  check('approval date valid', record.approvedAt, 'ISO-8601',
    Number.isFinite(Date.parse(record.approvedAt))),
  check('explicit requester statement', record.sourceStatement,
    '遠賀川河川事務所への資料照会はしません．公開データや推論に基づいてシミュレータを開発します．次に進める作業を教えてください．',
    record.sourceStatement
      === '遠賀川河川事務所への資料照会はしません．公開データや推論に基づいてシミュレータを開発します．次に進める作業を教えてください．'),
  check('official request disabled', record.scope?.officialRequestPreparationAndSubmission, false,
    record.scope?.officialRequestPreparationAndSubmission === false),
  check('public database acquisition allowed', record.scope?.publicOfficialDatabaseAcquisition, true,
    record.scope?.publicOfficialDatabaseAcquisition === true),
  check('declared inference preparation allowed', record.scope?.declaredInferenceScenarioPreparation, true,
    record.scope?.declaredInferenceScenarioPreparation === true),
  check('visual decision packet allowed', record.scope?.visualDecisionPacketPreparation, true,
    record.scope?.visualDecisionPacketPreparation === true),
  check('automatic solver assignment prohibited', record.scope?.automaticSolverAssignment, false,
    record.scope?.automaticSolverAssignment === false),
  check('numerical run disabled', record.scope?.numericalScenarioRunEnablement, false,
    record.scope?.numericalScenarioRunEnablement === false),
  check('physical Validation claim disabled', record.scope?.physicalValidationClaim, false,
    record.scope?.physicalValidationClaim === false),
  check('public simulator disconnected', record.scope?.publicSimulatorConnection, false,
    record.scope?.publicSimulatorConnection === false),
  check('corrected water identity retained', record.geometryBinding?.approvedWaterPixelCount, 680633,
    record.geometryBinding?.waterAuthorityVersion === 'v4.8.0-candidate-r3'
      && record.geometryBinding?.approvedWaterPixelCount === 680633
      && record.geometryBinding?.waterManifestSha256
        === '964eaa8d43607d0ac4cc6d81f37fa8a9ed8dc23563894ddce85b4252938fcbf7'),
  check('corrected mesh identity retained', record.geometryBinding?.metricMeshCellCount, 50129,
    record.geometryBinding?.metricMeshVersion === 'stage16-metric-fv-mesh-v2'
      && record.geometryBinding?.metricMeshCellCount === 50129
      && record.geometryBinding?.metricMeshPackageSha256
        === 'f18ac352604e286be395f7ced1580f654c00b29cf65f310fcbce38fb00219fe2'),
  check('all contact routes excluded', record.notApproved.some(item => item.includes('contacting the Onga River Office')), true,
    record.notApproved.some(item => item.includes('contacting the Onga River Office'))),
  check('new run still requires visual and scope approval',
    record.notApproved.some(item => item.includes('visual input packet')), true,
    record.notApproved.some(item => item.includes('visual input packet'))),
];

const report = {
  schema: 'onga-stage17-acquisition-decision-validation-v2',
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  optionId: record.optionId,
  safeguards: {
    officialRequestEnabled: false,
    physicalValuesAssigned: false,
    numericalRunEnabled: false,
    publicSimulatorConnected: false,
    approvedWaterGeometryChanged: false,
    externalContactCompletedByThisValidator: false,
  },
  checks,
};

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
