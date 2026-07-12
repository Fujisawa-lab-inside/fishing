import fs from 'node:fs/promises';
import {
  STAGE17_PHYSICAL_DATA_SOURCE_INVENTORY_VERSION,
  buildPhysicalDataSourceInventoryReport,
  loadPhysicalDataSourceInventory,
  recordDataAcquisitionRouteDecision,
  validatePhysicalDataSourceInventory,
} from '../onga_stage17_physical_data_source_inventory.mjs';

const inventoryPath = process.argv[2] || 'config/stage17_physical_data_source_inventory_v1.json';
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
const report = buildPhysicalDataSourceInventoryReport(inventory);
const requirement = id => inventory.requirements.find(item => item.id === id);

const optionA = recordDataAcquisitionRouteDecision(inventory, {
  optionId: 'A_official_request_plus_public_retrieval',
  approvedBy: 'synthetic-validator',
  approvedAt: '2026-07-12T00:00:00.000Z',
  notes: 'Decision-record contract test only．',
});
const optionB = recordDataAcquisitionRouteDecision(inventory, {
  optionId: 'B_public_data_only',
  approvedBy: 'synthetic-validator',
  approvedAt: '2026-07-12T00:00:00.000Z',
});

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

const unknownOptionRejected = expectThrow(() => recordDataAcquisitionRouteDecision(inventory, {
  optionId: 'force_visual_fit',
  approvedBy: 'synthetic-validator',
  approvedAt: '2026-07-12T00:00:00.000Z',
}));

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

const checks = [
  check('inventory version', inventory.version, STAGE17_PHYSICAL_DATA_SOURCE_INVENTORY_VERSION,
    inventory.version === STAGE17_PHYSICAL_DATA_SOURCE_INVENTORY_VERSION),
  check('selected governing equation', inventory.governingEquation.selected,
    'depth_averaged_shallow_water', inventory.governingEquation.selected === 'depth_averaged_shallow_water'),
  check('approved water pixels frozen', inventory.modelDomain.approvedWaterPixelCount, 679791,
    inventory.modelDomain.approvedWaterPixelCount === 679791 && inventory.modelDomain.geometryFrozen === true),
  check('metric mesh cells frozen', inventory.modelDomain.metricMeshCellCount, 50333,
    inventory.modelDomain.metricMeshCellCount === 50333),
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
  check('external-contact package requires approval',
    inventory.acquisitionPackages.find(item => item.id === 'package_A_official_office_request').status,
    'approval_required_before_external_contact',
    inventory.acquisitionPackages.find(item => item.id === 'package_A_official_office_request').status
      === 'approval_required_before_external_contact'),
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
  check('option A authorizes contact route only', optionA.externalContactAuthorized, true,
    optionA.externalContactAuthorized === true
      && optionA.sourceCandidatesApproved === false
      && optionA.physicalValuesApproved === false),
  check('option B does not authorize external contact', optionB.externalContactAuthorized, false,
    optionB.externalContactAuthorized === false),
  check('silent source selection rejected', silentSelectionRejected, true, silentSelectionRejected),
  check('unknown source reference rejected', unknownSourceRejected, true, unknownSourceRejected),
  check('approved geometry mutation rejected', geometryMutationRejected, true, geometryMutationRejected),
  check('automatic source approval rejected', automaticApprovalRejected, true, automaticApprovalRejected),
  check('multiple recommendations rejected', multipleRecommendationsRejected, true,
    multipleRecommendationsRejected),
  check('unknown acquisition option rejected', unknownOptionRejected, true, unknownOptionRejected),
  check('external contact not yet performed', inventory.safeguards.externalContactPerformed, false,
    inventory.safeguards.externalContactPerformed === false),
  check('legacy flow remains unchanged', inventory.safeguards.legacyFlowCalculationChanged, false,
    inventory.safeguards.legacyFlowCalculationChanged === false),
];

const validation = {
  schema: 'onga-stage17-physical-data-source-inventory-validation-v1',
  version: STAGE17_PHYSICAL_DATA_SOURCE_INVENTORY_VERSION,
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  inventoryReport: report,
  checks,
  safeguards: inventory.safeguards,
};

await fs.writeFile(outputPath, `${JSON.stringify(validation, null, 2)}\n`, 'utf8');
if (validation.status !== 'passed') throw new Error(JSON.stringify(validation, null, 2));
console.log(JSON.stringify(validation, null, 2));
