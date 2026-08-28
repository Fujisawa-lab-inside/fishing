export const STAGE20_LOCAL_SIMULATION_SCHEMA =
  'onga-stage20-local-R1C-browser-result-manifest-v1';
const CSRF_HEADER_NAME = 'X-Stage20-CSRF-Token';

let localCsrfToken = null;

const REQUIRED_ARRAYS = Object.freeze([
  'absoluteTimeS',
  'depthM',
  'eastVelocityMPS',
  'northVelocityMPS',
  'capacityFractionByGateId',
  'gateFluxM3SByGateId',
  'upstreamP2HeadM',
  'downstreamP2HeadM',
  'headDifferenceM',
  'fishwayOutflowM3S',
  'fishwayStorageDepthM',
  'storedVolumeM3',
]);

const TYPE_CONSTRUCTORS = Object.freeze({
  float32: Float32Array,
  float64: Float64Array,
  int32: Int32Array,
  uint8: Uint8Array,
});

function assert(condition, message) {
  if (!condition) throw new Error(`[stage20-local-simulation] ${message}`);
}

function bytesToHex(bytes) {
  return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
}

async function sha256ArrayBuffer(payload) {
  return bytesToHex(new Uint8Array(await crypto.subtle.digest('SHA-256', payload)));
}

async function fetchJson(url, signal, fetchImpl) {
  const response = await fetchImpl(url, {
    cache: 'no-store',
    credentials: 'same-origin',
    mode: 'same-origin',
    redirect: 'error',
    signal,
  });
  assert(response.ok, `${url} returned HTTP ${response.status}`);
  return response.json();
}

export async function probeStage20LocalSimulator(options = {}) {
  const fetchImpl = options.fetchImpl || fetch;
  localCsrfToken = null;
  const capabilities = await fetchJson(
    '/api/stage20/local/capabilities',
    options.signal,
    fetchImpl,
  );
  assert(
    capabilities?.schema === 'onga-stage20-local-simulator-capabilities-v1'
      && capabilities?.status === 'READY_FOR_EXPLICIT_LOCAL_RUN'
      && capabilities?.localOnly === true,
    'local simulator capability response changed',
  );
  assert(
    capabilities?.classification?.localRunnerAvailable === true
      && capabilities?.classification?.runtimeInputsVerified === true
      && capabilities?.classification?.solverExecutionPreflightPassed === false
      && capabilities?.classification?.physicalSolverConnected === false
      && capabilities?.classification?.physicalCalibration === false
      && capabilities?.classification?.fieldPrediction === false,
    'local simulator classification changed',
  );
  assert(
    capabilities?.csrfHeaderName === CSRF_HEADER_NAME
      && typeof capabilities?.csrfToken === 'string'
      && /^[A-Za-z0-9_-]{32,}$/.test(capabilities.csrfToken)
      && capabilities?.requestSecurity?.loopbackHostRequired === true
      && capabilities?.requestSecurity?.sameOriginRequired === true
      && capabilities?.requestSecurity?.applicationJsonRequired === true
      && capabilities?.requestSecurity?.perProcessCsrfToken === true,
    'local simulator request security changed',
  );
  assert(
    capabilities?.meshId === 'candidate_C_R1C_exact_confluence_R20_patches'
      && capabilities?.cellCount === 37724
      && capabilities?.fishwayMode === 'always_enabled_C2_1_storage_tau60',
    'local simulator physical binding changed',
  );
  localCsrfToken = capabilities.csrfToken;
  return Object.freeze(capabilities);
}

