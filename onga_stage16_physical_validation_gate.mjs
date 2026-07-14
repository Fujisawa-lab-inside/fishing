import fs from 'node:fs/promises';
import path from 'node:path';
import {
  buildGoverningEquationDecisionPacket,
  recordGoverningEquationDecision,
} from './onga_stage16_governing_equation_decision.mjs';
import {
  assertPhysicalSimulationReady,
  loadPhysicalReadinessConfiguration,
  physicalReadinessReport,
  validatePhysicalReadinessConfiguration,
} from './onga_stage16_physical_readiness.mjs';

export const STAGE16_PHYSICAL_VALIDATION_GATE_VERSION = 'stage16-physical-validation-gate-v1';
export const STAGE16_SELECTED_GOVERNING_EQUATION = 'depth_averaged_shallow_water';
export const STAGE16_SELECTED_DECISION_OPTION = 'adopt_depth_averaged_shallow_water_for_validation';
const VERIFIED_GATE_INPUTS = new WeakSet();

function blocker(code, pathName, message) {
  return Object.freeze({ code, path: pathName, message });
}

function nonempty(value) {
  return typeof value === 'string' && value.trim().length > 0;
}

function deepFreeze(value) {
  if (!value || typeof value !== 'object' || Object.isFrozen(value)) return value;
  for (const child of Object.values(value)) deepFreeze(child);
  return Object.freeze(value);
}

export function governingEquationSelectionReport({
  decisionInput,
  decisionRecord,
  readinessConfig,
}) {
  const blockers = [];
  let packet = null;

  try {
    if (decisionInput?.schema !== 'onga-stage16-governing-equation-decision-input-v1') {
      throw new Error('decision input schema mismatch');
    }
    if (decisionRecord?.schema !== 'onga-stage16-governing-equation-decision-record-v1') {
      throw new Error('decision record schema mismatch');
    }
    const basePacket = buildGoverningEquationDecisionPacket({
      objectiveWeights: decisionInput.objectiveWeights,
      evidence: decisionInput.evidence,
      currentSelection: decisionInput.currentSelection,
    });
    packet = recordGoverningEquationDecision(basePacket, decisionRecord);
  } catch (error) {
    blockers.push(blocker(
      'GOVERNING_EQUATION_DECISION_INVALID',
      'decisionRecord',
      String(error?.message ?? error),
    ));
  }

  if (packet) {
    if (decisionRecord.optionId !== STAGE16_SELECTED_DECISION_OPTION) blockers.push(blocker(
      'GOVERNING_EQUATION_OPTION_MISMATCH',
      'decisionRecord.optionId',
      `Expected ${STAGE16_SELECTED_DECISION_OPTION}.`,
    ));
    if (decisionRecord.governingEquation !== STAGE16_SELECTED_GOVERNING_EQUATION) blockers.push(blocker(
      'GOVERNING_EQUATION_RECORD_MISMATCH',
      'decisionRecord.governingEquation',
      `Expected ${STAGE16_SELECTED_GOVERNING_EQUATION}.`,
    ));
    if (packet.currentSelection !== STAGE16_SELECTED_GOVERNING_EQUATION
      || packet.selectionApproved !== true
      || packet.humanDecisionRequired !== false) blockers.push(blocker(
      'GOVERNING_EQUATION_SELECTION_UNAPPROVED',
      'decisionRecord',
      'The shallow-water selection is not recorded as an explicit human decision.',
    ));
  }

  const configured = readinessConfig?.governingEquation;
  if (readinessConfig?.schema !== 'onga-stage16-physical-readiness-v2') blockers.push(blocker(
    'READINESS_SCHEMA_DOWNGRADE_REJECTED',
    'schema',
    'Physical execution requires the current corrected v2 readiness schema; v1 is historical evidence only.',
  ));
  if (!configured || configured.selected !== STAGE16_SELECTED_GOVERNING_EQUATION) blockers.push(blocker(
    'READINESS_GOVERNING_EQUATION_MISMATCH',
    'governingEquation.selected',
    `The physical-readiness contract must select ${STAGE16_SELECTED_GOVERNING_EQUATION}.`,
  ));
  if (configured?.selectionApproved !== true) blockers.push(blocker(
    'READINESS_GOVERNING_EQUATION_UNAPPROVED',
    'governingEquation.selectionApproved',
    'The physical-readiness contract must preserve the explicit selection approval.',
  ));
  if (!nonempty(configured?.decisionRecord)) blockers.push(blocker(
    'READINESS_DECISION_RECORD_MISSING',
    'governingEquation.decisionRecord',
    'The readiness contract must link the machine-readable decision record.',
  ));
  if (configured?.approvedBy !== decisionRecord?.approvedBy
    || configured?.approvedAt !== decisionRecord?.approvedAt) blockers.push(blocker(
    'READINESS_DECISION_PROVENANCE_MISMATCH',
    'governingEquation',
    'The readiness contract and decision record use different approval provenance.',
  ));
  if (configured?.scalarBaselineRetained !== true) blockers.push(blocker(
    'SCALAR_BASELINE_NOT_RETAINED',
    'governingEquation.scalarBaselineRetained',
    'The scalar conservative skeleton must remain available as a diagnostic baseline.',
  ));

  return Object.freeze({
    version: STAGE16_PHYSICAL_VALIDATION_GATE_VERSION,
    ready: blockers.length === 0,
    blockerCount: blockers.length,
    blockers: Object.freeze(blockers),
    selectedEquation: packet?.currentSelection ?? null,
    decisionOption: decisionRecord?.optionId ?? null,
    approvedBy: decisionRecord?.approvedBy ?? null,
    approvedAt: decisionRecord?.approvedAt ?? null,
  });
}

