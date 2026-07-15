import { readFile } from 'node:fs/promises';
import { performance } from 'node:perf_hooks';
import { createHash } from 'node:crypto';
import { decodeStage20ResponsePack } from '../onga_stage20_response_pack.mjs';
import { stage20SnapshotViews, synthesiseStage20HourlyFields } from '../onga_stage20_hybrid_solver.mjs';

function requireValue(condition, message) {
  if (!condition) throw new Error(message);
}

function sha256(buffer) {
  return createHash('sha256').update(new Uint8Array(buffer)).digest('hex');
}

const manifest = JSON.parse(await readFile('public/data/onga/stage20/response-pack-synthetic-v1.json', 'utf8'));
const binary = await readFile('public/data/onga/stage20/response-pack-synthetic-v1.bin');
const inputs = JSON.parse(await readFile('public/data/onga/stage20/hybrid-synthetic-input-v1.json', 'utf8'));
const buffer = binary.buffer.slice(binary.byteOffset, binary.byteOffset + binary.byteLength);
requireValue(sha256(buffer) === manifest.binary.sha256, 'response-pack digest mismatch');
const pack = decodeStage20ResponsePack(manifest, buffer);
const started = performance.now();
const first = synthesiseStage20HourlyFields(pack, inputs);
const firstFinished = performance.now();
const second = synthesiseStage20HourlyFields(pack, inputs);
const secondFinished = performance.now();
const firstDigest = sha256(first.fields.buffer);
const secondDigest = sha256(second.fields.buffer);
requireValue(firstDigest === secondDigest, 'synthesis is not deterministic');
requireValue(first.snapshotCount === 37, 'snapshot count changed');
requireValue(first.hours[0] === -12 && first.hours.at(-1) === 24, 'hour range changed');
requireValue(first.cellCount === 50339, 'cell count changed');
requireValue(first.fields.byteLength === 37 * 3 * 50339 * 4, 'output byte length changed');
requireValue(first.diagnostics.nonFiniteValueCount === 0, 'non-finite synthetic output');
const present = stage20SnapshotViews(first, 12);
requireValue(present.hour === 0 && present.depthM.length === 50339, 'present snapshot view is invalid');

let envelopeRejected = false;
try {
  const invalid = structuredClone(inputs);
  invalid.barrageOpeningFraction[0] = 1.1;
  synthesiseStage20HourlyFields(pack, invalid);
} catch {
  envelopeRejected = true;
}
requireValue(envelopeRejected, 'out-of-envelope input was accepted');

console.log(JSON.stringify({
  schema: 'onga-stage20-hybrid-browser-validation-v1',
  status: 'passed',
  responsePackSha256: manifest.binary.sha256,
  outputSha256: firstDigest,
  responsePackBytes: binary.byteLength,
  outputBytes: first.fields.byteLength,
  snapshotCount: first.snapshotCount,
  hourRange: [first.hours[0], first.hours.at(-1)],
  intervalHours: 1,
  cellCount: first.cellCount,
  diagnostics: first.diagnostics,
  timingsMs: {
    firstSynthesis: firstFinished - started,
    repeatSynthesis: secondFinished - firstFinished,
  },
  checks: {
    deterministic: true,
    outOfEnvelopeRejected: envelopeRejected,
    presentSnapshotAccessible: true,
  },
  safeguards: {
    syntheticResponsePackOnly: true,
    physicalSolverExecuted: false,
    publicSimulatorConnected: false,
  },
}, null, 2));