export async function createStage20LocalSimulationJob(
  gateCapacityFractionById,
  durationS,
  options = {},
) {
  assert(localCsrfToken !== null, 'local simulator security handshake is required');
  const fetchImpl = options.fetchImpl || fetch;
  const response = await fetchImpl('/api/stage20/local/jobs', {
    method: 'POST',
    cache: 'no-store',
    credentials: 'same-origin',
    mode: 'same-origin',
    redirect: 'error',
    signal: options.signal,
    headers: {
      'Content-Type': 'application/json',
      [CSRF_HEADER_NAME]: localCsrfToken,
    },
    body: JSON.stringify({ gateCapacityFractionById, durationS }),
  });
  const payload = await response.json();
  assert(response.ok, payload?.message || `job request returned HTTP ${response.status}`);
  assert(
    payload?.schema === 'onga-stage20-local-simulator-job-v1'
      && typeof payload?.jobId === 'string'
      && payload?.completed === false,
    'local simulation job response changed',
  );
  return payload;
}

export async function fetchStage20LocalSimulationJob(jobId, options = {}) {
  assert(
    /^local-[0-9]{8}T[0-9]{6}-[0-9a-f]{12}$/.test(jobId),
    'local simulation job id is invalid',
  );
  const fetchImpl = options.fetchImpl || fetch;
  const payload = await fetchJson(
    `/api/stage20/local/jobs/${jobId}`,
    options.signal,
    fetchImpl,
  );
  assert(
    payload?.schema === 'onga-stage20-local-simulator-job-v1'
      && payload?.jobId === jobId,
    'local simulation job status changed',
  );
  return payload;
}

export function validateStage20LocalSimulationManifest(manifest, job) {
  assert(
    manifest?.schema === STAGE20_LOCAL_SIMULATION_SCHEMA
      && manifest?.version === 1
      && manifest?.status === 'PASS_LOCAL_UNCALIBRATED_PHYSICS_RESULT',
    'local result manifest identity changed',
  );
  assert(
    manifest?.requestId === job?.jobId
      && job?.status === 'PASS'
      && job?.completed === true
      && job?.resultUsable === true,
    'local result and completed job differ',
  );
  assert(
    manifest?.classification?.localPhysicsRun === true
      && manifest?.classification?.physicalCalibration === false
      && manifest?.classification?.fieldPrediction === false
      && manifest?.classification?.productionResponsePack === false,
    'local result classification changed',
  );
  assert(
    manifest?.mesh?.cellCount === 37724
      && manifest?.mesh?.sha256
        === '7f3e84b73fab3bff1ba4699dbf9b1299159c40e91d042376046a6fe99fc03164'
      && manifest?.mesh?.geometryIncludedInBinary === false,
    'local result mesh binding changed',
  );
  assert(
    Number.isInteger(manifest?.timeline?.snapshotCount)
      && manifest.timeline.snapshotCount >= 2
      && manifest.timeline.snapshotCount <= 61
      && manifest.timeline.absoluteStartS === 0
      && manifest.timeline.absoluteEndS === job.durationS,
    'local result timeline changed',
  );
  assert(
    manifest?.operation?.fishwayAlwaysEnabled === true
      && manifest?.operation?.capacityMeaning
        === 'classification_face_capacity_multiplier_not_measured_gate_lift'
      && Array.isArray(manifest.operation.gateCapacityFractionById)
      && manifest.operation.gateCapacityFractionById.length === 8,
    'local result operation contract changed',
  );
  assert(
    REQUIRED_ARRAYS.every(name => Object.hasOwn(manifest?.arrays || {}, name))
      && Object.keys(manifest.arrays).length === REQUIRED_ARRAYS.length,
    'local result array set changed',
  );
  assert(
    Number.isInteger(manifest?.binary?.byteLength)
      && manifest.binary.byteLength > 0
      && /^[0-9a-f]{64}$/.test(manifest.binary.sha256),
    'local result binary binding changed',
  );
  return manifest;
}

function shapeLength(shape) {
  return shape.reduce((product, value) => product * value, 1);
}

