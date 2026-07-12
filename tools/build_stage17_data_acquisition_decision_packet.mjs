import fs from 'node:fs/promises';
import {
  buildPhysicalDataSourceInventoryReport,
  loadPhysicalDataSourceInventory,
} from '../onga_stage17_physical_data_source_inventory.mjs';

const inventoryPath = process.argv[2] || 'config/stage17_physical_data_source_inventory_v1.json';
const outputPath = process.argv[3] || 'stage17-data-acquisition-decision-packet.json';
const inventory = await loadPhysicalDataSourceInventory(inventoryPath);
const report = buildPhysicalDataSourceInventoryReport(inventory);
const recommended = inventory.nextDecision.options.find(option => option.recommended === true);

const packet = {
  schema: 'onga-stage17-data-acquisition-decision-packet-v1',
  version: inventory.version,
  generatedFrom: inventoryPath,
  inventoryAsOf: inventory.asOf,
  governingEquation: inventory.governingEquation.selected,
  approvedWaterPixelCount: inventory.modelDomain.approvedWaterPixelCount,
  metricMeshCellCount: inventory.modelDomain.metricMeshCellCount,
  report,
  decision: inventory.nextDecision,
  recommendation: {
    optionId: recommended.id,
    reason: [
      'Surveyed bathymetry and its vertical datum cannot be reconstructed from the approved water mask.',
      'The public water-level network does not by itself establish discharge at every model boundary，and no direct public Magarigawa station has been identified.',
      'Gatewise barrage operation，effective geometry，fishway hydraulics，and independent velocity observations are most credibly obtained from the managing office or its official records.',
      'Public database retrieval should proceed in parallel because it can establish station metadata，available time series，quality flags，and candidate periods before any solver assignment.'
    ],
    doesNotApprove: [
      'Any candidate source for solver use',
      'Any bathymetry or vertical datum',
      'Any Manning roughness value or calibration',
      'Any M，N，O，or G boundary assignment',
      'Any fishway or barrage hydraulic parameter',
      'Any physical run or public release'
    ]
  },
  supportingDocuments: {
    acquisitionPlan: 'docs/STAGE17_PHYSICAL_DATA_ACQUISITION.md',
    unsentOfficeRequestDraft: 'docs/STAGE17_ONGA_OFFICE_DATA_REQUEST_DRAFT.md'
  },
  nextActionBoundary: {
    publicDatabaseInventoryMayProceedWithoutPhysicalParameterApproval: true,
    externalContactRequiresExplicitRouteDecision: true,
    physicalSourceSelectionRequiresLaterPerSourceApproval: true,
    physicalRunEnabled: false
  }
};

await fs.writeFile(outputPath, `${JSON.stringify(packet, null, 2)}\n`, 'utf8');
console.log(JSON.stringify({
  status: 'generated',
  recommendation: packet.recommendation.optionId,
  unresolvedRequirementCount: report.unresolvedRequirementCount,
  humanDecisionRequired: report.humanDecisionRequired,
  physicalValidationReady: report.physicalValidationReady,
  outputPath,
}, null, 2));
