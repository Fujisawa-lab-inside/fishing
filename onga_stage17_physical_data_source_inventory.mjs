import fs from 'node:fs/promises';

const INVENTORY_PROFILES = Object.freeze({
  'onga-stage17-physical-data-source-inventory-v1': Object.freeze({
    version: 'stage17-physical-data-source-inventory-v1',
    historical: true,
    asOf: '2026-07-12',
    waterAuthorityVersion: 'v4.8.0-candidate-r2',
    waterPixelCount: 679791,
    meshCellCount: 50333,
    officialRequestStatus: 'approval_required_before_external_contact',
  }),
  'onga-stage17-physical-data-source-inventory-v2': Object.freeze({
    version: 'stage17-physical-data-source-inventory-v2',
    historical: false,
    asOf: '2026-07-14',
    waterAuthorityVersion: 'v4.8.0-candidate-r3',
    waterPixelCount: 680633,
    meshCellCount: 50129,
    officialRequestStatus: 'route_approved_submission_readiness_required',
  }),
});

export const STAGE17_PHYSICAL_DATA_SOURCE_INVENTORY_VERSION = 'stage17-physical-data-source-inventory-v2';
export const STAGE17_PHYSICAL_DATA_SOURCE_INVENTORY_SCHEMAS = Object.freeze(
  Object.keys(INVENTORY_PROFILES),
);

