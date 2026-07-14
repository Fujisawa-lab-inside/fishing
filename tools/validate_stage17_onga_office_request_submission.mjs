import fs from 'node:fs/promises';
import crypto from 'node:crypto';

const requestPath = process.argv[2] || 'config/stage17_onga_office_request_submission_v1.json';
const decisionPath = process.argv[3] || 'config/stage17_physical_data_acquisition_decision_record_v2.json';
const outputPath = process.argv[4] || 'stage17-onga-office-request-submission-validation.json';

function assert(condition, message) {
  if (!condition) throw new Error(`[stage17-request-submission] ${message}`);
}

function nonempty(value) {
  return typeof value === 'string' && value.trim().length > 0;
}

function blocker(code, path, message) {
  return Object.freeze({ code, path, message });
}

function parseDateOrNull(value) {
  if (!nonempty(value)) return null;
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? timestamp : null;
}

function sha256Hex(value) {
  return typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
}

function validateSafeguards(config) {
  const expectedFalse = [
    'approvedWaterGeometryChanged',
    'metricMeshChanged',
    'stationBoundaryAssignmentPerformed',
    'physicalValuesAssigned',
    'physicalRunEnabled',
    'publicSimulatorConnected',
    'visualFittingPerformed',
  ];
  for (const key of expectedFalse) {
    assert(config.safeguards?.[key] === false, `safeguards.${key} must remain false`);
  }
}

function validateRouteDecision(decision) {
  assert(decision?.schema === 'onga-stage17-physical-data-acquisition-decision-record-v2',
    'acquisition decision schema mismatch');
  assert(decision.optionId === 'parallel_official_request_and_public_database_acquisition',
    'route A is not selected');
  assert(decision.scope?.officialRequestPreparationAndSubmission === true,
    'official request preparation and submission are not approved');
  assert(decision.scope?.automaticSolverAssignment === false,
    'automatic solver assignment must remain disallowed');
  assert(decision.scope?.physicalRunEnablement === false,
    'physical run enablement must remain disallowed');
}