async function parseArrays(manifest, payload) {
  assert(payload instanceof ArrayBuffer, 'local result payload must be an ArrayBuffer');
  assert(payload.byteLength === manifest.binary.byteLength, 'local result byte length changed');
  assert(
    await sha256ArrayBuffer(payload) === manifest.binary.sha256,
    'local result binary identity changed',
  );
  const arrays = {};
  for (const name of REQUIRED_ARRAYS) {
    const descriptor = manifest.arrays[name];
    const Constructor = TYPE_CONSTRUCTORS[descriptor.dtype];
    assert(Constructor, `${name} dtype is unsupported`);
    const count = shapeLength(descriptor.shape);
    assert(
      descriptor.byteLength === count * Constructor.BYTES_PER_ELEMENT,
      `${name} byte length and shape differ`,
    );
    assert(
      descriptor.byteOffset >= 0
        && descriptor.byteOffset + descriptor.byteLength <= payload.byteLength,
      `${name} exceeds the local result binary`,
    );
    const copied = new Uint8Array(
      payload,
      descriptor.byteOffset,
      descriptor.byteLength,
    ).slice();
    assert(
      await sha256ArrayBuffer(copied.buffer) === descriptor.sha256,
      `${name} identity changed`,
    );
    arrays[name] = new Constructor(copied.buffer);
  }
  return Object.freeze(arrays);
}

function diagnostics(arrays) {
  let minimumDepthM = Number.POSITIVE_INFINITY;
  let maximumDepthM = 0;
  let maximumSpeedMPS = 0;
  let nonFiniteValueCount = 0;
  for (let index = 0; index < arrays.depthM.length; index += 1) {
    const depth = arrays.depthM[index];
    const east = arrays.eastVelocityMPS[index];
    const north = arrays.northVelocityMPS[index];
    if (!Number.isFinite(depth) || !Number.isFinite(east) || !Number.isFinite(north)) {
      nonFiniteValueCount += 1;
      continue;
    }
    minimumDepthM = Math.min(minimumDepthM, depth);
    maximumDepthM = Math.max(maximumDepthM, depth);
    maximumSpeedMPS = Math.max(maximumSpeedMPS, Math.hypot(east, north));
  }
  assert(nonFiniteValueCount === 0, 'local result contains non-finite values');
  assert(minimumDepthM >= 0, 'local result contains negative depth');
  return Object.freeze({
    minimumDepthM,
    maximumDepthM,
    maximumSpeedMPS,
    nonFiniteValueCount,
    negativeDepthCount: 0,
  });
}

