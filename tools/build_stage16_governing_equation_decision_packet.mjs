import fs from 'node:fs/promises';
import {
  buildGoverningEquationDecisionPacket,
} from '../onga_stage16_governing_equation_decision.mjs';

const inputPath = process.argv[2] || 'config/stage16_governing_equation_decision_inputs.json';
const outputPath = process.argv[3] || 'stage16-governing-equation-decision-packet.json';
const input = JSON.parse(await fs.readFile(inputPath, 'utf8'));
if (input.schema !== 'onga-stage16-governing-equation-decision-input-v1') {
  throw new Error(`unexpected decision input schema: ${input.schema}`);
}
const packet = buildGoverningEquationDecisionPacket({
  objectiveWeights: input.objectiveWeights,
  evidence: input.evidence,
  currentSelection: input.currentSelection,
});
const output = {
  ...packet,
  sourceInput: inputPath,
  notes: input.notes ?? [],
};
await fs.writeFile(outputPath, `${JSON.stringify(output, null, 2)}\n`, 'utf8');
console.log(JSON.stringify({
  status: 'generated',
  recommendation: packet.recommendation,
  selectionApproved: packet.selectionApproved,
  humanDecisionRequired: packet.humanDecisionRequired,
  physicalValidationReady: packet.physicalValidationReady,
  dataGaps: packet.dataGaps,
  outputPath,
}, null, 2));