export function buildSubmissionReadiness(config, decision, actualMessageSha256) {
  assert(config?.schema === 'onga-stage17-official-request-submission-v1', 'request schema mismatch');
  validateRouteDecision(decision);
  validateSafeguards(config);
  assert(config.acquisitionDecisionRecord === 'config/stage17_physical_data_acquisition_decision_record_v2.json',
    'decision record path mismatch');
  assert(config.recipient?.organization === '国土交通省九州地方整備局 遠賀川河川事務所',
    'recipient organization mismatch');
  assert(config.recipient?.telephone === '0949-22-1830', 'official telephone mismatch');
  assert(config.recipient?.verifiedEmail === 'onga@qsr.mlit.go.jp', 'official email mismatch');
  assert(config.recipient?.officialContactEvidence?.url
    === 'https://www.qsr.mlit.go.jp/onga/access/index.html',
  'official contact evidence URL mismatch');
  assert(config.recipient?.officialContactEvidence?.sha256
    === 'a42fb487de0c39c8215a9fcb70010caf056e09a2f31172035a086736aef0adee',
  'official contact evidence SHA-256 mismatch');
  assert(config.submission?.externalContactPerformed === false,
    'committed pre-submission packet must not claim that contact was performed');
  assert(JSON.stringify(config.submission?.allowedMethods) === JSON.stringify(['verified_email']),
    'only the sealed official email route is currently supported');
  assert(sha256Hex(actualMessageSha256), 'actual message SHA-256 is required');
  assert(config.submission?.message?.path === 'docs/STAGE17_ONGA_OFFICE_DATA_REQUEST_DRAFT.md',
    'message path mismatch');
  assert(config.submission?.message?.currentDraftSha256 === actualMessageSha256,
    'committed draft digest does not match the exact message file');

  const blockers = [];
  const requesterFields = [
    ['university', '所属大学'],
    ['facultyOrDepartment', '学部・研究科・部局'],
    ['laboratory', '研究室'],
    ['fullName', '氏名'],
    ['position', '職位'],
    ['email', '連絡先メールアドレス'],
    ['telephone', '連絡先電話番号'],
  ];
  for (const [key, label] of requesterFields) {
    if (!nonempty(config.requester?.[key])) blockers.push(blocker(
      `REQUESTER_${key.toUpperCase()}_MISSING`,
      `requester.${key}`,
      `${label}が必要である．`,
    ));
  }

  if (!nonempty(config.research?.formalProjectTitle)) blockers.push(blocker(
    'FORMAL_PROJECT_TITLE_MISSING',
    'research.formalProjectTitle',
    '正式な研究課題名が必要である．',
  ));
  const useStart = parseDateOrNull(config.research?.plannedUsePeriod?.start);
  const useEnd = parseDateOrNull(config.research?.plannedUsePeriod?.end);
  if (useStart === null || useEnd === null || useEnd < useStart) blockers.push(blocker(
    'PLANNED_USE_PERIOD_INVALID',
    'research.plannedUsePeriod',
    '研究資料の利用予定期間を有効な開始日・終了日で指定する必要がある．',
  ));
  if (!nonempty(config.research?.publicationScope)) blockers.push(blocker(
    'PUBLICATION_SCOPE_MISSING',
    'research.publicationScope',
    '論文・学会・Web公開等の成果公開範囲が必要である．',
  ));

  const dataMode = config.requestedDomain?.dataPeriod?.mode;
  if (!new Set(['specified_priority_period', 'all_available_with_priority_period']).has(dataMode)) blockers.push(blocker(
    'DATA_PERIOD_MODE_MISSING',
    'requestedDomain.dataPeriod.mode',
    '必要な観測・操作資料の期間指定方式が必要である．',
  ));
  const dataStart = parseDateOrNull(config.requestedDomain?.dataPeriod?.priorityStart);
  const dataEnd = parseDateOrNull(config.requestedDomain?.dataPeriod?.priorityEnd);
  if (dataStart === null || dataEnd === null || dataEnd < dataStart) blockers.push(blocker(
    'DATA_PRIORITY_PERIOD_INVALID',
    'requestedDomain.dataPeriod',
    '優先して取得するデータ期間を有効な開始日・終了日で指定する必要がある．',
  ));

  const selectedMethod = config.submission?.selectedMethod;
  const allowedMethods = new Set(config.submission?.allowedMethods ?? []);
  if (!allowedMethods.has(selectedMethod)) blockers.push(blocker(
    'SUBMISSION_METHOD_UNSELECTED',
    'submission.selectedMethod',
    '現行gateでは封印済みの公式メール経路を選択する必要がある．',
  ));
  const message = config.submission?.message;
  if (config.submission?.messageApprovedByRequester !== true
    || message?.approvedSha256 !== actualMessageSha256
    || message?.approvedBy !== config.requester?.fullName
    || parseDateOrNull(message?.approvedAt) === null) blockers.push(blocker(
    'MESSAGE_NOT_APPROVED',
    'submission.message',
    '送信する本文そのもののSHA-256，承認者，承認日時を固定した最終承認が必要である．',
  ));
  const route = config.recipient?.routeVerification;
  const routeCommonReady = config.submission?.recipientRouteVerified === true
    && route?.method === selectedMethod
    && nonempty(route?.destination)
    && nonempty(route?.officialSourceUrl)
    && route.officialSourceUrl.startsWith('https://')
    && sha256Hex(route?.officialSourceSha256)
    && parseDateOrNull(route?.verifiedAt) !== null
    && parseDateOrNull(route?.verifiedAt)
      >= parseDateOrNull(config.recipient?.officialContactEvidence?.retrievedAt)
    && nonempty(route?.verifiedBy);
  const methodRouteReady = selectedMethod === 'verified_email'
    && nonempty(config.recipient?.verifiedEmail)
    && route?.destination === config.recipient.verifiedEmail
    && route?.officialSourceUrl === config.recipient.officialContactEvidence.url
    && route?.officialSourceSha256 === config.recipient.officialContactEvidence.sha256;
  if (!routeCommonReady || !methodRouteReady) blockers.push(blocker(
    'RECIPIENT_ROUTE_NOT_VERIFIED',
    'recipient.routeVerification',
    '選択した方法，送信先，公式確認元のSHA-256，確認者，確認日時を送信直前に固定する必要がある．',
  ));

  return Object.freeze({
    schema: 'onga-stage17-official-request-readiness-report-v1',
    readyForSubmission: blockers.length === 0,
    blockerCount: blockers.length,
    blockers: Object.freeze(blockers),
    routeAApproved: true,
    externalContactPerformed: false,
    physicalValuesAssigned: false,
    exactMessageSha256: actualMessageSha256,
  });
}

const request = JSON.parse(await fs.readFile(requestPath, 'utf8'));
const decision = JSON.parse(await fs.readFile(decisionPath, 'utf8'));
const actualMessageSha256 = crypto.createHash('sha256')
  .update(await fs.readFile(request.submission.message.path))
  .digest('hex');
const templateReport = buildSubmissionReadiness(request, decision, actualMessageSha256);

