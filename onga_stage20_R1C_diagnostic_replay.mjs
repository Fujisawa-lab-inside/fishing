export const STAGE20_R1C_DIAGNOSTIC_REPLAY_SCHEMA =
  'onga-stage20-R1C-diagnostic-replay-GUI-data-v1';

const EXPECTED = Object.freeze({
  approval: Object.freeze({
    url: './config/stage20_R1C_diagnostic_replay_GUI_integration_approval_v1.json',
    sha256: '4ce2f0b6693c6c581f104714d9f32f3f5d6608443ba289baeda3dbe3808c4e15',
    byteLength: 2546,
  }),
  approvalValidation: Object.freeze({
    url: './docs/results/stage20-R1C-diagnostic-replay-GUI-integration-approval-v1/static-validation.json',
    sha256: '6bfdd4ea451f758e0c661eedaa733c307972ddf019462e8f9b02cb987bec80b2',
    byteLength: 3601,
  }),
  replayManifest: Object.freeze({
    url: './docs/results/stage20-R1C-browser-replay-candidate-v1/manifest.json',
    sha256: 'b285e5c1c821b5b197b493b9409028994b9f40d500e3b926f848644ce09fab82',
    byteLength: 6624,
  }),
  replayValidation: Object.freeze({
    url: './docs/results/stage20-R1C-browser-replay-candidate-v1/static-validation.json',
    sha256: '03a0ce8ea1f1b94d41f9e9ee562cec5b23c0206f71544c61b76477fcda96043f',
    byteLength: 8816,
  }),
  replayBinary: Object.freeze({
    url: './docs/results/stage20-R1C-browser-replay-candidate-v1/replay-fields.bin',
    sha256: '4056d994cf91bef37af2eabbc67f10ead1a753e6c2018845b8d88382590c336a',
    byteLength: 78210991,
  }),
});

