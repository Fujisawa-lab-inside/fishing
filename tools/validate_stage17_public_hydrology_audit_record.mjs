import fs from 'node:fs/promises';

const inputPath = process.argv[2] || 'config/stage17_public_hydrology_audit_record_20260714.json';
const outputPath = process.argv[3]
  || 'stage17-public-hydrology-diagnostic-snapshot-validation.json';
const record = JSON.parse(await fs.readFile(inputPath, 'utf8'));

const EXPECTED_ALLOWED_HOSTS = Object.freeze([
  'www.data.jma.go.jp',
  'www.qsr.mlit.go.jp',
  'www.river.go.jp',
  'www1.river.go.jp',
]);
const EXPECTED_SOURCE_REPORT_SHA256 = Object.freeze({
  official_page_probe: '6e23d6426716abdf2a531eadb436db15e52a5452b91f2f8b9d3eb66fa85d3f6b',
  official_river_api_probe: 'bfbf8ff1232e1c32fee0e08f8a33d1e4ce5899f44f23804ed82a85076044d27f',
  station_boundary_compatibility_audit: '6f1a6427dd685d0433a7ac09dd38e68c2c96a0d941566551c0b6636c73e15a8c',
});
const EXPECTED_STATION_NAMES = Object.freeze({
  gion_bridge: '祇園橋',
  karakuma: '唐熊',
  nakama: '中間',
});
const EXPECTED_REQUIREMENT_IDS = Object.freeze([
  'bathymetry_and_vertical_datum',
  'M_mouth_water_level_boundary',
  'N_nishikawa_boundary',
  'O_mainstem_boundary',
  'G_magarigawa_boundary',
  'manning_roughness',
  'fishway_hydraulics',
  'barrage_hydraulics_and_operation',
  'independent_velocity_validation',
]);
const EXPECTED_CONTACT_PAGE = 'https://www.qsr.mlit.go.jp/onga/access/index.html';
const EXPECTED_CONTACT_PAGE_SHA256 = 'a42fb487de0c39c8215a9fcb70010caf056e09a2f31172035a086736aef0adee';

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

function exactStringSet(values, expected) {
  return Array.isArray(values)
    && values.length === expected.length
    && new Set(values).size === expected.length
    && expected.every(value => values.includes(value));
}

function exactObject(value, expected) {
  return value && typeof value === 'object'
    && Object.keys(value).length === Object.keys(expected).length
    && Object.entries(expected).every(([key, expectedValue]) => value[key] === expectedValue);
}