export function stage16PhysicalValidationGateReport({
  decisionInput,
  decisionRecord,
  readinessConfig,
}) {
  validatePhysicalReadinessConfiguration(readinessConfig);
  const equationSelection = governingEquationSelectionReport({
    decisionInput,
    decisionRecord,
    readinessConfig,
  });
  const physicalInputs = physicalReadinessReport(readinessConfig);
  const blockers = [
    ...equationSelection.blockers,
    ...physicalInputs.blockers,
  ];
  return Object.freeze({
    version: STAGE16_PHYSICAL_VALIDATION_GATE_VERSION,
    ready: equationSelection.ready && physicalInputs.ready,
    blockerCount: blockers.length,
    blockers: Object.freeze(blockers),
    equationSelection,
    physicalInputs,
    safeguards: Object.freeze({
      approvedWaterGeometryChanged: readinessConfig.safeguards.approvedWaterGeometryChanged,
      legacyFlowCalculationChanged: readinessConfig.safeguards.legacyFlowCalculationChanged,
      publicSimulatorConnected: readinessConfig.safeguards.publicSimulatorConnected,
      calibrationPerformed: readinessConfig.safeguards.calibrationPerformed,
    }),
  });
}

export function assertStage16PhysicalValidationReady(inputs) {
  if (!inputs || typeof inputs !== 'object' || !VERIFIED_GATE_INPUTS.has(inputs)) {
    throw new Error(
      '[stage16-physical-validation-gate] assertion requires deeply frozen inputs from the secure loader',
    );
  }
  const report = stage16PhysicalValidationGateReport(inputs);
  if (!report.ready) {
    throw new Error(
      `[stage16-physical-validation-gate] not ready: ${report.blockers.map(item => item.code).join(', ')}`,
    );
  }
  assertPhysicalSimulationReady(inputs.readinessConfig);
  return report;
}

export async function loadStage16PhysicalValidationGateInputs({
  decisionInputPath = 'config/stage16_governing_equation_decision_inputs.json',
  readinessConfigPath = 'config/onga_stage16_physical_readiness_v2.json',
} = {}) {
  const decisionInput = JSON.parse(await fs.readFile(decisionInputPath, 'utf8'));
  if (!nonempty(decisionInput.decisionRecord)) {
    throw new Error('[stage16-physical-validation-gate] decision input does not link a decision record');
  }
  const decisionRecordPath = path.resolve(decisionInput.decisionRecord);
  const [decisionRecord, readinessConfig] = await Promise.all([
    fs.readFile(decisionRecordPath, 'utf8').then(JSON.parse),
    loadPhysicalReadinessConfiguration(readinessConfigPath),
  ]);
  const inputs = deepFreeze({ decisionInput, decisionRecord, readinessConfig });
  VERIFIED_GATE_INPUTS.add(inputs);
  return inputs;
}