const REQUIRED_REQUIREMENTS = Object.freeze([
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

function assert(condition, message) {
  if (!condition) throw new Error(`[stage17-source-inventory] ${message}`);
}

function nonempty(value, label) {
  const text = String(value ?? '').trim();
  assert(text.length > 0, `${label} must be nonempty`);
  return text;
}

function uniqueById(items, label) {
  assert(Array.isArray(items), `${label} must be an array`);
  const ids = new Set();
  for (const [index, item] of items.entries()) {
    const id = nonempty(item?.id, `${label}[${index}].id`);
    assert(!ids.has(id), `${label} contains duplicate id ${id}`);
    ids.add(id);
  }
  return ids;
}

function countBy(items, key) {
  const result = {};
  for (const item of items) {
    const value = String(item?.[key] ?? 'unspecified');
    result[value] = (result[value] ?? 0) + 1;
  }
  return Object.freeze(result);
}

function inventoryProfile(inventory) {
  const profile = INVENTORY_PROFILES[inventory?.schema];
  assert(profile, `unsupported schema ${String(inventory?.schema)}`);
  assert(inventory.version === profile.version, 'version mismatch');
  return profile;
}

export function validatePhysicalDataSourceInventory(inventory) {
  assert(inventory && typeof inventory === 'object', 'inventory must be an object');
  const profile = inventoryProfile(inventory);
  assert(Number.isFinite(Date.parse(inventory.asOf)), 'asOf must be an ISO date or timestamp');
  assert(inventory.asOf === profile.asOf, 'inventory date does not match its versioned snapshot');
  assert(inventory.governingEquation?.selected === 'depth_averaged_shallow_water',
    'governing equation must remain depth_averaged_shallow_water');
  assert(inventory.governingEquation?.scalarBaselineRetained === true,
    'scalar conservative baseline must remain retained');
  assert(inventory.modelDomain?.approvedWaterAuthorityVersion === profile.waterAuthorityVersion,
    'approved water authority version mismatch');
  assert(Number(inventory.modelDomain?.approvedWaterPixelCount) === profile.waterPixelCount,
    'approved water pixel count mismatch');
  assert(Number(inventory.modelDomain?.metricMeshCellCount) === profile.meshCellCount,
    'metric mesh cell count mismatch');
  assert(inventory.modelDomain?.geometryFrozen === true, 'model geometry must remain frozen');
  if (profile.historical) {
    assert(inventory.physicalHypotheses === undefined,
      'historical v1 must not be rewritten with later physical hypotheses');
  } else {
    assert(inventory.modelDomain?.waterManifest === 'data/onga_unified_water_manifest_r3.json',
      'approved water manifest mismatch');
    assert(inventory.modelDomain?.waterManifestSha256
      === '964eaa8d43607d0ac4cc6d81f37fa8a9ed8dc23563894ddce85b4252938fcbf7',
    'approved water manifest digest mismatch');
    assert(inventory.modelDomain?.metricMeshVersion === 'stage16-metric-fv-mesh-v2',
      'metric mesh version mismatch');
    assert(inventory.modelDomain?.metricMeshPackageSha256
      === 'f18ac352604e286be395f7ced1580f654c00b29cf65f310fcbce38fb00219fe2',
    'metric mesh package digest mismatch');
    assert(inventory.modelDomain?.meshConstraintsSha256
      === '44c629ba6b7eb7bf0c43a1863de0c4835d8d331c0d230e50d891a0b23043fb33',
    'metric mesh constraints digest mismatch');
    const depthHypothesis = inventory.physicalHypotheses?.find(
      item => item.id === 'cross_channel_depth_profile',
    );
    assert(depthHypothesis?.status === 'unverified',
      'cross-channel depth hypothesis must remain unverified');
    assert(depthHypothesis?.verificationSourceRequired
      === 'authoritative_surveyed_cross_sections_with_vertical_datum',
    'cross-channel depth hypothesis requires authoritative surveyed sections');
    assert(depthHypothesis?.solverUseApproved === false,
      'cross-channel depth hypothesis must not be approved for solver use');
    assert(depthHypothesis?.visualFittingAllowed === false,
      'visual fitting to the cross-channel depth hypothesis must remain forbidden');
  }

  const sourceIds = uniqueById(inventory.officialSources, 'officialSources');
  for (const source of inventory.officialSources) {
    nonempty(source.provider, `official source ${source.id} provider`);
    nonempty(source.authorityLevel, `official source ${source.id} authorityLevel`);
    nonempty(source.accessMode, `official source ${source.id} accessMode`);
    const url = nonempty(source.url, `official source ${source.id} url`);
    assert(url.startsWith('https://'), `official source ${source.id} must use https`);
  }

  const requirementIds = uniqueById(inventory.requirements, 'requirements');
  for (const required of REQUIRED_REQUIREMENTS) {
    assert(requirementIds.has(required), `required physical-data item ${required} is missing`);
  }
  for (const requirement of inventory.requirements) {
    assert(Array.isArray(requirement.requiredBy) && requirement.requiredBy.length > 0,
      `requirement ${requirement.id} must list requiredBy uses`);
    assert(requirement.decisionStatus === 'unselected',
      `requirement ${requirement.id} cannot be silently selected`);
    assert(requirement.selectedCandidate === null,
      `requirement ${requirement.id} selectedCandidate must remain null`);
    nonempty(requirement.recommendedAcquisition, `requirement ${requirement.id} recommendedAcquisition`);
    const candidateIds = uniqueById(requirement.candidates, `requirement ${requirement.id} candidates`);
    assert(candidateIds.size > 0, `requirement ${requirement.id} must have candidates`);
    for (const candidate of requirement.candidates) {
      assert(Array.isArray(candidate.sourceIds), `candidate ${candidate.id} sourceIds must be an array`);
      for (const sourceId of candidate.sourceIds) {
        assert(sourceIds.has(sourceId), `candidate ${candidate.id} references unknown source ${sourceId}`);
      }
      nonempty(candidate.accessState, `candidate ${candidate.id} accessState`);
      nonempty(candidate.authority, `candidate ${candidate.id} authority`);
      nonempty(candidate.currentSufficiency, `candidate ${candidate.id} currentSufficiency`);
    }
  }

  const packageIds = uniqueById(inventory.acquisitionPackages, 'acquisitionPackages');
  assert(packageIds.has('package_A_official_office_request'), 'official-office request package missing');
  assert(packageIds.has('package_B_public_database_retrieval'), 'public-database package missing');
  for (const item of inventory.acquisitionPackages) {
    assert(Number.isInteger(Number(item.priority)) && Number(item.priority) > 0,
      `acquisition package ${item.id} priority must be positive integer`);
    nonempty(item.status, `acquisition package ${item.id} status`);
    assert(Array.isArray(item.requestedItems) && item.requestedItems.length > 0,
      `acquisition package ${item.id} requestedItems missing`);
  }

  assert(inventory.nextDecision?.id === 'stage17_data_acquisition_route', 'next decision id mismatch');
  nonempty(inventory.nextDecision?.question, 'nextDecision.question');
  const optionIds = uniqueById(inventory.nextDecision?.options, 'nextDecision.options');
  assert(optionIds.has('A_official_request_plus_public_retrieval'), 'option A missing');
  assert(optionIds.has('B_public_data_only'), 'option B missing');
  assert(optionIds.has('C_synthetic_verification_only'), 'option C missing');
  const recommended = inventory.nextDecision.options.filter(option => option.recommended === true);
  assert(recommended.length === 1, 'exactly one acquisition option must be recommended');
  assert(recommended[0].id === 'A_official_request_plus_public_retrieval',
    'recommended acquisition route must be option A');
  const officialRequest = inventory.acquisitionPackages
    .find(item => item.id === 'package_A_official_office_request');
  assert(officialRequest?.status === profile.officialRequestStatus,
    'official request package status does not match the inventory version');
  if (profile.historical) {
    assert(inventory.nextDecision?.status === 'pending',
      'historical v1 route decision must remain pending');
    assert(inventory.nextDecision?.selectedOption === undefined,
      'historical v1 must not contain a later route selection');
    assert(inventory.nextDecision?.decisionRecord === undefined,
      'historical v1 must not contain a later route-decision record');
    assert(inventory.submissionDecision === undefined,
      'historical v1 must not contain a later submission decision');
  } else {
    assert(inventory.nextDecision?.status === 'recorded', 'route decision must be recorded');
    assert(inventory.nextDecision?.selectedOption === 'A_official_request_plus_public_retrieval',
      'recorded route must remain option A');
    assert(inventory.nextDecision?.decisionRecord
      === 'config/stage17_physical_data_acquisition_decision_record_v2.json',
    'recorded route decision path mismatch');
    assert(inventory.submissionDecision?.id === 'stage17_official_request_submission',
      'submission decision id mismatch');
    assert(inventory.submissionDecision?.requiresExplicitRequesterDecision === true,
      'external submission must require an explicit requester decision');
    assert(inventory.submissionDecision?.publicDatabaseRetrievalMayContinue === true,
      'approved public database retrieval must remain available');
    assert(inventory.submissionDecision?.physicalSourceSelectionAllowed === false,
      'physical source selection must remain disallowed');
    assert(inventory.submissionDecision?.physicalRunEnabled === false,
      'physical run must remain disabled');
  }

  const safeguards = inventory.safeguards ?? {};
  for (const name of [
    'approvedWaterGeometryChanged',
    'meshGeometryChanged',
    'physicalValuesAssigned',
    'sourceCandidateAutomaticallyApproved',
    'externalContactPerformed',
    'legacyFlowCalculationChanged',
    'publicSimulatorConnected',
    'calibrationPerformed',
  ]) {
    assert(safeguards[name] === false, `safeguard ${name} must be false`);
  }
  return true;
}

export function buildPhysicalDataSourceInventoryReport(inventory) {
  validatePhysicalDataSourceInventory(inventory);
  const profile = inventoryProfile(inventory);
  const candidates = inventory.requirements.flatMap(requirement => requirement.candidates.map(candidate => ({
    requirementId: requirement.id,
    ...candidate,
  })));
  const unresolved = inventory.requirements.filter(requirement => requirement.selectedCandidate === null);
  const publicRetrievalPackages = inventory.acquisitionPackages
    .filter(item => item.status === 'can_proceed_without_physical_model_approval')
    .map(item => item.id);
  const externalContactPackages = inventory.acquisitionPackages
    .filter(item => item.status === profile.officialRequestStatus)
    .map(item => item.id);
  const recordedRoute = profile.historical
    ? inventory.nextDecision.options.find(option => option.recommended === true)?.id ?? null
    : inventory.nextDecision.selectedOption;
  return Object.freeze({
    schema: profile.historical
      ? 'onga-stage17-physical-data-source-inventory-report-v1'
      : 'onga-stage17-physical-data-source-inventory-report-v2',
    version: profile.version,
    inventoryAsOf: inventory.asOf,
    governingEquation: inventory.governingEquation.selected,
    requirementCount: inventory.requirements.length,
    sourceCount: inventory.officialSources.length,
    candidateCount: candidates.length,
    unresolvedRequirementCount: unresolved.length,
    unresolvedRequirementIds: Object.freeze(unresolved.map(item => item.id)),
    sourceAccessSummary: countBy(inventory.officialSources, 'accessMode'),
    candidateSufficiencySummary: countBy(candidates, 'currentSufficiency'),
    publicRetrievalPackages: Object.freeze(publicRetrievalPackages),
    externalContactPackages: Object.freeze(externalContactPackages),
    recommendedDecisionOption: recordedRoute,
    routeDecisionRequired: profile.historical,
    nextDecisionId: profile.historical
      ? inventory.nextDecision.id
      : inventory.submissionDecision.id,
    humanDecisionRequired: true,
    physicalValidationReady: false,
    publicProductionReady: false,
    safeguards: Object.freeze({ ...inventory.safeguards }),
  });
}

export async function loadPhysicalDataSourceInventory(
  path = 'config/stage17_physical_data_source_inventory_v2.json',
) {
  const inventory = JSON.parse(await fs.readFile(path, 'utf8'));
  validatePhysicalDataSourceInventory(inventory);
  return Object.freeze(inventory);
}

export const Stage17PhysicalDataSourceInventory = Object.freeze({
  version: STAGE17_PHYSICAL_DATA_SOURCE_INVENTORY_VERSION,
  schemas: STAGE17_PHYSICAL_DATA_SOURCE_INVENTORY_SCHEMAS,
  requiredRequirements: REQUIRED_REQUIREMENTS,
  validatePhysicalDataSourceInventory,
  buildPhysicalDataSourceInventoryReport,
  loadPhysicalDataSourceInventory,
});
