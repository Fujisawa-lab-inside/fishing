import crypto from 'node:crypto';
import fs from 'node:fs/promises';

import { evaluateFull64Result, validateFull64Authorization } from '../onga_stage18_full64_evaluator.mjs';
import { generateInferenceEnsemble } from '../onga_stage18_inference_ensemble.mjs';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function digest(text) {
  return crypto.createHash('sha256').update(text).digest('hex');
}

function clone(value) {
  return structuredClone(value);
}

const authorizationPath = 'config/stage18_full64_run_authorization_v1.json';
const authorizationText = await fs.readFile(authorizationPath, 'utf8');
const authorization = JSON.parse(authorizationText);
assert(validateFull64Authorization(authorization), 'authorization validation failed');

const prior = JSON.parse(await fs.readFile('config/stage17_inferred_physical_prior_v1.json', 'utf8'));
const generatedEnsemble = generateInferenceEnsemble(prior, { count: 64, seed: 20260713 });
const generatedEnsembleText = `${JSON.stringify(generatedEnsemble, null, 2)}\n`;
assert(digest(generatedEnsembleText) === authorization.ensembleExpected.sha256, 'canonical ensemble digest changed');

const attemptedCaseIds = Array.from({ length: 64 }, (_, index) => `stage18-${String(index + 1).padStart(4, '0')}`);
const protectedPaths = [
  'index.html',
  'pc_full.html',
  'mobile_lite.html',
  'app.js',
  'assets/app.js',
  'OngaEstuarySimulator_Browser_Service_v4_6_PCFull_ConfluenceTracer.html',
  'OngaEstuarySimulator_Browser_Service_v4_6_MobileLite_ConfluenceTracer.html',
];
const protectedHashes = Object.fromEntries(protectedPaths.map(path => [path, digest(path)]));

function completedDiagnostic(caseId, index) {
  return {
    caseId,
    status: 'completed',
    wallSeconds: 1,
    stepsCompleted: 500,
    simulatedTimeSeconds: 10 + (10 * index) / 63,
    minimumTimeStepSeconds: 0.01,
    maximumTimeStepSeconds: 0.04,
    massBalanceError: 1e-12,
    maxCfl: 0.12,
    minimumDepthM: 0.1,
  };
}

function makeReport(overrides = {}) {
  return {
    schema: 'onga-stage18-full64-run-report-v1',
    classification: 'provisional_full64_runtime_and_numerical_stability_evidence_only',
    geometry: clone(authorization.geometry),
    ensembleSeed: 20260713,
    requestedCaseCount: 64,
    attemptedCaseIds,
    completedCaseCount: 64,
    failedCaseCount: 0,
    failures: [],
    caseDiagnostics: attemptedCaseIds.map(completedDiagnostic),
    wallSeconds: 600,
    caseWallSecondsTotal: 64,
    peakResidentMemoryMiB: 512,
    maxCfl: 0.12,
    maxAbsoluteMassBalanceError: 1e-12,
    minimumDepthM: 0.1,
    minimumSimulatedTimeSeconds: 10,
    maximumSimulatedTimeSeconds: 20,
    nanCount: 0,
    negativeDepthCount: 0,
    comparisonBasis: authorization.run.comparisonBasis,
    parameterCoverage: clone(authorization.parameterCoverage),
    meshSummaryVerified: true,
    protectedSurfaceHashesBefore: { ...protectedHashes },
    protectedSurfaceHashesAfter: { ...protectedHashes },
    protectedSurfaceHashesUnchanged: true,
    fieldArtifact: {
      path: 'stage18-full64/full64-fields.npz',
      shape: { caseCount: 64, cellCount: 50333 },
      dtype: 'float64',
      sha256: 'a'.repeat(64),
    },
    inputDigests: {
      meshSha256: 'b'.repeat(64),
      meshSummarySha256: authorization.meshExpected.summarySha256,
      ensembleSha256: authorization.ensembleExpected.sha256,
      authorizationSha256: digest(authorizationText),
    },
    safeguards: clone(authorization.safeguards),
    ...overrides,
  };
}

const validReport = makeReport();
const passing = evaluateFull64Result(authorization, validReport);
assert(passing.passed, 'valid full64 report failed');
assert(passing.offlineStepMatchedStatisticsAllowed === false, 'pure report evaluation must not authorize offline statistics');
assert(passing.sensitivityClaimAllowed === false, 'sensitivity claim must remain disabled');
assert(passing.physicalValidationClaimAllowed === false, 'physical validation claim must remain disabled');
assert(passing.publicSimulatorConnectionAllowed === false, 'public connection must remain disabled');

