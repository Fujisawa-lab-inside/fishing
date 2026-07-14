import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import {
  STAGE17_PHYSICAL_DATA_SOURCE_INVENTORY_VERSION,
  buildPhysicalDataSourceInventoryReport,
  loadPhysicalDataSourceInventory,
} from '../onga_stage17_physical_data_source_inventory.mjs';

const inventoryPath = process.argv[2] || 'config/stage17_physical_data_source_inventory_v2.json';
const outputPath = process.argv[3] || 'stage17-data-acquisition-decision-packet.json';
const decisionPath = 'config/stage17_physical_data_acquisition_decision_record_v3.json';
const retirementPath = 'config/stage17_external_contact_retirement_v1.json';
const inputPlanPath = 'config/stage19_public_inference_input_plan_v1.json';

const inventory = await loadPhysicalDataSourceInventory(inventoryPath);
if (inventory.version !== STAGE17_PHYSICAL_DATA_SOURCE_INVENTORY_VERSION) {
  throw new Error('the current packet must retain the v2 requirement inventory snapshot');
}
const report = buildPhysicalDataSourceInventoryReport(inventory);
const decisionText = await fs.readFile(decisionPath, 'utf8');
const decision = JSON.parse(decisionText);
const retirement = JSON.parse(await fs.readFile(retirementPath, 'utf8'));
const inputPlan = JSON.parse(await fs.readFile(inputPlanPath, 'utf8'));
const decisionSha256 = crypto.createHash('sha256').update(decisionText).digest('hex');

if (decision.optionId !== 'public_database_and_declared_inference_only'
  || decision.scope?.officialRequestPreparationAndSubmission !== false
  || decision.scope?.publicOfficialDatabaseAcquisition !== true
  || decision.scope?.declaredInferenceScenarioPreparation !== true) {
  throw new Error('the current public-data and declared-inference route is invalid');
}
if (retirement.governingDecision?.sha256 !== decisionSha256
  || retirement.retiredSubmissionPacket?.mayBeSubmitted !== false) {
  throw new Error('external-contact retirement is not bound to the current route');
}
if (inputPlan.governingRouteDecision?.sha256 !== decisionSha256) {
  throw new Error('Stage 19 input plan is not bound to the current route');
}

const selectedOption = inventory.nextDecision.options.find(option => option.id === 'B_public_data_only');
const packet = {
  schema: 'onga-stage17-data-acquisition-decision-packet-v3',
  version: 'stage17-public-data-and-inference-route-v1',
  generatedFrom: inventoryPath,
  inventorySnapshotStatus: 'requirements_retained_route_fields_superseded_by_v3_decision',
  inventoryAsOf: inventory.asOf,
  governingEquation: inventory.governingEquation.selected,
  approvedWaterPixelCount: inventory.modelDomain.approvedWaterPixelCount,
  metricMeshCellCount: inventory.modelDomain.metricMeshCellCount,
  inventorySnapshotReport: report,
  routeTransition: {
    decisionRecord: decisionPath,
    decisionSha256,
    supersededOption: 'A_official_request_plus_public_retrieval',
    selectedOption: 'B_public_data_only',
    implementationOptionId: decision.optionId,
    officialRequestEnabled: false,
    externalContactRetirement: retirementPath,
  },
  recommendation: {
    optionId: selectedOption.id,
    reason: [
      'The requester explicitly disabled every official-office contact route.',
      'Official public station metadata identifies water-level/discharge stations for Nishikawa and the Onga main stem, while station-to-boundary compatibility still requires review.',
      'Public JMA astronomical tide can constrain timing and shape only; it is not an observed Onga-mouth boundary level.',
      'Bathymetry, Magarigawa inflow, period-matched gate operation, fishway hydraulics, and velocity observations remain inference variables with declared uncertainty.',
      'The cross-channel shape and broad ranges are approved and 64 cases are generated; the next approval is limited to the exact relative M-boundary tide curve for solver integration and does not authorize a run.',
    ],
    doesNotApprove: inputPlan.visualDecision.doesNotApprove,
  },
  supportingDocuments: {
    acquisitionPlan: 'docs/STAGE17_PHYSICAL_DATA_ACQUISITION.md',
    currentRoute: 'docs/STAGE19_PUBLIC_DATA_INFERENCE_ROUTE.md',
    publicInferenceInputPlan: inputPlanPath,
    approvedShape: 'config/stage19_public_inference_shape_approval_v1.json',
    proposedScenarioRanges: 'config/stage19_inferred_scenario_ranges_v1.json',
    approvedScenarioRanges: 'config/stage19_inferred_scenario_ranges_approval_v1.json',
    provisionalEnsemble: 'config/stage19_provisional_ensemble_cases_v1.json',
    solverCoverageAudit: 'config/stage19_solver_parameter_coverage_audit_v1.json',
    proposedMBoundaryTide: 'config/stage19_m_boundary_tide_candidate_v1.json',
    retiredRouteHistory: 'docs/STAGE17_ACQUISITION_ROUTE_A.md',
  },
  inventoryHistory: {
    requirementSnapshot: 'config/stage17_physical_data_source_inventory_v2.json',
    historicalInitialSnapshot: 'config/stage17_physical_data_source_inventory_v1.json',
  },
  nextActionBoundary: {
    publicDatabaseInventoryMayProceedWithoutPhysicalParameterApproval: true,
    declaredInferencePreviewMayProceed: true,
    externalContactDisabled: true,
    physicalSourceSelectionRequiresLaterPerSourceApproval: true,
    visualInputReviewRequired: true,
    numericalRunEnabled: false,
    publicSimulatorConnected: false,
  },
};

await fs.writeFile(outputPath, `${JSON.stringify(packet, null, 2)}\n`, 'utf8');
console.log(JSON.stringify({
  status: 'generated',
  selectedOption: packet.recommendation.optionId,
  unresolvedRequirementCount: report.unresolvedRequirementCount,
  visualInputReviewRequired: packet.nextActionBoundary.visualInputReviewRequired,
  numericalRunEnabled: packet.nextActionBoundary.numericalRunEnabled,
  outputPath,
}, null, 2));
