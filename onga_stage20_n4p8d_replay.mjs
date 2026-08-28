import { utm52NToLonLat } from './onga_stage20_R1C_diagnostic_replay.mjs';

export const STAGE20_N4P8D_REPLAY_SCHEMA =
  'onga-stage20-n4p8d-36h-GUI-data-20260806-v1';

const EXPECTED = Object.freeze({
  approval: Object.freeze({
    url: './config/stage20_n4p8d_gui_readonly_integration_approval_20260805_v1.json',
    sha256: 'dd3096c58c381ddf755ecfa9d776bcffc4d54715d169418568d2b251aa5e575c',
    byteLength: 1010,
  }),
  manifest: Object.freeze({
    url: './docs/results/stage20-n4p8d-36h-browser-sidecar-20260805-v1/manifest.json',
    sha256: 'c44289d6333ee47fd3d7a37a28523a66db142d1f1c3924c0faed8ea45970f3b7',
    byteLength: 25237,
  }),
  validation: Object.freeze({
    url: './docs/results/stage20-n4p8d-36h-browser-sidecar-20260805-v1/static-validation.json',
    sha256: 'a24f463d2437564c0f56d8818c73c5f42239324e6eb3c0b070e7df803a9a912b',
    byteLength: 4946,
  }),
  landFlowApproval: Object.freeze({
    url: './config/stage20_n4p8d_land_flow_visual_approval_20260806_v1.json',
    sha256: '002ae6310844f7c22d719422462ee8d30875961c6a830e54d1a22bdc9f66e9ff',
    byteLength: 2470,
  }),
  landFlowValidation: Object.freeze({
    url: './docs/results/stage20-n4p8d-land-flow-visual-approval-20260806-v1/static-validation.json',
    sha256: 'cf746f35b5b50ca2d359ae1a6aa5873e9329fc1f3c98681cf67d52d321ea61a5',
    byteLength: 5214,
  }),
  binary: Object.freeze({
    url: './docs/results/stage20-n4p8d-36h-browser-sidecar-20260805-v1/replay-fields.bin',
    sha256: 'c6e0b16c3ad0efc057184cbb148bd396524a541a38e5821bff2788766b7898f5',
    byteLength: 17520552,
  }),
});

const ARRAY_ORDER = Object.freeze([
  'verticesM',
  'triangles',
  'depthM',
  'eastVelocityMPS',
  'northVelocityMPS',
  'gateCapacityFractionByGateId',
  'boundaryCommandM_N_O_G',
  'storedVolumeM3',
  'timestampUnixNs',
]);
const TYPE_CONSTRUCTORS = Object.freeze({
  float32: Float32Array,
  float64: Float64Array,
  int32: Int32Array,
  int8: Int8Array,
  int64: BigInt64Array,
});
const CELL_COUNT = 37724;
const VERTEX_COUNT = 19771;
const SNAPSHOT_COUNT = 37;
const OPENING_ORDER = Object.freeze([5, 4, 6, 3, 7, 2, 8, 1]);

function assert(condition, message) {
  if (!condition) throw new Error(`[stage20-N4P8d-replay] ${message}`);
}

function resolveUrl(value) {
  return new URL(value, import.meta.url).href;
}

function bytesToHex(bytes) {
  return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
}

async function sha256(payload) {
  assert(globalThis.crypto?.subtle, 'Web Crypto SHA-256 is unavailable');
  return bytesToHex(new Uint8Array(await crypto.subtle.digest('SHA-256', payload)));
}

async function fetchPinned(binding, signal, fetchImpl) {
  const response = await fetchImpl(resolveUrl(binding.url), { cache: 'no-store', signal });
  assert(response.ok, `${binding.url} returned HTTP ${response.status}`);
  const payload = await response.arrayBuffer();
  assert(payload.byteLength === binding.byteLength, `${binding.url} byte length changed`);
  assert(await sha256(payload) === binding.sha256, `${binding.url} SHA-256 changed`);
  return payload;
}

async function fetchPinnedJson(binding, signal, fetchImpl) {
  const payload = await fetchPinned(binding, signal, fetchImpl);
  return JSON.parse(new TextDecoder().decode(payload));
}