for (const [label, mutate] of [
  ['nan', report => { report.nanCount = 1; }],
  ['negative depth', report => { report.negativeDepthCount = 1; }],
  ['cfl', report => { report.maxCfl = 1; report.caseDiagnostics[0].maxCfl = 1; }],
  ['mass balance', report => {
    report.maxAbsoluteMassBalanceError = 1e-6;
    report.caseDiagnostics[0].massBalanceError = 1e-6;
  }],
  ['wall time', report => { report.wallSeconds = 3601; }],
  ['memory', report => { report.peakResidentMemoryMiB = 8193; }],
]) {
  const thresholdReport = makeReport();
  mutate(thresholdReport);
  const evaluation = evaluateFull64Result(authorization, thresholdReport);
  assert(!evaluation.passed, `${label} report passed`);
}

const failedCaseId = attemptedCaseIds[63];
const failedDiagnostics = attemptedCaseIds.map(completedDiagnostic);
failedDiagnostics[63] = { caseId: failedCaseId, status: 'failed', wallSeconds: 1, reason: 'fixture failure' };
const incomplete = evaluateFull64Result(authorization, makeReport({
  completedCaseCount: 63,
  failedCaseCount: 1,
  failures: [{ caseId: failedCaseId, reason: 'fixture failure' }],
  caseDiagnostics: failedDiagnostics,
  maximumSimulatedTimeSeconds: failedDiagnostics[62].simulatedTimeSeconds,
  fieldArtifact: null,
}));
assert(!incomplete.passed, 'incomplete report passed');

let malformedRejected = 0;
for (const mutate of [
  report => { report.attemptedCaseIds = report.attemptedCaseIds.slice(0, 63); },
  report => { report.caseDiagnostics[0].stepsCompleted = 499; },
  report => { report.caseDiagnostics[0].simulatedTimeSeconds = 0; },
  report => { report.caseDiagnostics[0].maxCfl = 10; },
  report => { report.caseDiagnostics[0].massBalanceError = 0.01; },
  report => { report.caseDiagnostics[0].simulatedTimeSeconds = 9; },
  report => { report.caseWallSecondsTotal = 63; },
  report => { report.wallSeconds = 63; },
  report => { report.fieldArtifact.sha256 = 'bad'; },
  report => { report.inputDigests.ensembleSha256 = 'c'.repeat(64); },
  report => { report.protectedSurfaceHashesAfter['index.html'] = 'd'.repeat(64); },
  report => { report.parameterCoverage.active = []; },
  report => { report.meshSummaryVerified = false; },
]) {
  const malformed = makeReport();
  mutate(malformed);
  try {
    evaluateFull64Result(authorization, malformed);
  } catch {
    malformedRejected += 1;
  }
}
assert(malformedRejected === 13, 'malformed full64 reports were not all rejected');

let authorizationRejected = 0;
for (const mutate of [
  config => { config.approvedBy = 'Someone Else'; },
  config => { config.sourcePilot.headCommit = '0'.repeat(40); },
  config => { config.meshExpected.sourceWorkflowRunId = 1; },
  config => { config.meshExpected.meshArrayHashes.vertices = '0'.repeat(64); },
  config => { config.meshExpected.packageArrays.vertex_local_mm.sha256 = '0'.repeat(64); },
  config => { config.meshExpected.summarySha256 = '0'.repeat(64); },
  config => { config.ensembleExpected.sha256 = '0'.repeat(64); },
  config => { config.acceptance.maxCflMax = 1; },
  config => { config.parameterCoverage.inactive = []; },
  config => { config.safeguards.automaticAdditionalRunsAllowed = true; },
]) {
  const malformed = clone(authorization);
  mutate(malformed);
  try {
    validateFull64Authorization(malformed);
  } catch {
    authorizationRejected += 1;
  }
}
assert(authorizationRejected === 10, 'authorization mutations were not all rejected');

const report = {
  schema: 'onga-stage18-full64-validation-v1',
  status: 'passed',
  verified: [
    'exact user authorization identity and source statement',
    'passing pilot PR, head commit, merge commit, and workflow provenance',
    'frozen 679791-pixel and 50333-cell geometry with exact digests',
    'deterministic 64-case ensemble content digest',
    'canonical attempted-case and 500-step diagnostic accounting',
    'diagnostic-derived runtime and numerical aggregate reconciliation',
    'runtime and numerical acceptance thresholds',
    'protected public and legacy surfaces',
    'field artifact shape, dtype, and digest',
    'pure report evaluation withholds artifact-dependent statistics authorization',
    'step-matched interpretation limit',
    'sensitivity and physical-validation claims disabled',
  ],
};
await fs.writeFile('stage18-full64-validation.json', `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify(report));
