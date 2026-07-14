import fs from 'node:fs/promises';
import {
  STAGE17_PHYSICAL_DATA_SOURCE_INVENTORY_SCHEMAS,
  STAGE17_PHYSICAL_DATA_SOURCE_INVENTORY_VERSION,
  buildPhysicalDataSourceInventoryReport,
  loadPhysicalDataSourceInventory,
  validatePhysicalDataSourceInventory,
} from '../onga_stage17_physical_data_source_inventory.mjs';

const inventoryPath = process.argv[2] || 'config/stage17_physical_data_source_inventory_v2.json';
const outputPath = process.argv[3] || 'stage17-physical-data-source-inventory-validation.json';

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

function expectThrow(fn) {
  try {
    fn();
    return false;
  } catch (_) {
    return true;
  }
}

const inventory = await loadPhysicalDataSourceInventory(inventoryPath);
const defaultInventory = await loadPhysicalDataSourceInventory();
const historicalV1 = await loadPhysicalDataSourceInventory(
  'config/stage17_physical_data_source_inventory_v1.json',
);
const currentV2 = await loadPhysicalDataSourceInventory(
  'config/stage17_physical_data_source_inventory_v2.json',
);
const report = buildPhysicalDataSourceInventoryReport(inventory);
const historicalReport = buildPhysicalDataSourceInventoryReport(historicalV1);
const requirement = id => inventory.requirements.find(item => item.id === id);

const silentlySelected = clone(inventory);
silentlySelected.requirements[0].selectedCandidate = silentlySelected.requirements[0].candidates[0].id;
silentlySelected.requirements[0].decisionStatus = 'selected';
const silentSelectionRejected = expectThrow(() => validatePhysicalDataSourceInventory(silentlySelected));

const unknownSource = clone(inventory);
unknownSource.requirements[0].candidates[0].sourceIds.push('invented_source');
const unknownSourceRejected = expectThrow(() => validatePhysicalDataSourceInventory(unknownSource));

const geometryMutation = clone(inventory);
geometryMutation.safeguards.approvedWaterGeometryChanged = true;
const geometryMutationRejected = expectThrow(() => validatePhysicalDataSourceInventory(geometryMutation));

const automaticApproval = clone(inventory);
automaticApproval.safeguards.sourceCandidateAutomaticallyApproved = true;
const automaticApprovalRejected = expectThrow(() => validatePhysicalDataSourceInventory(automaticApproval));

const multipleRecommendations = clone(inventory);
multipleRecommendations.nextDecision.options[1].recommended = true;
const multipleRecommendationsRejected = expectThrow(() => validatePhysicalDataSourceInventory(multipleRecommendations));

const routeOverwrite = clone(inventory);
routeOverwrite.nextDecision.selectedOption = 'B_public_data_only';
const routeRerecordRejected = expectThrow(() => validatePhysicalDataSourceInventory(routeOverwrite));

const historicalIdentityMutation = clone(historicalV1);
historicalIdentityMutation.modelDomain.metricMeshCellCount = currentV2.modelDomain.metricMeshCellCount;
const historicalIdentityMutationRejected = expectThrow(
  () => validatePhysicalDataSourceInventory(historicalIdentityMutation),
);

const currentVersionDowngrade = clone(currentV2);
currentVersionDowngrade.version = 'stage17-physical-data-source-inventory-v1';
const currentVersionDowngradeRejected = expectThrow(
  () => validatePhysicalDataSourceInventory(currentVersionDowngrade),
);

const requiredIds = new Set(inventory.requirements.map(item => item.id));
const allCandidateSourceIdsValid = inventory.requirements.every(item => item.candidates.every(candidate => (
  candidate.sourceIds.every(sourceId => inventory.officialSources.some(source => source.id === sourceId))
)));
const noPhysicalSourceSelected = inventory.requirements.every(item => (
  item.selectedCandidate === null && item.decisionStatus === 'unselected'
));
const jmaCandidate = requirement('M_mouth_water_level_boundary').candidates
  .find(item => item.id === 'jma_astronomical_tide_secondary_reference');
