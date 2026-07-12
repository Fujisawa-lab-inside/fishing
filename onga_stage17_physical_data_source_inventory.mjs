import fs from 'node:fs/promises';

export const STAGE17_PHYSICAL_DATA_SOURCE_INVENTORY_VERSION = 'stage17-physical-data-source-inventory-v1';

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

export function validatePhysicalDataSourceInventory(inventory) {
  assert(inventory && typeof inventory === 'object', 'inventory must be an object');
  assert(inventory.schema === 'onga-stage17-physical-data-source-inventory-v1', 'schema mismatch');
  assert(inventory.version === STAGE17_PHYSICAL_DATA_SOURCE_INVENTORY_VERSION, 'version mismatch');
  assert(Number.isFinite(Date.parse(inventory.asOf)), 'asOf must be an ISO date or timestamp');
  assert(inventory.governingEquation?.selected === 'depth_averaged_shallow_water',
    'governing equation must remain depth_averaged_shallow_water');
  assert(inventory.governingEquation?.scalarBaselineRetained === true,
    'scalar conservative baseline must remain retained');
  assert(Number(inventory.modelDomain?.approvedWaterPixelCount) === 679791,
    'approved water pixel count mismatch');
  assert(Number(inventory.modelDomain?.metricMeshCellCount) === 50333,
    'metric mesh cell count mismatch');
  assert(inventory.modelDomain?.geometryFrozen === true, 'model geometry must remain frozen');

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
  assert(inventory.nextDecision?.status === 'pending', 'next decision must remain pending');
  nonempty(inventory.nextDecision?.question, 'nextDecision.question');
  const optionIds = uniqueById(inventory.nextDecision?.options, 'nextDecision.options');
  assert(optionIds.has('A_official_request_plus_public_retrieval'), 'option A missing');
  assert(optionIds.has('B_public_data_only'), 'option B missing');
  assert(optionIds.has('C_synthetic_verification_only'), 'option C missing');
  const recommended = inventory.nextDecision.options.filter(option => option.recommended === true);
  assert(recommended.length === 1, 'exactly one acquisition option must be recommended');
  assert(recommended[0].id === 'A_official_request_plus_public_retrieval',
    'recommended acquisition route must be option A');

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
  const candidates = inventory.requirements.flatMap(requirement => requirement.candidates.map(candidate => ({
    requirementId: requirement.id,
    ...candidate,
  })));
  const unresolved = inventory.requirements.filter(requirement => requirement.selectedCandidate === null);
  const publicRetrievalPackages = inventory.acquisitionPackages
    .filter(item => item.status === 'can_proceed_without_physical_model_approval')
    .map(item => item.id);
  const externalContactPackages = inventory.acquisitionPackages
    .filter(item => item.status === 'approval_required_before_external_contact')
    .map(item => item.id);
  return Object.freeze({
    schema: 'onga-stage17-physical-data-source-inventory-report-v1',
    version: STAGE17_PHYSICAL_DATA_SOURCE_INVENTORY_VERSION,
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
    recommendedDecisionOption: inventory.nextDecision.options.find(option => option.recommended)?.id ?? null,
    humanDecisionRequired: true,
    physicalValidationReady: false,
    publicProductionReady: false,
    safeguards: Object.freeze({ ...inventory.safeguards }),
  });
}

export function recordDataAcquisitionRouteDecision(inventory, decision) {
  validatePhysicalDataSourceInventory(inventory);
  const optionId = nonempty(decision?.optionId, 'decision.optionId');
  const option = inventory.nextDecision.options.find(item => item.id === optionId);
  assert(option, `unknown acquisition option ${optionId}`);
  const approvedBy = nonempty(decision?.approvedBy, 'decision.approvedBy');
  const approvedAt = nonempty(decision?.approvedAt, 'decision.approvedAt');
  assert(Number.isFinite(Date.parse(approvedAt)), 'decision.approvedAt must be an ISO timestamp');
  return Object.freeze({
    ...inventory,
    nextDecision: Object.freeze({
      ...inventory.nextDecision,
      status: 'recorded',
      selectedOption: optionId,
      approvedBy,
      approvedAt,
      notes: decision.notes ?? null,
    }),
    acquisitionRouteApproved: true,
    sourceCandidatesApproved: false,
    physicalValuesApproved: false,
    externalContactAuthorized: optionId === 'A_official_request_plus_public_retrieval',
  });
}

export async function loadPhysicalDataSourceInventory(
  path = 'config/stage17_physical_data_source_inventory_v1.json',
) {
  const inventory = JSON.parse(await fs.readFile(path, 'utf8'));
  validatePhysicalDataSourceInventory(inventory);
  return Object.freeze(inventory);
}

export const Stage17PhysicalDataSourceInventory = Object.freeze({
  version: STAGE17_PHYSICAL_DATA_SOURCE_INVENTORY_VERSION,
  requiredRequirements: REQUIRED_REQUIREMENTS,
  validatePhysicalDataSourceInventory,
  buildPhysicalDataSourceInventoryReport,
  recordDataAcquisitionRouteDecision,
  loadPhysicalDataSourceInventory,
});
