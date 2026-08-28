export const STAGE20_REFERENCE_V2_DISPLAY_ADAPTER_SCHEMA =
  'onga-stage20-reference-v2-display-adapter-20260730-g6t4-v1';

const EXPECTED_SOURCE_SCHEMA =
  'onga-stage20-reference-v2-sidecar-loader-20260730-l9e4-v1';
const EXPECTED_SUCCESSOR_SCHEMA =
  'onga-stage20-reference-v2-sidecar-loader-20260730-l9e4b-v1';
const EXPECTED_MESH_SHA256 =
  '7f3e84b73fab3bff1ba4699dbf9b1299159c40e91d042376046a6fe99fc03164';
const SNAPSHOT_COUNT = 37;
const CELL_COUNT = 37724;
const VERTEX_COUNT = 19771;
const FIXED_S4_CAPACITY = Object.freeze([0, 0, 1, 1, 1, 1, 0, 0]);
const OPENING_ORDER = Object.freeze([5, 4, 6, 3, 7, 2, 8, 1]);
const CLOSING_ORDER = Object.freeze([1, 8, 2, 7, 3, 6, 4, 5]);
const AVAILABLE_FIELDS = Object.freeze([
  'capacityFractionByGateId',
  'depthM',
  'eastVelocityMPS',
  'northVelocityMPS',
]);
const UNAVAILABLE_FIELDS = Object.freeze([
  'downstreamP2HeadM',
  'fishwayOutflowM3S',
  'fishwayStorageDepthM',
  'gateFluxM3SByGateId',
  'headDifferenceM',
  'storedVolumeM3',
  'upstreamP2HeadM',
]);

function fail(message) {
  throw new Error(`[stage20-reference-v2-display-g6t4] ${message}`);
}

function assert(condition, message) {
  if (!condition) fail(message);
}

function freezeObject(value) {
  return Object.freeze(value);
}

function assertSnapshotIndex(index) {
  assert(
    Number.isInteger(index) && index >= 0 && index < SNAPSHOT_COUNT,
    'snapshot index must be an integer from 0 through 36',
  );
}

function assertCellIndex(index) {
  assert(
    Number.isInteger(index) && index >= 0 && index < CELL_COUNT,
    `cell index must be an integer from 0 through ${CELL_COUNT - 1}`,
  );
}

function assertGateCapacityInput(levels) {
  assert(
    Array.isArray(levels) || ArrayBuffer.isView(levels),
    'gate input must contain eight numeric levels',
  );
  assert(levels.length === 8, 'gate input must contain exactly eight levels');
  for (let index = 0; index < levels.length; index += 1) {
    assert(Number.isFinite(Number(levels[index])), `gate ${index + 1} input is invalid`);
  }
}

