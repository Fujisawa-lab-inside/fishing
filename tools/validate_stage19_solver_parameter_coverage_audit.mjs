import crypto from 'node:crypto';
import fs from 'node:fs/promises';

const auditPath = process.argv[2] || 'config/stage19_solver_parameter_coverage_audit_v1.json';
const outputPath = process.argv[3] || 'stage19-solver-parameter-coverage-audit-validation.json';

function assert(condition, message) {
  if (!condition) throw new Error(`[stage19-coverage-audit] ${message}`);
}

function sha256(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

const audit = JSON.parse(await fs.readFile(auditPath, 'utf8'));
const ensembleText = await fs.readFile(audit.ensemble.path, 'utf8');
const kernelText = await fs.readFile(audit.auditedLegacyKernel.path, 'utf8');
const runnerText = await fs.readFile(audit.auditedLegacyKernel.runnerPath, 'utf8');

assert(audit.schema === 'onga-stage19-solver-parameter-coverage-audit-v1', 'schema mismatch');
assert(audit.status === 'implementation_required_before_stage19_execution_scope', 'status mismatch');
assert(sha256(ensembleText) === audit.ensemble.sha256, 'ensemble digest changed');
assert(sha256(kernelText) === audit.auditedLegacyKernel.sha256, 'legacy kernel digest changed');
assert(sha256(runnerText) === audit.auditedLegacyKernel.runnerSha256, 'legacy runner digest changed');
assert(audit.approvedCaseDimensions === 16 && audit.coverage.length === 16,
  'coverage must enumerate all 16 approved case dimensions');
assert(new Set(audit.coverage.map(item => item.input)).size === 16, 'coverage inputs must be unique');

const statusCounts = Object.fromEntries(
  ['semantically_applied', 'partial_wrong_semantics', 'partial_binary_only', 'not_used']
    .map(status => [status, audit.coverage.filter(item => item.legacyStatus === status).length]),
);
assert(statusCounts.semantically_applied === 1, 'semantic application count changed');
assert(statusCounts.partial_wrong_semantics + statusCounts.partial_binary_only === 6,
  'partial application count changed');
assert(statusCounts.not_used === 9, 'unused input count changed');
assert(audit.summary.semanticallyApplied === 1
  && audit.summary.partialOrWrongSemantics === 6
  && audit.summary.notUsed === 9, 'summary counts do not match coverage');
assert(audit.summary.stage19ExecutionOnLegacyKernelAllowed === false,
  'legacy Stage 19 execution must remain prohibited');

assert(kernelText.includes("state[:, 0] = initial_depth"), 'uniform legacy depth evidence missing');
assert(kernelText.includes("_reflected_state(state[boundary_cells]"), 'reflected boundary evidence missing');
assert(kernelText.includes("active_internal[barrage_face_ids] = opening_fraction > 0"),
  'binary barrage evidence missing');
assert(kernelText.includes("manning = float(case['roughness']['manningOpenChannel'])"),
  'Manning application evidence missing');
for (const forbiddenReference of [
  'tributaryMeanDepthM',
  'amplitudeMultiplier',
  "boundaries']['N",
  "boundaries']['O",
  "boundaries']['G",
  "barrage']['effectiveDischargeCoefficient",
]) {
  assert(!kernelText.includes(forbiddenReference),
    `legacy kernel unexpectedly references ${forbiddenReference}`);
}

for (const key of [
  'legacyKernelModifiedByAudit',
  'physicalValuesAssignedToLegacyKernel',
  'numericalCaseStarted',
  'numericalRunEnabled',
  'executionAuthorizationProvided',
]) {
  assert(audit.safeguards?.[key] === false, `safeguard ${key} changed`);
}

const report = {
  schema: 'onga-stage19-solver-parameter-coverage-audit-validation-v1',
  status: 'passed',
  approvedCaseDimensions: 16,
  statusCounts,
  stage19ExecutionOnLegacyKernelAllowed: false,
  numericalRunEnabled: false,
};
await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
console.log(JSON.stringify(report, null, 2));