const magariRequirement = requirement('G_magarigawa_boundary');
const bathymetryRequirement = requirement('bathymetry_and_vertical_datum');
const depthHypothesis = inventory.physicalHypotheses
  .find(item => item.id === 'cross_channel_depth_profile');

const checks = [
  check('supported inventory schemas', STAGE17_PHYSICAL_DATA_SOURCE_INVENTORY_SCHEMAS.length, 2,
    STAGE17_PHYSICAL_DATA_SOURCE_INVENTORY_SCHEMAS.length === 2),
  check('default inventory is current v2', defaultInventory.version,
    'stage17-physical-data-source-inventory-v2',
    defaultInventory.version === 'stage17-physical-data-source-inventory-v2'),
  check('historical v1 remains readable', historicalV1.version,
    'stage17-physical-data-source-inventory-v1',
    validatePhysicalDataSourceInventory(historicalV1)),
  check('historical v1 identity remains frozen',
    `${historicalV1.modelDomain.approvedWaterPixelCount}/${historicalV1.modelDomain.metricMeshCellCount}`,
    '679791/50333',
    historicalV1.modelDomain.approvedWaterAuthorityVersion === 'v4.8.0-candidate-r2'
      && historicalV1.modelDomain.approvedWaterPixelCount === 679791
      && historicalV1.modelDomain.metricMeshCellCount === 50333
      && historicalV1.nextDecision.status === 'pending'
      && historicalReport.routeDecisionRequired === true),
  check('current v2 identity is frozen',
    `${currentV2.modelDomain.approvedWaterPixelCount}/${currentV2.modelDomain.metricMeshCellCount}`,
    '680633/50129',
    currentV2.modelDomain.approvedWaterAuthorityVersion === 'v4.8.0-candidate-r3'
      && currentV2.modelDomain.approvedWaterPixelCount === 680633
      && currentV2.modelDomain.metricMeshCellCount === 50129),
  check('historical v1 identity mutation rejected', historicalIdentityMutationRejected, true,
    historicalIdentityMutationRejected),
  check('current v2 version downgrade rejected', currentVersionDowngradeRejected, true,
    currentVersionDowngradeRejected),
  check('inventory version', inventory.version, STAGE17_PHYSICAL_DATA_SOURCE_INVENTORY_VERSION,
    inventory.version === STAGE17_PHYSICAL_DATA_SOURCE_INVENTORY_VERSION),
  check('selected governing equation', inventory.governingEquation.selected,
    'depth_averaged_shallow_water', inventory.governingEquation.selected === 'depth_averaged_shallow_water'),
  check('approved water pixels frozen', inventory.modelDomain.approvedWaterPixelCount, 680633,
    inventory.modelDomain.approvedWaterPixelCount === 680633 && inventory.modelDomain.geometryFrozen === true),
  check('metric mesh cells frozen', inventory.modelDomain.metricMeshCellCount, 50129,
    inventory.modelDomain.metricMeshCellCount === 50129),
  check('all nine data requirements present', requiredIds.size, 9, requiredIds.size === 9),
  check('all candidate source references valid', allCandidateSourceIdsValid, true, allCandidateSourceIdsValid),
  check('no source candidate silently selected', noPhysicalSourceSelected, true, noPhysicalSourceSelected),
  check('all requirements unresolved before human choice', report.unresolvedRequirementCount,
    inventory.requirements.length, report.unresolvedRequirementCount === inventory.requirements.length),
  check('physical validation remains not ready', report.physicalValidationReady, false,
    report.physicalValidationReady === false),
  check('public production remains not ready', report.publicProductionReady, false,
    report.publicProductionReady === false),
  check('official request plus public retrieval recommended', report.recommendedDecisionOption,
    'A_official_request_plus_public_retrieval',
    report.recommendedDecisionOption === 'A_official_request_plus_public_retrieval'),
  check('external-contact package requires submission readiness',
    inventory.acquisitionPackages.find(item => item.id === 'package_A_official_office_request').status,
    'route_approved_submission_readiness_required',
    inventory.acquisitionPackages.find(item => item.id === 'package_A_official_office_request').status
      === 'route_approved_submission_readiness_required'),
  check('public retrieval package can proceed independently',
    report.publicRetrievalPackages.includes('package_B_public_database_retrieval'), true,
    report.publicRetrievalPackages.includes('package_B_public_database_retrieval')),
  check('JMA tide retained as secondary only', jmaCandidate.currentSufficiency,
    'secondary_reference_only', jmaCandidate.currentSufficiency === 'secondary_reference_only'),
  check('Magarigawa direct public station remains missing', magariRequirement.candidates[0].currentSufficiency,
    'missing', magariRequirement.candidates[0].currentSufficiency === 'missing'),
  check('synthetic bed rejected for physical validation',
    bathymetryRequirement.candidates.find(item => item.id === 'synthetic_or_image_inferred_bed').currentSufficiency,
    'rejected_for_physical_validation',
    bathymetryRequirement.candidates.find(item => item.id === 'synthetic_or_image_inferred_bed').currentSufficiency
      === 'rejected_for_physical_validation'),
  check('reviewed cross-channel depth pattern remains an unverified hypothesis',
    depthHypothesis.status, 'unverified',
    depthHypothesis.status === 'unverified'
      && depthHypothesis.preferredIdealizedShape
        === 'smooth_symmetric_inverted_normal_distribution_like_trough'
      && depthHypothesis.solverUseApproved === false
      && depthHypothesis.visualFittingAllowed === false),
  check('route A is already recorded', inventory.nextDecision.selectedOption,
    'A_official_request_plus_public_retrieval',
    inventory.nextDecision.status === 'recorded'
      && inventory.nextDecision.selectedOption === 'A_official_request_plus_public_retrieval'
      && report.routeDecisionRequired === false),
  check('external submission remains a later decision', report.nextDecisionId,
    'stage17_official_request_submission',
    report.humanDecisionRequired === true
      && report.nextDecisionId === 'stage17_official_request_submission'),
  check('silent source selection rejected', silentSelectionRejected, true, silentSelectionRejected),
  check('unknown source reference rejected', unknownSourceRejected, true, unknownSourceRejected),
  check('approved geometry mutation rejected', geometryMutationRejected, true, geometryMutationRejected),
  check('automatic source approval rejected', automaticApprovalRejected, true, automaticApprovalRejected),
  check('multiple recommendations rejected', multipleRecommendationsRejected, true,
    multipleRecommendationsRejected),
  check('recorded acquisition route cannot be overwritten', routeRerecordRejected, true,
    routeRerecordRejected),
  check('external contact not yet performed', inventory.safeguards.externalContactPerformed, false,
    inventory.safeguards.externalContactPerformed === false),
  check('legacy flow remains unchanged', inventory.safeguards.legacyFlowCalculationChanged, false,
    inventory.safeguards.legacyFlowCalculationChanged === false),
];

const validation = {
  schema: 'onga-stage17-physical-data-source-inventory-validation-v2',
  version: STAGE17_PHYSICAL_DATA_SOURCE_INVENTORY_VERSION,
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  inventoryReport: report,
  historicalV1: {
    version: historicalV1.version,
    approvedWaterPixelCount: historicalV1.modelDomain.approvedWaterPixelCount,
    metricMeshCellCount: historicalV1.modelDomain.metricMeshCellCount,
    routeDecisionStatus: historicalV1.nextDecision.status,
    readable: true,
  },
  checks,
  safeguards: inventory.safeguards,
};

await fs.writeFile(outputPath, `${JSON.stringify(validation, null, 2)}\n`, 'utf8');
if (validation.status !== 'passed') throw new Error(JSON.stringify(validation, null, 2));
console.log(JSON.stringify(validation, null, 2));