const stations = record.stationDiagnostics ?? [];
const sourceReports = record.sourceReports ?? [];
const sourceReportShaByRole = Object.fromEntries(
  sourceReports.map(item => [item.role, item.sha256]),
);
const requirementIds = record.physicalSourceSelection?.requirementIds ?? [];
const selectedRequirementIds = record.physicalSourceSelection?.selectedRequirementIds ?? [];
const safeguards = record.safeguards ?? {};
const recomputedSummary = {
  stationCount: stations.length,
  stationIdentityMatchCount: stations.filter(
    item => EXPECTED_STATION_NAMES[item.id] === item.name,
  ).length,
  stationWithPublicRecentWaterLevelCount: stations.filter(
    item => item.publicWaterLevelSeriesAvailable === true,
  ).length,
  stationWithPublicDischargeFieldCount: stations.filter(
    item => item.publicDischargeFieldAvailable === true,
  ).length,
  stationWithResolvedVerticalDatumCount: stations.filter(
    item => item.verticalDatumMeaningResolved === true,
  ).length,
  stationInsideApprovedWaterCount: stations.filter(
    item => item.insideApprovedWater === true,
  ).length,
  physicalRequirementCount: requirementIds.length,
  selectedPhysicalSourceCount: selectedRequirementIds.length,
  physicalValidationReady: requirementIds.length > 0
    && selectedRequirementIds.length === requirementIds.length
    && safeguards.physicalValuesAssigned === true
    && safeguards.physicalRunEnabled === true,
};
const checks = [
  check('schema', record.schema,
    'onga-stage17-public-hydrology-diagnostic-audit-snapshot-v1',
    record.schema === 'onga-stage17-public-hydrology-diagnostic-audit-snapshot-v1'),
  check('evidence is a diagnostic snapshot rather than a sealed authorization',
    record.evidenceClassification?.kind, 'diagnostic_audit_snapshot',
    record.evidenceClassification?.kind === 'diagnostic_audit_snapshot'
      && record.evidenceClassification?.sealedRecord === false
      && record.evidenceClassification?.authorizesSourceSelection === false),
  check('diagnostic status does not approve sources', record.status,
    'diagnostic_snapshot_sources_unselected',
    record.status === 'diagnostic_snapshot_sources_unselected'),
  check('corrected water identity', record.approvedDomain?.approvedWaterPixelCount, 680633,
    record.approvedDomain?.waterAuthorityVersion === 'v4.8.0-candidate-r3'
      && record.approvedDomain?.approvedWaterPixelCount === 680633),
  check('corrected mesh identity', record.approvedDomain?.metricMeshCellCount, 50129,
    record.approvedDomain?.metricMeshVersion === 'stage16-metric-fv-mesh-v2'
      && record.approvedDomain?.metricMeshCellCount === 50129),
  check('network method restricted', record.networkPolicy?.method, 'HTTPS_GET_only',
    record.networkPolicy?.method === 'HTTPS_GET_only'
      && record.networkPolicy?.redirectsOutsideAllowlistRejected === true
      && exactStringSet(record.networkPolicy?.allowedHosts, EXPECTED_ALLOWED_HOSTS)),
  check('three source report roles and SHA-256 values are exact', sourceReportShaByRole,
    EXPECTED_SOURCE_REPORT_SHA256,
    sourceReports.length === 3
      && new Set(sourceReports.map(item => item.role)).size === 3
      && exactObject(sourceReportShaByRole, EXPECTED_SOURCE_REPORT_SHA256)),
  check('three official station IDs and names are exact',
    Object.fromEntries(stations.map(item => [item.id, item.name])), EXPECTED_STATION_NAMES,
    stations.length === 3
      && exactObject(
        Object.fromEntries(stations.map(item => [item.id, item.name])),
        EXPECTED_STATION_NAMES,
      )),
  check('physical requirement inventory is exact and remains unselected', requirementIds,
    EXPECTED_REQUIREMENT_IDS,
    exactStringSet(requirementIds, EXPECTED_REQUIREMENT_IDS)
      && exactStringSet(selectedRequirementIds, [])),
  check('snapshot summary matches recomputed diagnostics', record.summary, recomputedSummary,
    exactObject(record.summary, recomputedSummary)),
  check('no station boundary assigned', stations.every(item => item.boundaryAssignment === null), true,
    stations.every(item => item.boundaryAssignment === null
      && item.hydraulicRoleInferredFromDistance === false)),
  check('public resources contain no discharge field',
    stations.filter(item => item.publicDischargeFieldAvailable).length, 0,
    stations.every(item => item.publicDischargeFieldAvailable === false)),
  check('vertical datum remains unresolved',
    stations.filter(item => item.verticalDatumMeaningResolved).length, 0,
    stations.every(item => item.verticalDatumMeaningResolved === false)),
  check('depth hypothesis remains unverified', record.bathymetryReview?.status, 'unverified',
    record.bathymetryReview?.status === 'unverified'
      && record.bathymetryReview?.preferredIdealizedShape
        === 'smooth_symmetric_inverted_normal_distribution_like_trough'
      && record.bathymetryReview?.visualFittingAllowed === false
      && record.bathymetryReview?.approvedForSolver === false),
  check('official email has page digest evidence', record.officialContact?.email,
    'onga@qsr.mlit.go.jp',
    record.officialContact?.email === 'onga@qsr.mlit.go.jp'
      && record.officialContact?.page === EXPECTED_CONTACT_PAGE
      && record.officialContact?.pageSha256 === EXPECTED_CONTACT_PAGE_SHA256
      && record.officialContact?.emailVerifiedOnOfficialPage === true
      && record.officialContact?.externalContactPerformed === false),
  check('external contact remains unperformed', safeguards.externalContactPerformed, false,
    safeguards.externalContactPerformed === false),
  check('physical values remain unassigned', safeguards.physicalValuesAssigned, false,
    safeguards.physicalValuesAssigned === false),
  check('physical run remains disabled', safeguards.physicalRunEnabled, false,
    safeguards.physicalRunEnabled === false),
  check('public simulator remains disconnected', safeguards.publicSimulatorConnected, false,
    safeguards.publicSimulatorConnected === false),
];

const report = {
  schema: 'onga-stage17-public-hydrology-diagnostic-snapshot-validation-v1',
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  snapshotSummary: record.summary,
  recomputedSummary,
  checks,
};

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