function sameJson(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

export function validateStage20N4P8dReplaySources(
  approval,
  manifest,
  validation,
  landFlowApproval,
  landFlowValidation,
) {
  assert(
    approval?.schema === 'onga-stage20-n4p8d-gui-readonly-integration-approval-20260805-v1'
      && approval?.status === 'APPROVED_LOCAL_OPT_IN_READ_ONLY_GUI_CONNECTION',
    'local GUI approval changed',
  );
  assert(
    approval?.authorizedScope?.addOptInN4P8dReplayMode === true
      && approval?.authorizedScope?.existingDefaultModeUnchanged === true
      && approval?.authorizedScope?.lazyLoadOnlyAfterSelection === true
      && approval?.authorizedScope?.readOnlySavedReplay === true
      && approval?.authorizedScope?.savedTimeSelectionOnly === true
      && approval?.authorizedScope?.fieldGateInputMayChangeReplay === false
      && approval?.authorizedScope?.automaticGateEstimatorMayChangeReplay === false
      && approval?.authorizedScope?.fishwayAlwaysEnabled === true
      && approval?.authorizedScope?.microEquivalentAggregatedIntoFishway === true
      && approval?.authorizedScope?.newSolverRunCount === 0,
    'approved local replay scope changed',
  );
  assert(
    manifest?.schema === 'onga-stage20-n4p8d-36h-browser-sidecar-20260805-v1'
      && manifest?.status === 'SEALED_READ_ONLY_BROWSER_REPLAY'
      && manifest?.classification === '未較正・モデル参考値',
    'sealed replay identity changed',
  );
  assert(
    manifest?.mesh?.sha256 === '7f3e84b73fab3bff1ba4699dbf9b1299159c40e91d042376046a6fe99fc03164'
      && manifest?.mesh?.cellCount === CELL_COUNT
      && manifest?.mesh?.vertexCount === VERTEX_COUNT,
    'R1C mesh identity changed',
  );
  assert(
    manifest?.timeline?.snapshotCount === SNAPSHOT_COUNT
      && manifest?.timeline?.intervalHours === 1
      && manifest?.timeline?.interpolationAllowed === false
      && manifest?.timeline?.modelHours?.length === SNAPSHOT_COUNT
      && manifest?.timeline?.timestampsJst?.length === SNAPSHOT_COUNT,
    '37-point timeline changed',
  );
  assert(
    manifest?.scenario?.fishwayAlwaysEnabled === true
      && manifest?.scenario?.microEquivalentAggregatedIntoFishway === true
      && manifest?.scenario?.weatherObserved === false
      && manifest?.scenario?.calibratedForecast === false
      && sameJson(manifest?.scenario?.automaticGateOrder, OPENING_ORDER),
    'scenario semantics changed',
  );
  assert(
    manifest?.runtimePolicy?.readOnlyReplay === true
      && manifest?.runtimePolicy?.savedTimeSelectionOnly === true
      && manifest?.runtimePolicy?.publicOrMainAdoptionAuthorized === false
      && manifest?.runtimePolicy?.physicalSolverStepCount === 0,
    'sealed runtime policy changed',
  );
  assert(
    validation?.schema === 'onga-stage20-n4p8d-36h-browser-sidecar-20260805-static-validation-v1'
      && validation?.status === 'PASS'
      && validation?.checkCount === 65
      && validation?.passedCount === 65
      && validation?.failedCount === 0
      && validation?.binarySha256 === EXPECTED.binary.sha256
      && validation?.manifestSha256 === EXPECTED.manifest.sha256,
    'independent replay validation changed',
  );
  assert(
    landFlowApproval?.schema === 'onga-stage20-n4p8d-land-flow-visual-approval-20260806-v1'
      && landFlowApproval?.status === 'USER_VISUAL_APPROVED_NO_APPARENT_PROBLEM'
      && landFlowApproval?.classification === '未較正・モデル参考値',
    'land-flow visual approval changed',
  );
  assert(
    landFlowApproval?.authorizedNextScope?.addReadOnly36HourMaximumSpeedLayerToLocalGui === true
      && landFlowApproval?.authorizedNextScope?.showOutsideWaterCentroidCellsAsMagentaAuditOverlay === true
      && landFlowApproval?.authorizedNextScope?.newSolverRunCount === 0
      && landFlowApproval?.authorizedNextScope?.meshGeometryMutation === false,
    'land-flow GUI scope changed',
  );
  const landEnvelope = landFlowApproval?.acceptedNumericalEnvelope;
  assert(
    landEnvelope?.cellCount === CELL_COUNT
      && landEnvelope?.outsideWaterCentroidCellCount === 19
      && landEnvelope?.outsideWaterCentroidCellIds?.length === 19
      && new Set(landEnvelope.outsideWaterCentroidCellIds).size === 19
      && landEnvelope.outsideWaterCentroidCellIds.every(value => Number.isInteger(value) && value >= 0 && value < CELL_COUNT)
      && landEnvelope?.maximumOutsideWaterCentroidDistanceM <= 0.60
      && landEnvelope?.maximumOutsideWaterVertexDistanceM <= 2.0,
    'accepted land-flow numerical envelope changed',
  );
  assert(
    landFlowValidation?.schema === 'onga-stage20-n4p8d-land-flow-visual-approval-20260806-static-validation-v1'
      && landFlowValidation?.status === 'PASS'
      && landFlowValidation?.checkCount === 27
      && landFlowValidation?.passedCount === 27
      && landFlowValidation?.failedCount === 0,
    'land-flow approval validation changed',
  );
  assert(sameJson(manifest?.binary?.arrayOrder, ARRAY_ORDER), 'array order changed');
  return Object.freeze({ approval, manifest, validation, landFlowApproval, landFlowValidation });
}

async function parseArrays(manifest, payload) {
  assert(payload instanceof ArrayBuffer, 'binary payload is unavailable');
  assert(payload.byteLength === EXPECTED.binary.byteLength, 'binary length changed');
  assert(await sha256(payload) === EXPECTED.binary.sha256, 'binary SHA-256 changed');
  const arrays = {};
  let cursor = 0;
  for (const name of ARRAY_ORDER) {
    const descriptor = manifest.arrays[name];
    const Constructor = TYPE_CONSTRUCTORS[descriptor?.dtype];
    assert(Constructor, `${name} dtype is unsupported`);
    assert(descriptor.byteOffset === cursor, `${name} is not contiguous`);
    const count = descriptor.shape.reduce((product, value) => product * value, 1);
    assert(descriptor.byteLength === count * Constructor.BYTES_PER_ELEMENT, `${name} shape differs`);
    const bytes = new Uint8Array(payload, descriptor.byteOffset, descriptor.byteLength).slice();
    assert(await sha256(bytes.buffer) === descriptor.sha256, `${name} SHA-256 changed`);
    arrays[name] = new Constructor(bytes.buffer);
    cursor += descriptor.byteLength;
  }
  assert(cursor === payload.byteLength, 'binary contains undescribed bytes');
  assert(arrays.verticesM.length === VERTEX_COUNT * 2, 'vertex count changed');
  assert(arrays.triangles.length === CELL_COUNT * 3, 'triangle count changed');
  assert(arrays.depthM.length === SNAPSHOT_COUNT * CELL_COUNT, 'depth field shape changed');
  return Object.freeze(arrays);
}

function deriveVertexLonLat(verticesM) {
  const result = new Float64Array(verticesM.length);
  for (let index = 0; index < verticesM.length; index += 2) {
    const [longitude, latitude] = utm52NToLonLat(verticesM[index], verticesM[index + 1]);
    result[index] = longitude;
    result[index + 1] = latitude;
  }
  return result;
}

function deriveBoundaryEdges(triangles) {
  const counts = new Map();
  for (let cell = 0; cell < triangles.length / 3; cell += 1) {
    const a = triangles[cell * 3];
    const b = triangles[cell * 3 + 1];
    const c = triangles[cell * 3 + 2];
    for (const [left, right] of [[a, b], [b, c], [c, a]]) {
      const low = Math.min(left, right);
      const high = Math.max(left, right);
      const key = `${low}:${high}`;
      counts.set(key, (counts.get(key) || 0) + 1);
    }
  }
  const result = [];
  for (const [key, count] of counts) {
    if (count !== 1) continue;
    const [left, right] = key.split(':').map(Number);
    result.push(left, right);
  }
  return Int32Array.from(result);
}

function diagnostics(arrays) {
  let minimumDepthM = Number.POSITIVE_INFINITY;
  let maximumDepthM = 0;
  let maximumSpeedMPS = 0;
  let nonFiniteValueCount = 0;
  let negativeDepthCount = 0;
  for (let index = 0; index < arrays.depthM.length; index += 1) {
    const depth = arrays.depthM[index];
    const east = arrays.eastVelocityMPS[index];
    const north = arrays.northVelocityMPS[index];
    if (!Number.isFinite(depth) || !Number.isFinite(east) || !Number.isFinite(north)) {
      nonFiniteValueCount += 1;
      continue;
    }
    if (depth < 0) negativeDepthCount += 1;
    minimumDepthM = Math.min(minimumDepthM, depth);
    maximumDepthM = Math.max(maximumDepthM, depth);
    maximumSpeedMPS = Math.max(maximumSpeedMPS, Math.hypot(east, north));
  }
  assert(nonFiniteValueCount === 0 && negativeDepthCount === 0, 'replay contains invalid fields');
  return Object.freeze({ minimumDepthM, maximumDepthM, maximumSpeedMPS, nonFiniteValueCount, negativeDepthCount });
}

function maximumSpeedByCell(arrays) {
  const result = new Float32Array(CELL_COUNT);
  for (let snapshot = 0; snapshot < SNAPSHOT_COUNT; snapshot += 1) {
    const offset = snapshot * CELL_COUNT;
    for (let cell = 0; cell < CELL_COUNT; cell += 1) {
      result[cell] = Math.max(
        result[cell],
        Math.hypot(
          arrays.eastVelocityMPS[offset + cell],
          arrays.northVelocityMPS[offset + cell],
        ),
      );
    }
  }
  return result;
}

export function buildStage20N4P8dReplayData({
  baseData,
  approval,
  manifest,
  validation,
  landFlowApproval,
  landFlowValidation,
  arrays,
  loadMilliseconds = 0,
}) {
  assert(baseData?.schema === 'onga-stage20-gui-data-v1', 'base GUI data is unavailable');
  validateStage20N4P8dReplaySources(
    approval,
    manifest,
    validation,
    landFlowApproval,
    landFlowValidation,
  );
  assert(arrays?.depthM instanceof Float32Array, 'parsed fields are unavailable');
  const vertexLonLat = deriveVertexLonLat(arrays.verticesM);
  const vertexLocalMillimetres = Float64Array.from(arrays.verticesM, value => value * 1000);
  const boundaryEdges = deriveBoundaryEdges(arrays.triangles);
  const maximumSpeedMPSByCell = maximumSpeedByCell(arrays);
  const landEnvelope = landFlowApproval.acceptedNumericalEnvelope;
  const absoluteTimeS = Float64Array.from({ length: SNAPSHOT_COUNT }, (_, index) => index * 3600);
  const tideRelativeM = [];
  const ongaDischargeM3S = [];
  const barrageOpeningFraction = [];
  for (let index = 0; index < SNAPSHOT_COUNT; index += 1) {
    tideRelativeM.push(arrays.boundaryCommandM_N_O_G[index * 4]);
    ongaDischargeM3S.push(arrays.boundaryCommandM_N_O_G[index * 4 + 2]);
    let opening = 0;
    for (let gate = 0; gate < 8; gate += 1) opening += arrays.gateCapacityFractionByGateId[index * 8 + gate];
    barrageOpeningFraction.push(opening / 8);
  }
  const responseManifest = Object.freeze({
    ...manifest,
    timeline: Object.freeze({ ...manifest.timeline, intervalS: 3600, absoluteEndS: 36 * 3600 }),
  });
  const snapshot = index => {
    assert(Number.isInteger(index) && index >= 0 && index < SNAPSHOT_COUNT, 'snapshot index is invalid');
    const start = index * CELL_COUNT;
    return Object.freeze({
      index,
      hour: manifest.timeline.modelHours[index],
      modelHour: manifest.timeline.modelHours[index],
      timestampJst: manifest.timeline.timestampsJst[index],
      absoluteTimeS: absoluteTimeS[index],
      depthM: arrays.depthM.subarray(start, start + CELL_COUNT),
      eastVelocityMPS: arrays.eastVelocityMPS.subarray(start, start + CELL_COUNT),
      northVelocityMPS: arrays.northVelocityMPS.subarray(start, start + CELL_COUNT),
    });
  };
  const gateCapacities = index => {
    assert(Number.isInteger(index) && index >= 0 && index < SNAPSHOT_COUNT, 'gate snapshot index is invalid');
    return arrays.gateCapacityFractionByGateId.subarray(index * 8, index * 8 + 8);
  };
  const unavailable = Object.freeze({
    upstreamP2HeadM: '保存時点に値なし',
    downstreamP2HeadM: '保存時点に値なし',
    headDifferenceM: '保存時点に値なし',
    fishwayOutflowM3S: '保存時点に値なし',
    fishwayStorageDepthM: '保存時点に値なし',
    gateFluxM3SByGateId: '保存時点に値なし',
  });
  const displayValue = name => {
    assert(Object.hasOwn(unavailable, name), `unknown unavailable field ${String(name)}`);
    return Object.freeze({ available: false, value: null, displayTextJa: unavailable[name], field: name });
  };
  const mesh = Object.freeze({
    manifest: Object.freeze({
      schema: 'onga-stage20-n4p8d-R1C-review-mesh-browser-view-v1',
      version: 1,
      status: 'local_read_only_uncalibrated_replay',
      counts: Object.freeze({ vertices: VERTEX_COUNT, cells: CELL_COUNT }),
      binary: Object.freeze({ sha256: manifest.binary.sha256, byteLength: manifest.binary.byteLength }),
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
    schema: STAGE20_N4P8D_REPLAY_SCHEMA,
    metadata: Object.freeze({
      ...baseData.metadata,
      dataMode: 'n4p8d_36h_replay',
      sourceStatus: manifest.status,
      sourceLabel: 'N4P8d・36時間保存結果',
      interpretation: '魚道等を簡易集約した未較正36時間計算の保存済み結果です。予測・現地操作指示ではありません。',
      hours: Object.freeze([...manifest.timeline.modelHours]),
      componentOrder: Object.freeze(['depthM', 'eastVelocityMPS', 'northVelocityMPS']),
      cellCount: CELL_COUNT,
      snapshotCount: SNAPSHOT_COUNT,
      meshSha256: manifest.mesh.sha256,
      responsePackSha256: manifest.binary.sha256,
      responsePackVersion: 'N4P8d-sealed-36h-replay-20260805-v1',
      currentFlowProvenanceClassification: 'uncalibrated_n4p8d_36h_replay',
      currentFlowProvenanceLabelJa: 'N4P8d未較正36時間リプレイ',
      fishwayAlwaysEnabled: true,
      microEquivalentAggregatedIntoFishway: true,
      fieldGateInputDrivesDisplayedFlow: false,
      automaticGateEstimatorDrivesDisplayedFlow: false,
      physicalCalibrationPassed: false,
      productionAdopted: false,
      maximumSpeedLayerAvailable: true,
      landFlowVisualApproved: true,
    }),
    mesh,
    responseManifest,
    inputs: Object.freeze({
      hours: Object.freeze([...manifest.timeline.modelHours]),
      tideRelativeM: Object.freeze(tideRelativeM),
      barrageOpeningFraction: Object.freeze(barrageOpeningFraction),
      ongaDischargeM3S: Object.freeze(ongaDischargeM3S),
    }),
    diagnostics: diagnostics(arrays),
    timingsMs: Object.freeze({ synthesis: loadMilliseconds }),
    snapshot,
    displayValue,
    replay: Object.freeze({
      absoluteTimeS,
      timestampsJst: Object.freeze([...manifest.timeline.timestampsJst]),
      boundaryCommandM_N_O_G: arrays.boundaryCommandM_N_O_G,
      storedVolumeM3: arrays.storedVolumeM3,
      maximumSpeedMPSByCell,
      landAudit: Object.freeze({
        outsideWaterCentroidCellIds: Int32Array.from(landEnvelope.outsideWaterCentroidCellIds),
        outsideWaterCentroidCellCount: landEnvelope.outsideWaterCentroidCellCount,
        maximumOutsideWaterCentroidDistanceM: landEnvelope.maximumOutsideWaterCentroidDistanceM,
        maximumOutsideWaterVertexDistanceM: landEnvelope.maximumOutsideWaterVertexDistanceM,
        maximumOutsideWaterCellSpeedMPS: landEnvelope.maximumOutsideWaterCellSpeedMPS,
        userVisualApproved: true,
      }),
      gateCapacities,
      openingOrder: OPENING_ORDER,
      closingOrder: Object.freeze([1, 8, 2, 7, 3, 6, 4, 5]),
      fishwayAlwaysEnabled: true,
      microEquivalentAggregatedIntoFishway: true,
      readOnly: true,
    }),
  });
}

export async function loadStage20N4P8dReplay(options = {}) {
  assert(options.baseData, 'base GUI data is required');
  const fetchImpl = options.fetchImpl || fetch;
  const signal = options.signal;
  const started = performance.now();
  options.onProgress?.('n4p8d-contract');
  const [approval, manifest, validation, landFlowApproval, landFlowValidation] = await Promise.all([
    fetchPinnedJson(EXPECTED.approval, signal, fetchImpl),
    fetchPinnedJson(EXPECTED.manifest, signal, fetchImpl),
    fetchPinnedJson(EXPECTED.validation, signal, fetchImpl),
    fetchPinnedJson(EXPECTED.landFlowApproval, signal, fetchImpl),
    fetchPinnedJson(EXPECTED.landFlowValidation, signal, fetchImpl),
  ]);
  validateStage20N4P8dReplaySources(
    approval,
    manifest,
    validation,
    landFlowApproval,
    landFlowValidation,
  );
  options.onProgress?.('n4p8d-binary');
  const payload = await fetchPinned(EXPECTED.binary, signal, fetchImpl);
  const arrays = await parseArrays(manifest, payload);
  options.onProgress?.('n4p8d-index');
  return buildStage20N4P8dReplayData({
    baseData: options.baseData,
    approval,
    manifest,
    validation,
    landFlowApproval,
    landFlowValidation,
    arrays,
    loadMilliseconds: performance.now() - started,
  });
}