export function buildStage20LocalSimulationData({
  baseR1CData,
  manifest,
  job,
  arrays,
  loadMilliseconds,
}) {
  assert(
    baseR1CData?.metadata?.dataMode === 'r1c_diagnostic_replay',
    'validated R1C geometry base is unavailable',
  );
  validateStage20LocalSimulationManifest(manifest, job);
  const cellCount = manifest.mesh.cellCount;
  const snapshotCount = manifest.timeline.snapshotCount;
  assert(arrays.depthM.length === snapshotCount * cellCount, 'depth shape changed');
  assert(
    arrays.eastVelocityMPS.length === arrays.depthM.length
      && arrays.northVelocityMPS.length === arrays.depthM.length,
    'velocity shape changed',
  );
  assert(
    arrays.capacityFractionByGateId.length === snapshotCount * 8
      && arrays.gateFluxM3SByGateId.length === snapshotCount * 8,
    'gate result shape changed',
  );
  const snapshot = index => {
    assert(
      Number.isInteger(index) && index >= 0 && index < snapshotCount,
      'local result snapshot index is invalid',
    );
    const start = index * cellCount;
    return Object.freeze({
      index,
      hour: arrays.absoluteTimeS[index] / 3600,
      absoluteTimeS: arrays.absoluteTimeS[index],
      depthM: arrays.depthM.subarray(start, start + cellCount),
      eastVelocityMPS: arrays.eastVelocityMPS.subarray(start, start + cellCount),
      northVelocityMPS: arrays.northVelocityMPS.subarray(start, start + cellCount),
    });
  };
  const gateCapacities = index => (
    arrays.capacityFractionByGateId.subarray(index * 8, index * 8 + 8)
  );
  const gateFluxes = index => (
    arrays.gateFluxM3SByGateId.subarray(index * 8, index * 8 + 8)
  );
  const barrageOpeningFraction = Array.from(
    { length: snapshotCount },
    (_, snapshotIndex) => {
      let total = 0;
      for (let gateIndex = 0; gateIndex < 8; gateIndex += 1) {
        total += arrays.capacityFractionByGateId[snapshotIndex * 8 + gateIndex];
      }
      return total / 8;
    },
  );
  const inputs = Object.freeze({
    hours: Object.freeze(Array.from(arrays.absoluteTimeS, value => value / 3600)),
    tideRelativeM: Object.freeze(Array.from(arrays.headDifferenceM)),
    barrageOpeningFraction: Object.freeze(barrageOpeningFraction),
    ongaDischargeM3S: Object.freeze(Array.from({ length: snapshotCount }, () => 180)),
  });
  return Object.freeze({
    ...baseR1CData,
    metadata: Object.freeze({
      ...baseR1CData.metadata,
      dataMode: 'r1c_local_physics',
      sourceStatus: manifest.status,
      sourceLabel: 'R1Cローカル未較正物理計算',
      interpretation:
        'GUIの8門入力をR1C物理solverへ反映したローカル計算です。現地較正済みの流量予測ではありません。',
      hours: inputs.hours,
      cellCount,
      snapshotCount,
      responsePackSha256: manifest.binary.sha256,
      responsePackVersion: `local-R1C-${job.jobId}`,
      currentFlowProvenanceClassification: 'local_uncalibrated_physics',
      currentFlowProvenanceLabelJa: 'R1Cローカル未較正物理計算',
      fieldGateInputDrivesDisplayedFlow: true,
      automaticGateEstimatorDrivesDisplayedFlow: true,
      mainGatePhysicalMeshSelected: true,
      mainGateSolverConnected: true,
      mainGateResponsePackConnected: false,
      physicalCalibrationPassed: false,
      productionAdopted: false,
      localJobId: job.jobId,
    }),
    responseManifest: Object.freeze(manifest),
    inputs,
    diagnostics: diagnostics(arrays),
    timingsMs: Object.freeze({ synthesis: loadMilliseconds }),
    snapshot,
    replay: Object.freeze({
      absoluteTimeS: arrays.absoluteTimeS,
      gateCapacities,
      gateFluxes,
      upstreamP2HeadM: arrays.upstreamP2HeadM,
      downstreamP2HeadM: arrays.downstreamP2HeadM,
      headDifferenceM: arrays.headDifferenceM,
      fishwayOutflowM3S: arrays.fishwayOutflowM3S,
      fishwayStorageDepthM: arrays.fishwayStorageDepthM,
      storedVolumeM3: arrays.storedVolumeM3,
      openingOrder: Object.freeze([5, 4, 6, 3, 7, 2, 8, 1]),
      closingOrder: Object.freeze([1, 8, 2, 7, 3, 6, 4, 5]),
      fishwayAlwaysEnabled: true,
      readOnly: true,
    }),
  });
}

export async function loadStage20LocalSimulationResult(job, options = {}) {
  assert(job?.status === 'PASS' && job?.resultUsable === true, 'job result is unavailable');
  const fetchImpl = options.fetchImpl || fetch;
  const started = performance.now();
  options.onProgress?.('local-manifest');
  const manifest = await fetchJson(job.manifestUrl, options.signal, fetchImpl);
  validateStage20LocalSimulationManifest(manifest, job);
  options.onProgress?.('local-binary');
  const response = await fetchImpl(job.binaryUrl, {
    cache: 'no-store',
    credentials: 'same-origin',
    mode: 'same-origin',
    redirect: 'error',
    signal: options.signal,
  });
  assert(response.ok, `${job.binaryUrl} returned HTTP ${response.status}`);
  const payload = await response.arrayBuffer();
  const arrays = await parseArrays(manifest, payload);
  options.onProgress?.('local-index');
  return buildStage20LocalSimulationData({
    baseR1CData: options.baseR1CData,
    manifest,
    job,
    arrays,
    loadMilliseconds: performance.now() - started,
  });
}