// EPSG:32652 (WGS84 / UTM zone 52N) to EPSG:4326. This is the same
// display-only projection used by the existing R1C replay loader.
function utm52NToLonLat(eastingM, northingM) {
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
  return [
    129.0 + longitudeOffset * 180.0 / Math.PI,
    latitude * 180.0 / Math.PI,
  ];
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

function createAvailability(sourceAvailability) {
  const availability = {};
  for (const name of AVAILABLE_FIELDS) {
    availability[name] = freezeObject({
      available: true,
      displayTextJa: null,
      source:
        name === 'capacityFractionByGateId'
          ? 'sealed fixed S4 scenario contract'
          : sourceAvailability[name]?.source || 'sealed S8A1 primitive field',
      reason: null,
    });
  }
  for (const name of UNAVAILABLE_FIELDS) {
    availability[name] = freezeObject({
      available: false,
      displayTextJa: '値なし',
      source: null,
      reason:
        '保存済みreference-v2に瞬時値がありません。0または推定値では補いません。',
    });
  }
  return freezeObject(availability);
}

function calculateDiagnostics(readSnapshot) {
  let minimumDepthM = Number.POSITIVE_INFINITY;
  let maximumDepthM = 0;
  let maximumSpeedMPS = 0;
  let nonFiniteValueCount = 0;
  let negativeDepthCount = 0;
  for (let snapshotIndex = 0; snapshotIndex < SNAPSHOT_COUNT; snapshotIndex += 1) {
    const snapshot = readSnapshot(snapshotIndex);
    for (let cellIndex = 0; cellIndex < CELL_COUNT; cellIndex += 1) {
      const depth = snapshot.depthM[cellIndex];
      const east = snapshot.eastVelocityMPS[cellIndex];
      const north = snapshot.northVelocityMPS[cellIndex];
      if (!Number.isFinite(depth) || !Number.isFinite(east) || !Number.isFinite(north)) {
        nonFiniteValueCount += 1;
        continue;
      }
      if (depth < 0) negativeDepthCount += 1;
      minimumDepthM = Math.min(minimumDepthM, depth);
      maximumDepthM = Math.max(maximumDepthM, depth);
      maximumSpeedMPS = Math.max(maximumSpeedMPS, Math.hypot(east, north));
    }
  }
  assert(nonFiniteValueCount === 0, 'source fields contain non-finite values');
  assert(negativeDepthCount === 0, 'source fields contain negative depth');
  return freezeObject({
    minimumDepthM,
    maximumDepthM,
    maximumSpeedMPS,
    nonFiniteValueCount,
    negativeDepthCount,
  });
}

export function buildStage20ReferenceV2DisplayData({
  baseData,
  sidecar,
  loadMilliseconds = 0,
} = {}) {
  assert(baseData?.schema === 'onga-stage20-gui-data-v1', 'base GUI data is unavailable');
  assert(sidecar?.metadata?.schema === EXPECTED_SOURCE_SCHEMA, 'L9E4 source interface changed');
  assert(
    sidecar?.metadata?.successorSchema === EXPECTED_SUCCESSOR_SCHEMA,
    'L9E4b successor interface is required',
  );
  assert(sidecar?.metadata?.meshSha256 === EXPECTED_MESH_SHA256, 'R1C mesh changed');
  assert(
    sidecar?.metadata?.snapshotCount === SNAPSHOT_COUNT
      && sidecar?.metadata?.cellCount === CELL_COUNT
      && sidecar?.metadata?.vertexCount === VERTEX_COUNT,
    'reference-v2 display dimensions changed',
  );
  assert(
    sidecar?.metadata?.gateStage === 4
      && JSON.stringify(sidecar?.metadata?.openGates) === JSON.stringify([5, 4, 6, 3]),
    'fixed S4 scenario changed',
  );
  assert(
    sidecar?.metadata?.fieldInputDrivesDisplayedFlow === false
      && sidecar?.metadata?.automaticGateEstimatorDrivesDisplayedFlow === false,
    'input-independent replay policy changed',
  );

  const sourceGeometry = sidecar.geometry();
  assert(
    sourceGeometry.verticesM instanceof Float64Array
      && sourceGeometry.verticesM.length === VERTEX_COUNT * 2,
    'vertices are unavailable',
  );
  assert(
    sourceGeometry.triangles instanceof Int32Array
      && sourceGeometry.triangles.length === CELL_COUNT * 3,
    'triangles are unavailable',
  );
  const vertexLonLat = deriveVertexLonLat(sourceGeometry.verticesM);
  const boundaryEdges = deriveBoundaryEdges(sourceGeometry.triangles);
  const snapshotCache = new Map();
  const readSnapshot = index => {
    assertSnapshotIndex(index);
    if (!snapshotCache.has(index)) snapshotCache.set(index, sidecar.snapshot(index));
    return snapshotCache.get(index);
  };
  const availability = createAvailability(sidecar.fieldAvailability);
  const diagnostics = calculateDiagnostics(readSnapshot);
  const timestampsJst = freezeObject([...sidecar.timeline.timestampsJst]);
  const modelHours = freezeObject([...sidecar.timeline.modelHours]);
  const completedHours = freezeObject([...sidecar.timeline.completedHours]);
  const absoluteTimeS = Float64Array.from(
    { length: SNAPSHOT_COUNT },
    (_, index) => index * 3600,
  );

  function snapshot(index) {
    const source = readSnapshot(index);
    return freezeObject({
      index,
      hour: source.modelHour,
      modelHour: source.modelHour,
      completedHour: source.completedHour,
      absoluteTimeS: absoluteTimeS[index],
      timestampJst: source.timestampJst,
      depthM: source.depthM.slice(),
      eastVelocityMPS: source.eastVelocityMPS.slice(),
      northVelocityMPS: source.northVelocityMPS.slice(),
    });
  }

  function fieldAt(name, snapshotIndex, cellIndex) {
    assertSnapshotIndex(snapshotIndex);
    assertCellIndex(cellIndex);
    const source = readSnapshot(snapshotIndex);
    assert(
      name === 'depthM' || name === 'eastVelocityMPS' || name === 'northVelocityMPS',
      `field ${String(name)} is not a primitive display field`,
    );
    return source[name][cellIndex];
  }

  const depthAt = (snapshotIndex, cellIndex) => fieldAt('depthM', snapshotIndex, cellIndex);
  const eastVelocityAt = (snapshotIndex, cellIndex) => (
    fieldAt('eastVelocityMPS', snapshotIndex, cellIndex)
  );
  const northVelocityAt = (snapshotIndex, cellIndex) => (
    fieldAt('northVelocityMPS', snapshotIndex, cellIndex)
  );

  function availabilityFor(name) {
    assert(Object.hasOwn(availability, name), `unknown field ${String(name)}`);
    return availability[name];
  }

  function displayValue(name) {
    const descriptor = availabilityFor(name);
    assert(descriptor.available === false, `${name} is available through a typed accessor`);
    return freezeObject({
      available: false,
      value: null,
      displayTextJa: '値なし',
      field: name,
      reason: descriptor.reason,
    });
  }

  function gateCapacities(index) {
    assertSnapshotIndex(index);
    return Float32Array.from(FIXED_S4_CAPACITY);
  }

  function compareGateInput(levels) {
    assertGateCapacityInput(levels);
    const normalized = Array.from(levels, value => Number(value) > 0 ? 1 : 0);
    const differingGateIds = normalized.flatMap(
      (value, index) => value === FIXED_S4_CAPACITY[index] ? [] : [index + 1],
    );
    return freezeObject({
      dataDriven: false,
      displayedFlowChanged: false,
      fixedScenario: 'S4',
      fixedCapacityFractionByGateId: FIXED_S4_CAPACITY,
      differingGateIds: freezeObject(differingGateIds),
      displayTextJa:
        differingGateIds.length === 0
          ? '固定S4と一致（表示データは変更しません）'
          : `固定S4との差：${differingGateIds.join('・')}番（表示データは変更しません）`,
    });
  }

  const mesh = freezeObject({
    manifest: freezeObject({
      schema: 'onga-stage20-reference-v2-display-mesh-view-v1',
      version: 1,
      status: 'sealed_read_only_reference_v2_geometry',
      counts: freezeObject({ vertices: VERTEX_COUNT, cells: CELL_COUNT }),
      binary: freezeObject({
        sha256: sidecar.metadata.binarySha256,
        meshSha256: EXPECTED_MESH_SHA256,
      }),
    }),
    arrays: freezeObject({
      triangles: sourceGeometry.triangles,
      vertices_m: sourceGeometry.verticesM,
      vertex_local_mm: Float64Array.from(
        sourceGeometry.verticesM,
        value => value * 1000,
      ),
      vertex_lonlat: vertexLonLat,
      boundary_edges: boundaryEdges,
      fishway_cells: new Int32Array(0),
    }),
  });
  const inputs = freezeObject({
    hours: modelHours,
    timestampsJst,
    barrageOpeningFraction: freezeObject(
      Array.from({ length: SNAPSHOT_COUNT }, () => 0.5),
    ),
  });
  const metadata = freezeObject({
    ...baseData.metadata,
    dataMode: 'reference_v2_fixed_S4_replay',
    sourceStatus: 'SEALED_READ_ONLY_BROWSER_REPLAY',
    sourceLabel: '固定S4基準リプレイ',
    interpretation:
      '未較正・モデル参考値。保存済み37時点の固定S4基準リプレイであり、予測ではありません。',
    classification: '未較正・モデル参考値',
    currentFlowProvenanceClassification: 'reference_v2_fixed_S4_replay',
    currentFlowProvenanceLabelJa: '固定S4基準リプレイ（未較正）',
    replayOnly: true,
    readOnly: true,
    savedTimeSelectionOnly: true,
    lazyLoadRequired: true,
    inputDriven: false,
    fieldGateInputDrivesDisplayedFlow: false,
    automaticGateEstimatorDrivesDisplayedFlow: false,
    physicalCalibrationPassed: false,
    prediction: false,
    productionAdopted: false,
    periodicWrapUsed: false,
    fishwayAlwaysEnabled: true,
    fishwayInstantaneousFlowAvailable: false,
    gateFluxAvailable: false,
    P2InstantaneousHeadsAvailable: false,
    missingValueDisplayTextJa: '値なし',
    gateStage: 4,
    openGates: freezeObject([5, 4, 6, 3]),
    gateCapacityMeaning:
      'classification_face_capacity_multiplier_not_measured_gate_lift',
    capacityFractionByGateId: FIXED_S4_CAPACITY,
    hours: modelHours,
    timestampsJst,
    snapshotCount: SNAPSHOT_COUNT,
    cellCount: CELL_COUNT,
    vertexCount: VERTEX_COUNT,
    meshSha256: EXPECTED_MESH_SHA256,
    responsePackSha256: sidecar.metadata.binarySha256,
    responsePackVersion: 'reference-v2-fixed-S4-read-only',
    sidecarManifestSha256: sidecar.metadata.manifestSha256,
    fieldAvailability: availability,
  });

  return freezeObject({
    ...baseData,
    schema: STAGE20_REFERENCE_V2_DISPLAY_ADAPTER_SCHEMA,
    metadata,
    mesh,
    inputs,
    diagnostics,
    timingsMs: freezeObject({ synthesis: loadMilliseconds }),
    snapshot,
    depthAt,
    eastVelocityAt,
    northVelocityAt,
    geometry: freezeObject({
      vertices: () => sourceGeometry.verticesM.slice(),
      triangles: () => sourceGeometry.triangles.slice(),
      boundaryEdges: () => boundaryEdges.slice(),
    }),
    fieldAvailability: availability,
    availability: availabilityFor,
    displayValue,
    compareGateInput,
    replay: freezeObject({
      absoluteTimeS,
      timestampsJst,
      modelHours,
      completedHours,
      gateCapacities,
      openingOrder: OPENING_ORDER,
      closingOrder: CLOSING_ORDER,
      fishwayAlwaysEnabled: true,
      readOnly: true,
      savedTimeSelectionOnly: true,
      inputDriven: false,
      availability: availabilityFor,
      displayValue,
    }),
  });
}

export async function loadStage20ReferenceV2DisplayData(options = {}) {
  assert(options.baseData, 'baseData is required');
  const started = globalThis.performance?.now?.() ?? Date.now();
  options.onProgress?.('reference-v2-loader-import');
  const module = await import(
    './onga_stage20_reference_v2_sidecar_loader_20260730_l9e4b.mjs'
  );
  options.onProgress?.('reference-v2-sidecar');
  const sidecar = await module.loadStage20ReferenceV2Sidecar({
    baseUrl: options.baseUrl,
    fetchImpl: options.fetchImpl,
    signal: options.signal,
    onProgress: stage => options.onProgress?.(`reference-v2-${stage}`),
  });
  options.onProgress?.('reference-v2-adapter');
  const finished = globalThis.performance?.now?.() ?? Date.now();
  const data = buildStage20ReferenceV2DisplayData({
    baseData: options.baseData,
    sidecar,
    loadMilliseconds: Math.max(0, finished - started),
  });
  options.onProgress?.('reference-v2-ready');
  return data;
}
