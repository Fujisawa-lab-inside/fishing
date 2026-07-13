function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const EXPECTED_AUTHORIZATION = Object.freeze({
  approvedBy: 'Ryusuke Fujisawa',
  approvedDate: '2026-07-13',
  sourceStatement: '作業を開始してください．',
  sourcePilot: Object.freeze({
    mergeCommit: 'e22bc2e81ebfb968fc535915e817f268229513a3',
    headCommit: '958964f41bc3eed3a5e739a693173f1ca4b2197f',
    workflowRunId: 29229011438,
    tier: 'pilot',
    completedCaseCount: 16,
    passed: true,
  }),
  meshArrayHashes: Object.freeze({
    vertices: '719e1206939dee4fdf45fa8bedba13c6608fdff46b885811ba8deb886b9b33c0',
    triangles: '104b03f5174b5a14a91aca51ee2fbb3cfa32b64679486781413dea930f57141d',
    segments: '07689a5cbe85a23248ca49f68983570249967de390e31cacb5b310731a371101',
    segment_markers: '9b5be414b15f71a19825d5f4a50e255e491d9de4f9ceae6d7020b0c9318701e4',
  }),
  meshSummarySha256: 'f44b1317f469e34227e83cb0910db75d75404098f0927d93a8e3316ae92060f8',
  meshProvenance: Object.freeze({
    sourceWorkflowRunId: 29191537971,
    sourceCommit: '43d94c8e26c0cb86ec33166fa28628f8cff664fd',
    sourceArtifactName: 'stage16-metric-fv-mesh',
  }),
  ensemble: Object.freeze({
    schema: 'onga-stage18-inference-ensemble-v1',
    generatedFrom: 'onga-stage17-inferred-physical-prior-v1',
    seed: 20260713,
    caseCount: 64,
    sha256: '0a926fa20d6260a6cdb113b2a7d5be6807ca87f33350ce82be32ef9e13023ef2',
  }),
  acceptance: Object.freeze({
    completionFractionMin: 1,
    nanCountMax: 0,
    negativeDepthCountMax: 0,
    maxCflMax: 0.95,
    maxAbsoluteMassBalanceErrorMax: 1e-8,
    maxWallSeconds: 3600,
    maxResidentMemoryMiB: 8192,
  }),
});

const EXPECTED_ACTIVE_PARAMETERS = Object.freeze([
  'bathymetry.mainstemMeanDepthM',
  'roughness.manningOpenChannel',
  'boundaries.M.phaseShiftMinutes',
  'fishway.mode',
  'fishway.effectiveDischargeCoefficient',
  'fishway.effectiveAreaM2',
  'barrage.scenario.closedVersusOpen',
]);

const EXPECTED_PACKAGE_ARRAYS = Object.freeze({
  vertex_local_mm: { shape: [28560, 2], dtype: 'int32', sha256: '7b65e2a63a65da840b7318b27741412271a37eabc865ca1ee885ff20e41e2e4b' },
  vertex_image_millipixel: { shape: [28560, 2], dtype: 'int32', sha256: '514175658451ec82d8eb3449184d90ad446e24938dbc411811502674edbde779' },
  triangles: { shape: [50333, 3], dtype: 'int32', sha256: '104b03f5174b5a14a91aca51ee2fbb3cfa32b64679486781413dea930f57141d' },
  internal_face_vertices: { shape: [72107, 2], dtype: 'int32', sha256: '123eda613dc6eed147d48238634cdc72b41527bc5b0a2b81db6e779cec044449' },
  internal_face_cells: { shape: [72107, 2], dtype: 'int32', sha256: '8b7ad394cff17129536af5e836f08c2564de3ae8dfa6136f094f0589850700b5' },
  boundary_face_vertices: { shape: [6785, 2], dtype: 'int32', sha256: 'a6b5f9c550a3117d2ada3ce99856fc6823378207a4328c6f7305712470436e15' },
  boundary_face_cell: { shape: [6785], dtype: 'int32', sha256: 'fc4687f57c34e029ddb82d8162702de1ef5f18320f61f61eaa5b68dc13a84f66' },
  boundary_face_tag: { shape: [6785], dtype: 'uint8', sha256: 'c0047c37c44d7abb4f562a4963bcf1e49417e512827bf6c80e71f1c1ccc50698' },
  barrage_face_ids: { shape: [68], dtype: 'int32', sha256: 'e4431bc01ec36c5b272e0a074e385c3638e401dfcc808d52c3eabbe4be0a9c86' },
  barrage_gate_id: { shape: [68], dtype: 'uint8', sha256: '2e4f9937653b020f6326cab02f0c7321676686f16793d391f2674e19ca7b5d1b' },
  fishway_cells: { shape: [2], dtype: 'int32', sha256: '1e1aa278d790d6d33bb4e708879b8fec5bf3f4661141f5366bc2b83e18a7bd6d' },
  fishway_components: { shape: [2], dtype: 'int32', sha256: '01acecb507abfe1a354aa8064f4af5d3f1acd019e37db3c11c97523b71c76e9d' },
});

