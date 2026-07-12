import fs from 'node:fs/promises';
import path from 'node:path';
import {
  buildGoverningEquationDecisionPacket,
  recordGoverningEquationDecision,
} from '../onga_stage16_governing_equation_decision.mjs';

const inputPath = process.argv[2] || 'config/stage16_governing_equation_decision_inputs.json';
const outputPath = process.argv[3] || 'stage16-governing-equation-decision-packet.json';
const input = JSON.parse(await fs.readFile(inputPath, 'utf8'));
if (input.schema !== 'onga-stage16-governing-equation-decision-input-v1') {
  throw new Error(`unexpected decision input schema: ${input.schema}`);
}

const basePacket = buildGoverningEquationDecisionPacket({
  objectiveWeights: input.objectiveWeights,
  evidence: input.evidence,
  currentSelection: input.currentSelection,
});

let packet = basePacket;
let decisionRecord = null;
if (input.decisionRecord !== null && input.decisionRecord !== undefined) {
  if (typeof input.decisionRecord !== 'string' || !input.decisionRecord.trim()) {
    throw new Error('decisionRecord must be a nonempty repository-relative path');
  }
  const decisionPath = path.resolve(input.decisionRecord);
  decisionRecord = JSON.parse(await fs.readFile(decisionPath, 'utf8'));
  if (decisionRecord.schema !== 'onga-stage16-governing-equation-decision-record-v1') {
    throw new Error(`unexpected decision record schema: ${decisionRecord.schema}`);
  }
  packet = recordGoverningEquationDecision(basePacket, decisionRecord);
  if (decisionRecord.governingEquation !== packet.currentSelection) {
    throw new Error(
      `decision record governing equation mismatch: ${decisionRecord.governingEquation} != ${packet.currentSelection}`,
    );
  }
} else if (input.currentSelection !== null && input.currentSelection !== undefined) {
  throw new Error('currentSelection cannot be asserted without an explicit decisionRecord');
}

const output = {
  ...packet,
  sourceInput: inputPath,
  decisionRecordPath: input.decisionRecord ?? null,
  decisionRecord,
  notes: input.notes ?? [],
};
await fs.writeFile(outputPath, `${JSON.stringify(output, null, 2)}\n`, 'utf8');
console.log(JSON.stringify({
  status: 'generated',
  recommendation: packet.recommendation,
  currentSelection: packet.currentSelection,
  selectionApproved: packet.selectionApproved,
  humanDecisionRequired: packet.humanDecisionRequired,
  physicalValidationReady: packet.physicalValidationReady,
  dataGaps: packet.dataGaps,
  outputPath,
}, null, 2));