const fixture = JSON.parse(JSON.stringify(request));
fixture.status = 'validator_only_ready_fixture';
fixture.requester = {
  university: '検証大学',
  facultyOrDepartment: '検証研究科',
  laboratory: '検証研究室',
  fullName: '検証 太郎',
  position: '教授',
  email: 'fixture@example.invalid',
  telephone: '000-0000-0000',
  postalAddress: null,
};
fixture.research.formalProjectTitle = '検証用研究課題';
fixture.research.plannedUsePeriod = { start: '2026-07-01', end: '2029-03-31' };
fixture.research.publicationScope = '査読論文，学会発表，研究室Webでの成果公開';
fixture.requestedDomain.dataPeriod = {
  ...fixture.requestedDomain.dataPeriod,
  mode: 'all_available_with_priority_period',
  priorityStart: '2025-01-01',
  priorityEnd: '2026-12-31',
};
fixture.recipient.routeVerification = {
  method: 'verified_email',
  destination: fixture.recipient.verifiedEmail,
  officialSourceUrl: fixture.recipient.officialContactEvidence.url,
  officialSourceSha256: fixture.recipient.officialContactEvidence.sha256,
  verifiedAt: '2026-07-14T06:00:00Z',
  verifiedBy: 'verification-fixture',
};
fixture.submission.selectedMethod = 'verified_email';
fixture.submission.messageApprovedByRequester = true;
fixture.submission.message.approvedSha256 = actualMessageSha256;
fixture.submission.message.approvedBy = fixture.requester.fullName;
fixture.submission.message.approvedAt = '2026-07-14T00:00:00Z';
fixture.submission.recipientRouteVerified = true;
const fixtureReport = buildSubmissionReadiness(fixture, decision, actualMessageSha256);

const alteredDecision = JSON.parse(JSON.stringify(decision));
alteredDecision.optionId = 'public_database_only';
let alteredDecisionRejected = false;
try {
  buildSubmissionReadiness(request, alteredDecision, actualMessageSha256);
} catch (_) {
  alteredDecisionRejected = true;
}

const alteredGeometry = JSON.parse(JSON.stringify(request));
alteredGeometry.safeguards.approvedWaterGeometryChanged = true;
let alteredGeometryRejected = false;
try {
  buildSubmissionReadiness(alteredGeometry, decision, actualMessageSha256);
} catch (_) {
  alteredGeometryRejected = true;
}

const tamperedApproval = JSON.parse(JSON.stringify(fixture));
tamperedApproval.submission.message.approvedSha256 = 'b'.repeat(64);
const tamperedApprovalReport = buildSubmissionReadiness(
  tamperedApproval,
  decision,
  actualMessageSha256,
);

const mismatchedRoute = JSON.parse(JSON.stringify(fixture));
mismatchedRoute.recipient.routeVerification.destination = 'different@example.invalid';
const mismatchedRouteReport = buildSubmissionReadiness(
  mismatchedRoute,
  decision,
  actualMessageSha256,
);

const alteredContactEvidence = JSON.parse(JSON.stringify(request));
alteredContactEvidence.recipient.officialContactEvidence.sha256 = 'c'.repeat(64);
let alteredContactEvidenceRejected = false;
try {
  buildSubmissionReadiness(alteredContactEvidence, decision, actualMessageSha256);
} catch (_) {
  alteredContactEvidenceRejected = true;
}

const requiredTemplateBlockers = [
  'REQUESTER_UNIVERSITY_MISSING',
  'REQUESTER_FULLNAME_MISSING',
  'FORMAL_PROJECT_TITLE_MISSING',
  'PLANNED_USE_PERIOD_INVALID',
  'PUBLICATION_SCOPE_MISSING',
  'DATA_PERIOD_MODE_MISSING',
  'DATA_PRIORITY_PERIOD_INVALID',
  'SUBMISSION_METHOD_UNSELECTED',
  'MESSAGE_NOT_APPROVED',
  'RECIPIENT_ROUTE_NOT_VERIFIED',
];
const templateCodes = new Set(templateReport.blockers.map(item => item.code));
const checks = [
  { name: 'committed template is not ready', ok: templateReport.readyForSubmission === false },
  { name: 'required requester and scope blockers are present', ok: requiredTemplateBlockers.every(code => templateCodes.has(code)) },
  { name: 'validator-only complete fixture is ready', ok: fixtureReport.readyForSubmission === true && fixtureReport.blockerCount === 0 },
  { name: 'non-A acquisition route is rejected', ok: alteredDecisionRejected },
  { name: 'approved geometry mutation is rejected', ok: alteredGeometryRejected },
  { name: 'message approval is bound to exact digest', ok: tamperedApprovalReport.blockers.some(item => item.code === 'MESSAGE_NOT_APPROVED') },
  { name: 'selected method is bound to the verified destination', ok: mismatchedRouteReport.blockers.some(item => item.code === 'RECIPIENT_ROUTE_NOT_VERIFIED') },
  { name: 'official contact evidence digest is immutable', ok: alteredContactEvidenceRejected },
  { name: 'external contact remains unperformed', ok: templateReport.externalContactPerformed === false },
  { name: 'no physical value is assigned', ok: templateReport.physicalValuesAssigned === false },
];
const output = {
  schema: 'onga-stage17-official-request-submission-validation-v1',
  status: checks.every(check => check.ok) ? 'passed' : 'failed',
  template: templateReport,
  validatorFixture: {
    readyForSubmission: fixtureReport.readyForSubmission,
    committed: false,
    purpose: 'positive-path validation only',
  },
  checks,
};
await fs.writeFile(outputPath, `${JSON.stringify(output, null, 2)}\n`, 'utf8');
if (output.status !== 'passed') throw new Error(JSON.stringify(output, null, 2));
console.log(JSON.stringify(output, null, 2));