const EXPECTED_INACTIVE_PARAMETERS = Object.freeze([
  'bathymetry.crossSectionShape',
  'bathymetry.tributaryMeanDepthM',
  'bathymetry.thalwegOffsetFractionOfLocalWidth',
  'bathymetry.longitudinalSmoothingLengthM',
  'roughness.shallowMarginMultiplier',
  'roughness.structureVicinityMultiplier',
  'boundaries.M.amplitudeMultiplier',
  'boundaries.N.dischargeM3S',
  'boundaries.O.dischargeM3S',
  'boundaries.G.dischargeM3S',
  'barrage.effectiveDischargeCoefficient',
  'barrage.gateOpeningUncertaintyFraction',
  'barrage.scenario.openingMagnitude',
]);

const PROTECTED_PATHS = Object.freeze([
  'index.html',
  'pc_full.html',
  'mobile_lite.html',
  'app.js',
  'assets/app.js',
  'OngaEstuarySimulator_Browser_Service_v4_6_PCFull_ConfluenceTracer.html',
  'OngaEstuarySimulator_Browser_Service_v4_6_MobileLite_ConfluenceTracer.html',
]);

function equalJson(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function finiteNonnegative(value, label) {
  assert(Number.isFinite(value) && value >= 0, `${label} must be finite and nonnegative`);
}

function assertClose(actual, expected, label) {
  finiteNonnegative(actual, label);
  finiteNonnegative(expected, `${label} diagnostic aggregate`);
  const scale = Math.max(1, Math.abs(actual), Math.abs(expected));
  const tolerance = 8 * Number.EPSILON * scale;
  assert(Math.abs(actual - expected) <= tolerance, `${label} does not match case diagnostics`);
}

function sha256(value, label) {
  assert(/^[a-f0-9]{64}$/.test(value || ''), `${label} SHA-256 required`);
}

function validateProtectedHashes(report) {
  const before = report.protectedSurfaceHashesBefore;
  const after = report.protectedSurfaceHashesAfter;
  assert(before && after, 'protected surface hash maps required');
  assert(equalJson(Object.keys(before), PROTECTED_PATHS), 'protected surface paths changed');
  assert(equalJson(Object.keys(after), PROTECTED_PATHS), 'protected surface paths changed after run');
  for (const path of PROTECTED_PATHS) {
    sha256(before[path], `${path} before`);
    sha256(after[path], `${path} after`);
    assert(before[path] === after[path], `${path} changed during run`);
  }
}

export function validateFull64Authorization(config) {
  assert(config?.schema === 'onga-stage18-full64-run-authorization-v1', 'unsupported authorization schema');
  assert(config.authorized === true, 'full64 run is not authorized');
  assert(config.scope === 'exactly_64_provisional_inference_cases_for_runtime_and_numerical_stability_evidence', 'authorization scope changed');
  assert(config.approvedBy === EXPECTED_AUTHORIZATION.approvedBy, 'authorization approver changed');
  assert(config.approvedDate === EXPECTED_AUTHORIZATION.approvedDate, 'authorization date changed');
  assert(config.sourceStatement === EXPECTED_AUTHORIZATION.sourceStatement, 'authorization source statement changed');
  assert(equalJson(config.sourcePilot, EXPECTED_AUTHORIZATION.sourcePilot), 'pilot authorization provenance changed');
  assert(config.geometry?.approvedWaterPixelCount === 679791, 'approved water geometry changed');
  assert(config.geometry?.metricMeshCellCount === 50333, 'metric mesh changed');
  assert(config.geometry?.frozen === true, 'geometry must remain frozen');
  assert(config.meshExpected?.sourceWorkflowRunId === EXPECTED_AUTHORIZATION.meshProvenance.sourceWorkflowRunId, 'mesh workflow provenance changed');
  assert(config.meshExpected?.sourceCommit === EXPECTED_AUTHORIZATION.meshProvenance.sourceCommit, 'mesh source commit changed');
  assert(config.meshExpected?.sourceArtifactName === EXPECTED_AUTHORIZATION.meshProvenance.sourceArtifactName, 'mesh artifact provenance changed');
  assert(config.meshExpected?.vertices === 28560, 'mesh vertex count changed');
  assert(config.meshExpected?.cells === 50333, 'mesh cell count changed');
  assert(config.meshExpected?.internalFaces === 72107, 'internal face count changed');
  assert(config.meshExpected?.boundaryFaces === 6785, 'boundary face count changed');
  assert(config.meshExpected?.barrageFaces === 68, 'barrage face count changed');
  assert(config.meshExpected?.summarySha256 === EXPECTED_AUTHORIZATION.meshSummarySha256, 'mesh summary digest changed');
  assert(equalJson(config.meshExpected?.meshArrayHashes, EXPECTED_AUTHORIZATION.meshArrayHashes), 'authorized mesh digests changed');
  assert(equalJson(config.meshExpected?.packageArrays, EXPECTED_PACKAGE_ARRAYS), 'authorized metric mesh package changed');
  assert(equalJson(config.ensembleExpected, EXPECTED_AUTHORIZATION.ensemble), 'authorized ensemble identity changed');
  assert(config.run?.caseCount === 64, 'exactly 64 cases required');
  assert(config.run?.ensembleSeed === 20260713, 'ensemble seed changed');
  assert(config.run?.maxStepsPerCase === 500, 'step limit changed');
  assert(config.run?.comparisonBasis === 'equal_step_count_not_equal_simulated_time', 'comparison basis must remain explicit');
  assert(equalJson(config.acceptance, EXPECTED_AUTHORIZATION.acceptance), 'acceptance thresholds changed');
  assert(equalJson(config.parameterCoverage?.active, EXPECTED_ACTIVE_PARAMETERS), 'active parameter coverage changed');
  assert(equalJson(config.parameterCoverage?.inactive, EXPECTED_INACTIVE_PARAMETERS), 'inactive parameter coverage changed');
  const safeguards = config.safeguards;
  for (const key of [
    'inferredParametersAreObservations', 'physicalValidationClaimAllowed',
    'publicSimulatorConnectionAllowed', 'legacyFlowCalculationMayChange',
    'failedCasesMayBeImputed', 'sensitivityClaimAllowed', 'automaticAdditionalRunsAllowed',
  ]) assert(safeguards?.[key] === false, `${key} must remain false`);
  return true;
}

export function evaluateFull64Result(config, report) {
  validateFull64Authorization(config);
  assert(report?.schema === 'onga-stage18-full64-run-report-v1', 'unsupported full64 report');
  assert(report.classification === 'provisional_full64_runtime_and_numerical_stability_evidence_only', 'report classification changed');
  assert(report.geometry?.approvedWaterPixelCount === config.geometry.approvedWaterPixelCount, 'water geometry mismatch');
  assert(report.geometry?.metricMeshCellCount === config.geometry.metricMeshCellCount, 'mesh mismatch');
  assert(report.geometry?.frozen === true, 'report geometry is not frozen');
  assert(report.ensembleSeed === config.run.ensembleSeed, 'ensemble seed mismatch');
  assert(report.requestedCaseCount === 64, 'requested case count mismatch');
  assert(Array.isArray(report.attemptedCaseIds) && report.attemptedCaseIds.length === 64, '64 attempted case IDs required');
  assert(new Set(report.attemptedCaseIds).size === 64, 'attempted case IDs must be unique');
  const expectedIds = Array.from({ length: 64 }, (_, index) => `stage18-${String(index + 1).padStart(4, '0')}`);
  assert(JSON.stringify(report.attemptedCaseIds) === JSON.stringify(expectedIds), 'attempted case IDs mismatch');
  assert(Number.isInteger(report.completedCaseCount) && report.completedCaseCount >= 0, 'invalid completed case count');
  assert(Number.isInteger(report.failedCaseCount) && report.failedCaseCount >= 0, 'invalid failed case count');
  assert(report.completedCaseCount + report.failedCaseCount === 64, 'case accounting mismatch');
  assert(Array.isArray(report.failures) && report.failures.length === report.failedCaseCount, 'failure list mismatch');
  const failureIds = report.failures.map(item => item.caseId);
  assert(new Set(failureIds).size === failureIds.length, 'duplicate failure case ID');
  for (const failure of report.failures) {
    assert(report.attemptedCaseIds.includes(failure.caseId), `unknown failure case ${failure.caseId}`);
    assert(typeof failure.reason === 'string' && failure.reason.length > 0, 'failure reason required');
  }
  assert(Array.isArray(report.caseDiagnostics) && report.caseDiagnostics.length === 64, '64 case diagnostics required');
  let completedDiagnostics = 0;
  let caseWallSecondsTotal = 0;
  const completedMaxCfl = [];
  const completedMassBalanceError = [];
  const completedSimulatedTime = [];
  for (let index = 0; index < report.caseDiagnostics.length; index += 1) {
    const diagnostic = report.caseDiagnostics[index];
    const caseId = expectedIds[index];
    assert(diagnostic?.caseId === caseId, `case diagnostic order mismatch at ${caseId}`);
    finiteNonnegative(diagnostic.wallSeconds, `${caseId}.wallSeconds`);
    caseWallSecondsTotal += diagnostic.wallSeconds;
    if (diagnostic.status === 'completed') {
      completedDiagnostics += 1;
      assert(diagnostic.stepsCompleted === config.run.maxStepsPerCase, `${caseId} step count mismatch`);
      for (const key of [
        'simulatedTimeSeconds', 'minimumTimeStepSeconds', 'maximumTimeStepSeconds',
        'massBalanceError', 'maxCfl', 'minimumDepthM',
      ]) finiteNonnegative(diagnostic[key], `${caseId}.${key}`);
      assert(diagnostic.simulatedTimeSeconds > 0, `${caseId} simulated time must be positive`);
      assert(diagnostic.minimumTimeStepSeconds > 0, `${caseId} minimum time step must be positive`);
      assert(diagnostic.maximumTimeStepSeconds >= diagnostic.minimumTimeStepSeconds, `${caseId} time-step range invalid`);
      assert(!failureIds.includes(caseId), `${caseId} is both completed and failed`);
      completedMaxCfl.push(diagnostic.maxCfl);
      completedMassBalanceError.push(Math.abs(diagnostic.massBalanceError));
      completedSimulatedTime.push(diagnostic.simulatedTimeSeconds);
    } else {
      assert(diagnostic.status === 'failed', `${caseId} status invalid`);
      const failure = report.failures.find(item => item.caseId === caseId);
      assert(failure && diagnostic.reason === failure.reason, `${caseId} failure diagnostic mismatch`);
    }
  }
  assert(completedDiagnostics === report.completedCaseCount, 'completed diagnostic count mismatch');
  for (const key of [
    'wallSeconds', 'peakResidentMemoryMiB', 'maxCfl', 'maxAbsoluteMassBalanceError',
    'minimumDepthM', 'minimumSimulatedTimeSeconds', 'maximumSimulatedTimeSeconds',
  ]) finiteNonnegative(report[key], key);
  for (const key of ['nanCount', 'negativeDepthCount']) {
    assert(Number.isInteger(report[key]) && report[key] >= 0, `${key} must be a nonnegative integer`);
  }
  assertClose(report.caseWallSecondsTotal, caseWallSecondsTotal, 'caseWallSecondsTotal');
  assert(
    report.wallSeconds + 8 * Number.EPSILON * Math.max(1, report.wallSeconds, report.caseWallSecondsTotal)
      >= report.caseWallSecondsTotal,
    'wallSeconds must include total case runtime',
  );
  if (completedDiagnostics > 0) {
    assertClose(report.maxCfl, Math.max(...completedMaxCfl), 'maxCfl');
    assertClose(
      report.maxAbsoluteMassBalanceError,
      Math.max(...completedMassBalanceError),
      'maxAbsoluteMassBalanceError',
    );
    assertClose(
      report.minimumSimulatedTimeSeconds,
      Math.min(...completedSimulatedTime),
      'minimumSimulatedTimeSeconds',
    );
    assertClose(
      report.maximumSimulatedTimeSeconds,
      Math.max(...completedSimulatedTime),
      'maximumSimulatedTimeSeconds',
    );
  }
  assert(report.minimumSimulatedTimeSeconds <= report.maximumSimulatedTimeSeconds, 'simulated-time range invalid');
  assert(report.comparisonBasis === config.run.comparisonBasis, 'comparison basis mismatch');
  assert(equalJson(report.parameterCoverage, config.parameterCoverage), 'reported parameter coverage changed');
  assert(equalJson(report.safeguards, config.safeguards), 'reported safeguards changed');
  for (const key of ['meshSha256', 'meshSummarySha256', 'ensembleSha256', 'authorizationSha256']) {
    sha256(report.inputDigests?.[key], `inputDigests.${key}`);
  }
  assert(report.inputDigests.meshSummarySha256 === config.meshExpected.summarySha256, 'mesh summary digest mismatch');
  assert(report.inputDigests.ensembleSha256 === config.ensembleExpected.sha256, 'ensemble digest mismatch');
  assert(report.meshSummaryVerified === true, 'frozen mesh summary was not verified');
  assert(report.protectedSurfaceHashesUnchanged === true, 'public or legacy surface changed');
  validateProtectedHashes(report);
  if (report.completedCaseCount === 64) {
    assert(report.fieldArtifact?.shape?.caseCount === 64, 'field artifact case count mismatch');
    assert(report.fieldArtifact?.shape?.cellCount === 50333, 'field artifact cell count mismatch');
    assert(report.fieldArtifact?.dtype === 'float64', 'field artifact dtype mismatch');
    assert(typeof report.fieldArtifact?.path === 'string' && report.fieldArtifact.path.endsWith('.npz'), 'field artifact path required');
    sha256(report.fieldArtifact?.sha256, 'field artifact');
  } else {
    assert(report.fieldArtifact === null, 'partial run must not publish a field artifact');
  }

  const completionFraction = report.completedCaseCount / 64;
  const checks = {
    completionFraction: completionFraction >= config.acceptance.completionFractionMin,
    nanCount: report.nanCount <= config.acceptance.nanCountMax,
    negativeDepthCount: report.negativeDepthCount <= config.acceptance.negativeDepthCountMax,
    maxCfl: report.maxCfl <= config.acceptance.maxCflMax,
    massBalance: Math.abs(report.maxAbsoluteMassBalanceError) <= config.acceptance.maxAbsoluteMassBalanceErrorMax,
    wallTime: report.wallSeconds <= config.acceptance.maxWallSeconds,
    memory: report.peakResidentMemoryMiB <= config.acceptance.maxResidentMemoryMiB,
    minimumDepth: report.minimumDepthM >= 0,
    protectedSurfaces: report.protectedSurfaceHashesUnchanged,
  };
  const passed = Object.values(checks).every(Boolean);
  return {
    schema: 'onga-stage18-full64-evaluation-v1',
    passed,
    checks,
    completionFraction,
    offlineStepMatchedStatisticsAllowed: false,
    sensitivityClaimAllowed: false,
    physicalValidationClaimAllowed: false,
    publicSimulatorConnectionAllowed: false,
    automaticAdditionalRunAuthorized: false,
    classification: 'provisional_full64_runtime_and_numerical_stability_evidence_only',
  };
}