const REQUIRED_ARRAYS = Object.freeze([
  'verticesM',
  'triangles',
  'absoluteTimeS',
  'sourceStageCode',
  'sourceCheckpointIndex',
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
  if (!condition) throw new Error(`[stage20-R1C-replay] ${message}`);
}

function resolveUrl(value) {
  return new URL(value, import.meta.url).href;
}

function bytesToHex(bytes) {
  return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
}

async function sha256ArrayBuffer(payload) {
  return bytesToHex(new Uint8Array(await crypto.subtle.digest('SHA-256', payload)));
}

async function fetchPinnedArrayBuffer(binding, signal, fetchImpl = fetch) {
  const url = resolveUrl(binding.url);
  const response = await fetchImpl(url, { cache: 'no-store', signal });
  assert(response.ok, `${binding.url} returned HTTP ${response.status}`);
  const payload = await response.arrayBuffer();
  assert(payload.byteLength === binding.byteLength, `${binding.url} byte length changed`);
  assert(await sha256ArrayBuffer(payload) === binding.sha256, `${binding.url} identity changed`);
  return payload;
}

async function fetchPinnedJson(binding, signal, fetchImpl = fetch) {
  const payload = await fetchPinnedArrayBuffer(binding, signal, fetchImpl);
  return JSON.parse(new TextDecoder().decode(payload));
}

export function validateStage20R1CReplayApproval(approval, validation) {
  assert(
    approval?.schema === 'onga-stage20-R1C-diagnostic-replay-GUI-integration-approval-v1',
    'integration approval schema changed',
  );
  assert(
    approval?.status === 'approved_local_private_R1C_diagnostic_GUI_connection',
    'local/private R1C GUI connection is not approved',
  );
  assert(approval?.userEvidence?.text === '承認する', 'approval user evidence changed');
  const scope = approval?.authorizedScope;
  assert(
    scope?.addOptInR1CDiagnosticReplayMode === true
      && scope?.existingSyntheticModeRemainsDefault === true
      && scope?.lazyLoadOnlyAfterR1CSelection === true
      && scope?.readOnlySavedReplay === true
      && scope?.fieldGateInputMayChangeReplay === false
      && scope?.automaticGateEstimatorMayChangeReplay === false
      && scope?.fishwayAlwaysEnabledAndNotControllable === true
      && scope?.uncalibratedLabelsRequired === true
      && scope?.newSolverRunCount === 0,
    'approved R1C GUI scope changed',
  );
  assert(
    validation?.schema
      === 'onga-stage20-R1C-diagnostic-replay-GUI-integration-approval-static-validation-v1'
      && validation?.status === 'PASS'
      && validation?.passedCount === validation?.checkCount
      && validation?.checkCount === 6
      && validation?.approvalSha256 === EXPECTED.approval.sha256
      && validation?.newSolverRunCount === 0
      && validation?.publicRuntimeChanged === false,
    'integration approval validation changed',
  );
  return Object.freeze({ approval, validation });
}

export function validateStage20R1CReplayManifest(manifest, validation) {
  assert(
    manifest?.schema === 'onga-stage20-R1C-browser-replay-candidate-v1'
      && manifest?.version === 1
      && manifest?.status === 'private_browser_candidate_ready_not_GUI_connected',
    'browser replay candidate identity changed',
  );
  assert(
    manifest?.classification?.relativeDiagnosticReplay === true
      && manifest?.classification?.physicalFieldAccuracy === false
      && manifest?.classification?.productionResponsePack === false
      && manifest?.classification?.publicBrowserAsset === false,
    'browser replay classification changed',
  );
  assert(
    manifest?.mesh?.cellCount === 37724
      && manifest?.mesh?.vertexCount === 19771
      && manifest?.mesh?.triangleCount === 37724
      && manifest?.mesh?.geometryChangedByExport === false,
    'R1C browser mesh identity changed',
  );
  assert(
    manifest?.timeline?.absoluteStartS === 0
      && manifest?.timeline?.absoluteEndS === 10200
      && manifest?.timeline?.intervalS === 60
      && manifest?.timeline?.snapshotCount === 171,
    'R1C replay timeline changed',
  );
  assert(
    manifest?.binary?.path ===
      'docs/results/stage20-R1C-browser-replay-candidate-v1/replay-fields.bin'
      && manifest?.binary?.sha256 === EXPECTED.replayBinary.sha256
      && manifest?.binary?.byteLength === EXPECTED.replayBinary.byteLength,
    'R1C replay binary binding changed',
  );
  assert(
    manifest?.componentOrder?.join(',') ===
      'depthM,eastVelocityMPS,northVelocityMPS',
    'R1C replay component order changed',
  );
  assert(
    REQUIRED_ARRAYS.every(name => Object.hasOwn(manifest?.arrays || {}, name))
      && Object.keys(manifest.arrays).length === REQUIRED_ARRAYS.length,
    'R1C replay array set changed',
  );
  const display = manifest?.displayContract;
  assert(
    display?.geometryMustUseEmbeddedVerticesAndTriangles === true
      && display?.fishwayAlwaysEnabled === true
      && display?.uncalibratedBannerRequired === true
      && display?.fieldGateInputMayDriveThisReplay === false
      && display?.automaticGateEstimatorMayDriveThisReplay === false
      && display?.replayTimeSelectionOnly === true
      && display?.gateCapacityMeaning?.includes('not_measured_gate_lift'),
    'R1C replay display contract changed',
  );
  assert(
    validation?.schema === 'onga-stage20-R1C-browser-replay-candidate-static-validation-v1'
      && validation?.status === 'PASS'
      && validation?.passedCount === validation?.checkCount
      && validation?.checkCount === 10
      && validation?.manifestSha256 === EXPECTED.replayManifest.sha256
      && validation?.binarySha256 === EXPECTED.replayBinary.sha256
      && validation?.newSolverRunCount === 0
      && validation?.existingGUIChanged === false
      && validation?.publicRuntimeChanged === false,
    'R1C replay validation changed',
  );
  return Object.freeze({ manifest, validation });
}

function shapeLength(shape) {
  return shape.reduce((product, value) => product * value, 1);
}

function assertLittleEndian() {
  const word = new Uint16Array([0x1234]);
  assert(new Uint8Array(word.buffer)[0] === 0x34, 'little-endian browser is required');
}

function typedArrayFromDescriptor(payload, descriptor, name) {
  const Constructor = TYPE_CONSTRUCTORS[descriptor.dtype];
  assert(Constructor, `${name} dtype is unsupported`);
  assert(
    Number.isInteger(descriptor.byteOffset)
      && descriptor.byteOffset >= 0
      && Number.isInteger(descriptor.byteLength)
      && descriptor.byteLength > 0,
    `${name} byte range is invalid`,
  );
  const count = shapeLength(descriptor.shape);
  assert(
    descriptor.byteLength === count * Constructor.BYTES_PER_ELEMENT,
    `${name} byte length and shape differ`,
  );
  assert(
    descriptor.byteOffset + descriptor.byteLength <= payload.byteLength,
    `${name} exceeds the replay binary`,
  );
  const copied = new Uint8Array(
    payload,
    descriptor.byteOffset,
    descriptor.byteLength,
  ).slice();
  return new Constructor(copied.buffer);
}

export function parseStage20R1CReplayBinary(manifest, payload) {
  assertLittleEndian();
  assert(payload instanceof ArrayBuffer, 'replay payload must be an ArrayBuffer');
  assert(
    payload.byteLength === manifest.binary.byteLength,
    'replay binary byte length differs from manifest',
  );
  const arrays = {};
  for (const name of REQUIRED_ARRAYS) {
    arrays[name] = typedArrayFromDescriptor(payload, manifest.arrays[name], name);
  }
  assert(arrays.verticesM.length === 19771 * 2, 'verticesM shape changed');
  assert(arrays.triangles.length === 37724 * 3, 'triangles shape changed');
  assert(arrays.absoluteTimeS.length === 171, 'absoluteTimeS shape changed');
  assert(arrays.depthM.length === 171 * 37724, 'depthM shape changed');
  assert(arrays.eastVelocityMPS.length === arrays.depthM.length, 'east velocity shape changed');
  assert(arrays.northVelocityMPS.length === arrays.depthM.length, 'north velocity shape changed');
  assert(arrays.capacityFractionByGateId.length === 171 * 8, 'gate capacity shape changed');
  assert(arrays.gateFluxM3SByGateId.length === 171 * 8, 'gate flux shape changed');
  for (let index = 0; index < arrays.absoluteTimeS.length; index += 1) {
    assert(arrays.absoluteTimeS[index] === index * 60, '60-second replay timeline changed');
  }
  return Object.freeze(arrays);
}

// EPSG:32652 (WGS84 / UTM zone 52N) to EPSG:4326.
export function utm52NToLonLat(eastingM, northingM) {
  assert(Number.isFinite(eastingM) && Number.isFinite(northingM), 'UTM coordinate is invalid');
  const a = 6378137.0;
  const eccentricitySquared = 0.0066943799901413165;
  const eccentricityPrimeSquared =
    eccentricitySquared / (1.0 - eccentricitySquared);
  const k0 = 0.9996;
  const x = eastingM - 500000.0;
  const meridionalArc = northingM / k0;
  const mu = meridionalArc / (
    a * (
      1.0
      - eccentricitySquared / 4.0
      - 3.0 * eccentricitySquared ** 2 / 64.0
      - 5.0 * eccentricitySquared ** 3 / 256.0
    )
  );
  const root = Math.sqrt(1.0 - eccentricitySquared);
  const e1 = (1.0 - root) / (1.0 + root);
  const j1 = 3.0 * e1 / 2.0 - 27.0 * e1 ** 3 / 32.0;
  const j2 = 21.0 * e1 ** 2 / 16.0 - 55.0 * e1 ** 4 / 32.0;
  const j3 = 151.0 * e1 ** 3 / 96.0;
  const j4 = 1097.0 * e1 ** 4 / 512.0;
  const footprintLatitude = mu
    + j1 * Math.sin(2.0 * mu)
    + j2 * Math.sin(4.0 * mu)
    + j3 * Math.sin(6.0 * mu)
    + j4 * Math.sin(8.0 * mu);
  const sin = Math.sin(footprintLatitude);
  const cos = Math.cos(footprintLatitude);
  const tan = Math.tan(footprintLatitude);
  const c1 = eccentricityPrimeSquared * cos ** 2;
  const t1 = tan ** 2;
  const n1 = a / Math.sqrt(1.0 - eccentricitySquared * sin ** 2);
  const r1 = a * (1.0 - eccentricitySquared)
    / (1.0 - eccentricitySquared * sin ** 2) ** 1.5;
  const d = x / (n1 * k0);
  const latitude = footprintLatitude - n1 * tan / r1 * (
    d ** 2 / 2.0
    - (5.0 + 3.0 * t1 + 10.0 * c1 - 4.0 * c1 ** 2
      - 9.0 * eccentricityPrimeSquared) * d ** 4 / 24.0
    + (61.0 + 90.0 * t1 + 298.0 * c1 + 45.0 * t1 ** 2
      - 252.0 * eccentricityPrimeSquared - 3.0 * c1 ** 2)
      * d ** 6 / 720.0
  );
  const longitudeOffset = (
    d
    - (1.0 + 2.0 * t1 + c1) * d ** 3 / 6.0
    + (5.0 - 2.0 * c1 + 28.0 * t1 - 3.0 * c1 ** 2
      + 8.0 * eccentricityPrimeSquared + 24.0 * t1 ** 2)
      * d ** 5 / 120.0
  ) / cos;
  return Object.freeze([
    129.0 + longitudeOffset * 180.0 / Math.PI,
    latitude * 180.0 / Math.PI,
  ]);
}

function deriveVertexLonLat(verticesM) {
  const result = new Float64Array(verticesM.length);
  for (let index = 0; index < verticesM.length; index += 2) {
    const [longitude, latitude] = utm52NToLonLat(
      verticesM[index],
      verticesM[index + 1],
    );
    result[index] = longitude;
    result[index + 1] = latitude;
  }
  return result;
}

function deriveBoundaryEdges(triangles) {
  const counts = new Map();
  for (let cell = 0; cell < triangles.length / 3; cell += 1) {
    const vertices = [
      triangles[cell * 3],
      triangles[cell * 3 + 1],
      triangles[cell * 3 + 2],
    ];
    for (const [left, right] of [
      [vertices[0], vertices[1]],
      [vertices[1], vertices[2]],
      [vertices[2], vertices[0]],
    ]) {
      const a = Math.min(left, right);
      const b = Math.max(left, right);
      const key = `${a}:${b}`;
      const existing = counts.get(key);
      if (existing) {
        existing.count += 1;
      } else {
        counts.set(key, { left: a, right: b, count: 1 });
      }
    }
  }
  const boundary = [];
  for (const item of counts.values()) {
    if (item.count === 1) boundary.push(item.left, item.right);
  }
  return Int32Array.from(boundary);
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
  assert(nonFiniteValueCount === 0, 'replay fields contain non-finite values');
  assert(minimumDepthM >= 0, 'replay fields contain negative depth');
  return Object.freeze({
    minimumDepthM,
    maximumDepthM,
    maximumSpeedMPS,
    nonFiniteValueCount,
    negativeDepthCount: 0,
  });
}

function buildInputs(arrays) {
  const hours = Array.from(arrays.absoluteTimeS, value => value / 3600.0);
  const barrageOpeningFraction = Array.from(
    { length: arrays.absoluteTimeS.length },
    (_, snapshotIndex) => {
      let total = 0;
      for (let gateIndex = 0; gateIndex < 8; gateIndex += 1) {
        total += arrays.capacityFractionByGateId[snapshotIndex * 8 + gateIndex];
      }
      return total / 8.0;
    },
  );
  return Object.freeze({
    hours: Object.freeze(hours),
    tideRelativeM: Object.freeze(Array.from(arrays.headDifferenceM)),
    barrageOpeningFraction: Object.freeze(barrageOpeningFraction),
    ongaDischargeM3S: Object.freeze(Array.from({ length: hours.length }, () => 180.0)),
  });
}

export function buildStage20R1CDiagnosticReplayData({
  baseData,
  manifest,
  validation,
  approval,
  approvalValidation,
  arrays,
  loadMilliseconds = 0,
}) {
  assert(baseData?.schema === 'onga-stage20-gui-data-v1', 'base GUI data is unavailable');
  validateStage20R1CReplayApproval(approval, approvalValidation);
  validateStage20R1CReplayManifest(manifest, validation);
  assert(arrays?.depthM instanceof Float32Array, 'parsed R1C arrays are unavailable');

  const vertexLonLat = deriveVertexLonLat(arrays.verticesM);
  const vertexLocalMillimetres = new Float64Array(arrays.verticesM.length);
  for (let index = 0; index < arrays.verticesM.length; index += 1) {
    vertexLocalMillimetres[index] = arrays.verticesM[index] * 1000.0;
  }
  const boundaryEdges = deriveBoundaryEdges(arrays.triangles);
  const diagnostic = diagnostics(arrays);
  const inputs = buildInputs(arrays);
  const cellCount = manifest.mesh.cellCount;
  const snapshotCount = manifest.timeline.snapshotCount;
  const snapshot = index => {
    assert(
      Number.isInteger(index) && index >= 0 && index < snapshotCount,
      'R1C snapshot index is invalid',
    );
    const start = index * cellCount;
    return Object.freeze({
      index,
      hour: arrays.absoluteTimeS[index] / 3600.0,
      absoluteTimeS: arrays.absoluteTimeS[index],
      depthM: arrays.depthM.subarray(start, start + cellCount),
      eastVelocityMPS: arrays.eastVelocityMPS.subarray(start, start + cellCount),
      northVelocityMPS: arrays.northVelocityMPS.subarray(start, start + cellCount),
    });
  };
  const gateCapacities = index => {
    assert(
      Number.isInteger(index) && index >= 0 && index < snapshotCount,
      'R1C gate-capacity snapshot index is invalid',
    );
    return arrays.capacityFractionByGateId.subarray(index * 8, index * 8 + 8);
  };
  const gateFluxes = index => {
    assert(
      Number.isInteger(index) && index >= 0 && index < snapshotCount,
      'R1C gate-flux snapshot index is invalid',
    );
    return arrays.gateFluxM3SByGateId.subarray(index * 8, index * 8 + 8);
  };

  const mesh = Object.freeze({
    manifest: Object.freeze({
      schema: 'onga-stage20-R1C-review-mesh-browser-view-v1',
      version: 1,
      status: 'private_uncalibrated_diagnostic_view_only',
      counts: Object.freeze({
        vertices: manifest.mesh.vertexCount,
        cells: manifest.mesh.cellCount,
      }),
      binary: Object.freeze({
        sha256: manifest.binary.sha256,
        byteLength: manifest.binary.byteLength,
      }),
    }),
    arrays: Object.freeze({
      triangles: arrays.triangles,
      vertices_m: arrays.verticesM,
      vertex_local_mm: vertexLocalMillimetres,
      vertex_lonlat: vertexLonLat,
      boundary_edges: boundaryEdges,
      fishway_cells: new Int32Array(0),
    }),
  });

  return Object.freeze({
    ...baseData,
    schema: STAGE20_R1C_DIAGNOSTIC_REPLAY_SCHEMA,
    metadata: Object.freeze({
      ...baseData.metadata,
      dataMode: 'r1c_diagnostic_replay',
      sourceStatus: manifest.status,
      sourceLabel: 'R1C未較正診断',
      interpretation:
        '標準開閉cycleの保存済み診断結果です。現地流量の絶対再現、物理較正、予測ではありません。',
      hours: inputs.hours,
      componentOrder: Object.freeze([...manifest.componentOrder]),
      cellCount,
      snapshotCount,
      meshSha256:
        '7f3e84b73fab3bff1ba4699dbf9b1299159c40e91d042376046a6fe99fc03164',
      responsePackSha256: manifest.binary.sha256,
      responsePackVersion: 'R1C-private-diagnostic-replay-v1',
      currentFlowProvenanceClassification: 'uncalibrated_diagnostic_replay',
      currentFlowProvenanceLabelJa: 'R1C未較正診断リプレイ',
      R1CDiagnosticReplayConnected: true,
      R1CDiagnosticReplayApprovalSha256: EXPECTED.approval.sha256,
      R1CDiagnosticReplayManifestSha256: EXPECTED.replayManifest.sha256,
      R1CDiagnosticReplayBinarySha256: EXPECTED.replayBinary.sha256,
      fishwayAlwaysEnabled: true,
      gateCapacityMeaning:
        'classification_face_capacity_multiplier_not_measured_gate_lift',
      fieldGateInputDrivesDisplayedFlow: false,
      automaticGateEstimatorDrivesDisplayedFlow: false,
      physicalCalibrationPassed: false,
      productionAdopted: false,
    }),
    mesh,
    responseManifest: Object.freeze(manifest),
    inputs,
    diagnostics: diagnostic,
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

export async function loadStage20R1CDiagnosticReplay(options = {}) {
  const baseData = options.baseData;
  assert(baseData, 'base GUI data is required for R1C diagnostic mode');
  const signal = options.signal;
  const fetchImpl = options.fetchImpl || fetch;
  const started = performance.now();
  options.onProgress?.('R1C-approval');
  const [approval, approvalValidation, manifest, validation] = await Promise.all([
    fetchPinnedJson(EXPECTED.approval, signal, fetchImpl),
    fetchPinnedJson(EXPECTED.approvalValidation, signal, fetchImpl),
    fetchPinnedJson(EXPECTED.replayManifest, signal, fetchImpl),
    fetchPinnedJson(EXPECTED.replayValidation, signal, fetchImpl),
  ]);
  validateStage20R1CReplayApproval(approval, approvalValidation);
  validateStage20R1CReplayManifest(manifest, validation);
  options.onProgress?.('R1C-binary');
  const payload = await fetchPinnedArrayBuffer(EXPECTED.replayBinary, signal, fetchImpl);
  const arrays = parseStage20R1CReplayBinary(manifest, payload);
  options.onProgress?.('R1C-index');
  return buildStage20R1CDiagnosticReplayData({
    baseData,
    manifest,
    validation,
    approval,
    approvalValidation,
    arrays,
    loadMilliseconds: performance.now() - started,
  });
}
