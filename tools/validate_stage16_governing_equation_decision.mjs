import fs from 'node:fs/promises';
import {
  STAGE16_GOVERNING_EQUATION_DECISION_VERSION,
  buildGoverningEquationDecisionPacket,
  recordGoverningEquationDecision,
} from '../onga_stage16_governing_equation_decision.mjs';

const outputPath = process.argv[2] || 'stage16-governing-equation-decision-validation.json';

function check(name, value, expected, ok) {
  return { name, value, expected, ok: Boolean(ok) };
}

const objectives = {
  mass_conservation: 1,
  bidirectional_tidal_flow: 1.5,
  two_dimensional_velocity_vector: 2,
  tributary_confluence_interaction: 2,
  barrage_and_fishway_transfer: 1,
  water_level_propagation: 1.5,
  wetting_and_drying: 1,
};
const currentEvidence = {
  approvedWaterAuthorityReady: true,
  productionMeshAudited: false,
  scalarSyntheticBenchmarksPassed: true,
  shallowWaterSyntheticBenchmarksPassed: false,
  bathymetryApproved: false,
  roughnessApproved: false,
  boundaryInputsApproved: false,
  structureParametersApproved: false,
};
const packet = buildGoverningEquationDecisionPacket({
  objectiveWeights: objectives,
  evidence: currentEvidence,
});
const scalar = packet.candidates.find(candidate => candidate.id === 'scalar_conservative_skeleton');
const shallow = packet.candidates.find(candidate => candidate.id === 'depth_averaged_shallow_water');
const recorded = recordGoverningEquationDecision(packet, {
  optionId: 'continue_dual_track_without_selection',
  approvedBy: 'synthetic-validator',
  approvedAt: '2026-07-12T00:00:00.000Z',
  notes: 'Synthetic contract test only．',
});

const scalarOnlyPacket = buildGoverningEquationDecisionPacket({
  objectiveWeights: {
    mass_conservation: 1,
    bidirectional_tidal_flow: 0,
    two_dimensional_velocity_vector: 0,
    tributary_confluence_interaction: 0,
    barrage_and_fishway_transfer: 1,
    water_level_propagation: 0,
    wetting_and_drying: 0,
  },
  evidence: currentEvidence,
});

const completeShallowEvidence = {
  approvedWaterAuthorityReady: true,
  productionMeshAudited: true,
  scalarSyntheticBenchmarksPassed: true,
  shallowWaterSyntheticBenchmarksPassed: true,
  bathymetryApproved: true,
  roughnessApproved: true,
  boundaryInputsApproved: true,
  structureParametersApproved: true,
};
const physicallyReadyPacket = buildGoverningEquationDecisionPacket({
  objectiveWeights: objectives,
  evidence: completeShallowEvidence,
});

let unknownDecisionRejected = false;
try {
  recordGoverningEquationDecision(packet, {
    optionId: 'force_visual_fit',
    approvedBy: 'validator',
    approvedAt: '2026-07-12T00:00:00.000Z',
  });
} catch (_) {
  unknownDecisionRejected = true;
}

let invalidWeightRejected = false;
try {
  buildGoverningEquationDecisionPacket({
    objectiveWeights: { two_dimensional_velocity_vector: -1 },
  });
} catch (_) {
  invalidWeightRejected = true;
}

let invalidSelectionRejected = false;
try {
  buildGoverningEquationDecisionPacket({ currentSelection: 'visual_vector_fit' });
} catch (_) {
  invalidSelectionRejected = true;
}

const checks = [
  check('high-fidelity objectives recommend shallow water', packet.recommendation,
    'depth_averaged_shallow_water', packet.recommendation === 'depth_averaged_shallow_water'),
  check('shallow-water suitability exceeds scalar',
    shallow.suitabilityFraction - scalar.suitabilityFraction,
    '>0', shallow.suitabilityFraction > scalar.suitabilityFraction),
  check('scalar lacks vector velocity', scalar.unmetObjectives.includes('two_dimensional_velocity_vector'),
    true, scalar.unmetObjectives.includes('two_dimensional_velocity_vector')),
  check('scalar only partially represents confluence', scalar.partialObjectives.includes('tributary_confluence_interaction'),
    true, scalar.partialObjectives.includes('tributary_confluence_interaction')),
  check('selection remains unapproved', packet.selectionApproved, false,
    packet.selectionApproved === false && packet.currentSelection === null),
  check('human decision remains required', packet.humanDecisionRequired, true,
    packet.humanDecisionRequired === true),
  check('current packet not physically ready', packet.physicalValidationReady, false,
    packet.physicalValidationReady === false),
  check('current data gaps include bathymetry', packet.dataGaps.includes('approved bathymetry'),
    true, packet.dataGaps.includes('approved bathymetry')),
  check('current data gaps include production mesh audit', packet.dataGaps.includes('audited production mesh'),
    true, packet.dataGaps.includes('audited production mesh')),
  check('dual-track decision records no equation', recorded.currentSelection, null,
    recorded.selectionApproved && recorded.currentSelection === null),
  check('recorded decision removes pending flag', recorded.humanDecisionRequired, false,
    recorded.humanDecisionRequired === false),
  check('low-complexity objectives recommend scalar', scalarOnlyPacket.recommendation,
    'scalar_conservative_skeleton', scalarOnlyPacket.recommendation === 'scalar_conservative_skeleton'),
  check('complete evidence can make shallow physical validation ready', physicallyReadyPacket.physicalValidationReady,
    true, physicallyReadyPacket.physicalValidationReady === true),
  check('public readiness remains false', physicallyReadyPacket.publicProductionReady, false,
    physicallyReadyPacket.publicProductionReady === false),
  check('unknown decision rejected', unknownDecisionRejected, true, unknownDecisionRejected),
  check('negative objective weight rejected', invalidWeightRejected, true, invalidWeightRejected),
  check('unsupported current selection rejected', invalidSelectionRejected, true, invalidSelectionRejected),
  check('module version', packet.version, STAGE16_GOVERNING_EQUATION_DECISION_VERSION,
    packet.version === STAGE16_GOVERNING_EQUATION_DECISION_VERSION),
];

const report = {
  schema: 'onga-stage16-governing-equation-decision-validation-v1',
  moduleVersion: STAGE16_GOVERNING_EQUATION_DECISION_VERSION,
  status: checks.every(item => item.ok) ? 'passed' : 'failed',
  checks,
  safeguards: {
    recommendationIsApproval: false,
    selectionRecordedInProduction: false,
    connectedToPublicSimulator: false,
    modifiesApprovedWaterGeometry: false,
    physicalValuesAssigned: false,
    calibrationPerformed: false,
  },
};

await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
if (report.status !== 'passed') throw new Error(JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
