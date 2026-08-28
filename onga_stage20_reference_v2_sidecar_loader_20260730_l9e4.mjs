export const STAGE20_REFERENCE_V2_SIDECAR_LOADER_SCHEMA =
  'onga-stage20-reference-v2-sidecar-loader-20260730-l9e4-v1';

const SIDECAR_SCHEMA =
  'onga-stage20-reference-v2-browser-sidecar-20260730-s8a1-v1';
const SIDECAR_DIRECTORY =
  './docs/results/stage20-reference-v2-browser-sidecar-20260730-s8a1-v1/';
const EXPECTED_MANIFEST = Object.freeze({
  byteLength: 30127,
  sha256: 'b2b0779ea0e08b620521fb64f72db5737465758361e47770b8a0d3efef350d3c',
});
const EXPECTED_BINARY = Object.freeze({
  byteLength: 17518480,
  sha256: 'd6d226b054869cde0f1a865a5fe524982a48ec92f5f400cc20ef846a7d443822',
});
const EXPECTED_MESH_SHA256 =
  '7f3e84b73fab3bff1ba4699dbf9b1299159c40e91d042376046a6fe99fc03164';
const EXPECTED_ARRAYS = Object.freeze({
  verticesM: Object.freeze({
    byteOffset: 0,
    byteLength: 316336,
    dtype: 'float64',
    shape: Object.freeze([19771, 2]),
    sha256: 'e57970856c3670f6e3128ce6d4d97f6abd1f8a77ea3c839372c30a9feea90ec4',
  }),
  triangles: Object.freeze({
    byteOffset: 316336,
    byteLength: 452688,
    dtype: 'int32',
    shape: Object.freeze([37724, 3]),
    sha256: 'f4e191ae546e5d4ae19840f408c25c1630337b61bd619d24290f0c927680b0e9',
  }),
  depthM: Object.freeze({
    byteOffset: 769024,
    byteLength: 5583152,
    dtype: 'float32',
    shape: Object.freeze([37, 37724]),
    sha256: '19c2660b5dd9724bac497be7fedaa1fc4a23935370b6c0712ee0b3c496cb9f5b',
  }),
  eastVelocityMPS: Object.freeze({
    byteOffset: 6352176,
    byteLength: 5583152,
    dtype: 'float32',
    shape: Object.freeze([37, 37724]),
    sha256: '608b63a81fdd7492325b4e589d07a9242177c0f57d709531d09826b506ab9cc0',
  }),
  northVelocityMPS: Object.freeze({
    byteOffset: 11935328,
    byteLength: 5583152,
    dtype: 'float32',
    shape: Object.freeze([37, 37724]),
    sha256: '89b718ecf850459b1b53980b36b35e5c03667546b98bd35a0696cfd09ca0c14f',
  }),
});
const ARRAY_ORDER = Object.freeze(Object.keys(EXPECTED_ARRAYS));
const AVAILABLE_FIELDS = Object.freeze([
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
  'upstreamP2HeadM',
]);
const TOP_LEVEL_KEYS = Object.freeze([
  'adapter',
  'arrays',
  'availableFields',
  'binary',
  'classification',
  'labels',
  'mesh',
  'runtimePolicy',
  'scenario',
  'schema',
  'source',
  'status',
  'timeline',
  'transform',
  'unavailableNotFabricated',
  'version',
]);
const TYPE_CONSTRUCTORS = Object.freeze({
  float32: Float32Array,
  float64: Float64Array,
  int32: Int32Array,
});

function fail(message) {
  throw new Error(`[stage20-reference-v2-sidecar] ${message}`);
}

function assert(condition, message) {
  if (!condition) fail(message);
}

function sameJson(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function exactKeys(value, expected) {
  return value !== null
    && typeof value === 'object'
    && sameJson(Object.keys(value).sort(), [...expected].sort());
}

function deepFreeze(value) {
  if (value === null || typeof value !== 'object' || Object.isFrozen(value)) return value;
  Object.freeze(value);
  for (const child of Object.values(value)) deepFreeze(child);
  return value;
}

function bytesToHex(bytes) {
  return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
}

async function sha256(payload) {
  assert(
    globalThis.crypto?.subtle,
    'Web Crypto SHA-256 is unavailable; package identity cannot be verified',
  );
  return bytesToHex(
    new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256', payload)),
  );
}

async function fetchArrayBuffer(url, signal, fetchImpl) {
  const response = await fetchImpl(url, { cache: 'no-store', signal });
  assert(response?.ok === true, `${url} returned HTTP ${response?.status ?? 'unknown'}`);
  return response.arrayBuffer();
}

function assertLittleEndian() {
  const word = new Uint16Array([0x1234]);
  assert(new Uint8Array(word.buffer)[0] === 0x34, 'little-endian runtime is required');
}

function assertExactTimeline(timeline) {
  const modelHours = Array.from({ length: 37 }, (_, index) => index - 12);
  const completedHours = Array.from({ length: 37 }, (_, index) => index + 12);
  assert(
    timeline?.snapshotCount === 37
      && timeline?.intervalHours === 1
      && timeline?.interpolationAllowed === false
      && sameJson(timeline?.modelHours, modelHours)
      && sameJson(timeline?.completedHours, completedHours)
      && Array.isArray(timeline?.timestampsJst)
      && timeline.timestampsJst.length === 37,
    '37-point saved-only timeline changed',
  );
  for (let index = 0; index < timeline.timestampsJst.length; index += 1) {
    const timestamp = timeline.timestampsJst[index];
    assert(
      typeof timestamp === 'string' && timestamp.endsWith('+09:00'),
      `timestamp ${index} is not an explicit JST instant`,
    );
    if (index > 0) {
      const difference = Date.parse(timestamp) - Date.parse(timeline.timestampsJst[index - 1]);
      assert(difference === 3600000, `timestamp ${index} is not one hour after its predecessor`);
    }
  }
}

function assertExactArrayDescriptors(manifest) {
  assert(
    exactKeys(manifest?.arrays, ARRAY_ORDER),
    'array set changed; auxiliary quantities must not be added or omitted',
  );
  assert(
    sameJson(manifest?.binary?.arrayOrder, ARRAY_ORDER),
    'binary array order changed',
  );
  let expectedOffset = 0;
  for (const name of ARRAY_ORDER) {
    const actual = manifest.arrays[name];
    const expected = EXPECTED_ARRAYS[name];
    assert(
      actual?.byteOffset === expected.byteOffset
        && actual?.byteLength === expected.byteLength
        && actual?.dtype === expected.dtype
        && sameJson(actual?.shape, expected.shape)
        && actual?.sha256 === expected.sha256,
      `${name} descriptor changed`,
    );
    assert(actual.byteOffset === expectedOffset, `${name} is not contiguous`);
    expectedOffset += actual.byteLength;
  }
  assert(expectedOffset === EXPECTED_BINARY.byteLength, 'array ranges do not cover the binary');
}

export function validateStage20ReferenceV2SidecarManifest(manifest) {
  assert(exactKeys(manifest, TOP_LEVEL_KEYS), 'manifest top-level schema changed');
  assert(
    manifest?.schema === SIDECAR_SCHEMA
      && manifest?.version === 1
      && manifest?.status === 'SEALED_READ_ONLY_BROWSER_REPLAY',
    'sealed S8A1 sidecar identity changed',
  );
  assert(manifest?.classification === '未較正・モデル参考値', 'classification changed');
  assert(
    manifest?.labels?.classification === '未較正・モデル参考値'
      && manifest?.labels?.scenario === '固定S4基準リプレイ'
      && manifest?.labels?.tide === '連続49点・周期折返しなし'
      && manifest?.labels?.prediction === '予測ではありません'
      && manifest?.labels?.inputMode === '保存済み時刻のみ・入力非駆動',
    'required caution labels changed',
  );
  assert(
    sameJson(manifest?.availableFields, AVAILABLE_FIELDS)
      && sameJson(manifest?.unavailableNotFabricated, UNAVAILABLE_FIELDS),
    'available/unavailable field declaration changed',
  );
  assert(
    manifest?.mesh?.sha256 === EXPECTED_MESH_SHA256
      && manifest?.mesh?.cellCount === 37724
      && manifest?.mesh?.vertexCount === 19771
      && manifest?.mesh?.cellOrderArray === 'triangles'
      && manifest?.mesh?.cellOrderSha256 === EXPECTED_ARRAYS.triangles.sha256
      && manifest?.mesh?.geometryMutationAllowed === false
      && manifest?.mesh?.cellReorderingAllowed === false,
    'R1C mesh binding changed',
  );
  assert(
    manifest?.binary?.format === 'little_endian_raw_array_concatenation'
      && manifest?.binary?.byteLength === EXPECTED_BINARY.byteLength
      && manifest?.binary?.sha256 === EXPECTED_BINARY.sha256,
    'binary binding changed',
  );
  assertExactArrayDescriptors(manifest);
  assertExactTimeline(manifest?.timeline);
  assert(
    manifest?.scenario?.id === 'fixed_S4_reference_replay'
      && manifest?.scenario?.gateStage === 4
      && sameJson(manifest?.scenario?.openGates, [5, 4, 6, 3])
      && sameJson(
        manifest?.scenario?.capacityByGateId1To8,
        [0, 0, 1, 1, 1, 1, 0, 0],
      )
      && manifest?.scenario?.periodicWrapUsed === false
      && manifest?.scenario?.tideMode === 'direct_49_point_piecewise_linear_no_wrap'
      && manifest?.scenario?.fishway === 'always_enabled',
    'fixed S4/no-wrap scenario changed',
  );
  assert(
    manifest?.runtimePolicy?.replayOnly === true
      && manifest?.runtimePolicy?.savedTimeSelectionOnly === true
      && manifest?.runtimePolicy?.fieldInputDrivesFlow === false
      && manifest?.runtimePolicy?.automaticGateEstimatorDrivesFlow === false
      && manifest?.runtimePolicy?.directExistingGuiConnectionAuthorized === false
      && manifest?.runtimePolicy?.publicOrMainAdoptionAuthorized === false,
    'read-only opt-in runtime policy changed',
  );
  assert(
    manifest?.transform?.browserDtype === 'float32'
      && manifest?.transform?.negativeDepthAllowed === false
      && manifest?.transform?.nonFiniteAllowed === false
      && manifest?.transform?.dryDepthCutoffM === 1e-8
      && manifest?.transform?.dryRule?.eastVelocityMPS === 0
      && manifest?.transform?.dryRule?.northVelocityMPS === 0,
    'field transformation safety contract changed',
  );
  assert(
    manifest?.source?.postcompletionStatus === 'PASS'
      && manifest?.source?.postcompletionCheckCount === 705
      && Array.isArray(manifest?.source?.commitChain)
      && manifest.source.commitChain.length === 49
      && Array.isArray(manifest?.source?.selectedCheckpointSha256)
      && manifest.source.selectedCheckpointSha256.length === 37,
    'finalized source evidence changed',
  );
  return deepFreeze(manifest);
}

function shapeLength(shape) {
  return shape.reduce((product, value) => product * value, 1);
}

async function parseAndVerifyArrays(manifest, payload) {
  assertLittleEndian();
  assert(payload instanceof ArrayBuffer, 'binary response is not an ArrayBuffer');
  assert(payload.byteLength === EXPECTED_BINARY.byteLength, 'binary byte length changed');
  assert(await sha256(payload) === EXPECTED_BINARY.sha256, 'binary SHA-256 changed');

  const arrays = {};
  for (const name of ARRAY_ORDER) {
    const descriptor = manifest.arrays[name];
    const Constructor = TYPE_CONSTRUCTORS[descriptor.dtype];
    assert(Constructor, `${name} dtype is unsupported`);
    const count = shapeLength(descriptor.shape);
    assert(
      descriptor.byteLength === count * Constructor.BYTES_PER_ELEMENT,
      `${name} shape and byte length differ`,
    );
    const bytes = new Uint8Array(
      payload,
      descriptor.byteOffset,
      descriptor.byteLength,
    ).slice();
    assert(await sha256(bytes.buffer) === descriptor.sha256, `${name} SHA-256 changed`);
    arrays[name] = new Constructor(bytes.buffer);
  }

  const { verticesM, triangles, depthM, eastVelocityMPS, northVelocityMPS } = arrays;
  for (let index = 0; index < verticesM.length; index += 1) {
    assert(Number.isFinite(verticesM[index]), `verticesM contains non-finite value at ${index}`);
  }
  for (let index = 0; index < triangles.length; index += 1) {
    assert(
      triangles[index] >= 0 && triangles[index] < 19771,
      `triangles contains invalid vertex index at ${index}`,
    );
  }
  for (let index = 0; index < depthM.length; index += 1) {
    const depth = depthM[index];
    const east = eastVelocityMPS[index];
    const north = northVelocityMPS[index];
    assert(
      Number.isFinite(depth) && Number.isFinite(east) && Number.isFinite(north),
      `field contains non-finite value at ${index}`,
    );
    assert(depth >= 0, `depthM contains negative value at ${index}`);
    if (depth <= 1e-8) {
      assert(
        east === 0 && north === 0,
        `dry cell contains non-zero velocity at ${index}`,
      );
    }
  }
  return arrays;
}

function createFieldAvailability() {
  const metadata = {};
  for (const name of AVAILABLE_FIELDS) {
    metadata[name] = Object.freeze({
      available: true,
      source: 'sealed S8A1 primitive field',
    });
  }
  for (const name of UNAVAILABLE_FIELDS) {
    metadata[name] = Object.freeze({
      available: false,
      source: null,
      reason:
        'S8A1 source checkpoint does not contain this instantaneous auxiliary quantity; no value was fabricated.',
    });
  }
  return Object.freeze(metadata);
}

function createDataInterface(manifest, arrays, identity) {
  const cellCount = 37724;
  const snapshotCount = 37;
  const fieldAvailability = createFieldAvailability();
  const timeline = Object.freeze({
    modelHours: Object.freeze([...manifest.timeline.modelHours]),
    completedHours: Object.freeze([...manifest.timeline.completedHours]),
    timestampsJst: Object.freeze([...manifest.timeline.timestampsJst]),
    snapshotCount,
    intervalHours: 1,
    interpolationAllowed: false,
  });
  const metadata = Object.freeze({
    schema: STAGE20_REFERENCE_V2_SIDECAR_LOADER_SCHEMA,
    dataMode: 'reference_v2_sealed_read_only_replay',
    classification: '未較正・モデル参考値',
    sourceLabel: '固定S4基準リプレイ',
    interpretation:
      '連続49点・周期折返しなしの保存済み時刻だけを表示します。予測ではありません。',
    replayOnly: true,
    readOnly: true,
    savedTimeSelectionOnly: true,
    fieldInputDrivesDisplayedFlow: false,
    automaticGateEstimatorDrivesDisplayedFlow: false,
    physicalCalibrationPassed: false,
    productionAdopted: false,
    periodicWrapUsed: false,
    gateStage: 4,
    openGates: Object.freeze([5, 4, 6, 3]),
    cellCount,
    vertexCount: 19771,
    snapshotCount,
    modelHourStart: -12,
    modelHourEnd: 24,
    meshSha256: EXPECTED_MESH_SHA256,
    manifestSha256: identity.manifestSha256,
    binarySha256: identity.binarySha256,
    fieldAvailability,
  });

  function assertSnapshotIndex(index) {
    assert(
      Number.isInteger(index) && index >= 0 && index < snapshotCount,
      'snapshot index must be an integer from 0 through 36',
    );
  }

  function snapshot(index) {
    assertSnapshotIndex(index);
    const start = index * cellCount;
    const end = start + cellCount;
    return Object.freeze({
      index,
      modelHour: timeline.modelHours[index],
      completedHour: timeline.completedHours[index],
      timestampJst: timeline.timestampsJst[index],
      depthM: arrays.depthM.slice(start, end),
      eastVelocityMPS: arrays.eastVelocityMPS.slice(start, end),
      northVelocityMPS: arrays.northVelocityMPS.slice(start, end),
    });
  }

  function snapshotByModelHour(modelHour) {
    assert(
      Number.isInteger(modelHour),
      'only exact saved integer model hours are available; interpolation is forbidden',
    );
    const index = modelHour + 12;
    assert(
      index >= 0 && index < snapshotCount,
      'model hour must be one of the saved hours -12 through 24',
    );
    return snapshot(index);
  }

  function geometry() {
    return Object.freeze({
      crs: 'EPSG:32652',
      meshSha256: EXPECTED_MESH_SHA256,
      verticesM: arrays.verticesM.slice(),
      triangles: arrays.triangles.slice(),
      vertexCount: 19771,
      cellCount,
      cellOrderPreserved: true,
    });
  }

  function availability(name) {
    assert(
      Object.hasOwn(fieldAvailability, name),
      `unknown field ${String(name)} has no declared availability`,
    );
    return fieldAvailability[name];
  }

  function unavailable(name) {
    const descriptor = availability(name);
    assert(descriptor.available === false, `${name} is an available primitive field`);
    return Object.freeze({ name, ...descriptor });
  }

  return Object.freeze({
    metadata,
    timeline,
    fieldAvailability,
    geometry,
    snapshot,
    snapshotByModelHour,
    availability,
    unavailable,
  });
}

export async function loadStage20ReferenceV2Sidecar(options = {}) {
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  assert(typeof fetchImpl === 'function', 'fetch implementation is unavailable');
  const baseUrl = options.baseUrl
    ? new URL(options.baseUrl, import.meta.url)
    : new URL(SIDECAR_DIRECTORY, import.meta.url);
  const manifestUrl = new URL('manifest.json', baseUrl).href;
  const binaryUrl = new URL('replay-fields.bin', baseUrl).href;

  options.onProgress?.('manifest');
  const manifestPayload = await fetchArrayBuffer(manifestUrl, options.signal, fetchImpl);
  assert(
    manifestPayload.byteLength === EXPECTED_MANIFEST.byteLength,
    'manifest byte length changed',
  );
  const manifestSha256 = await sha256(manifestPayload);
  assert(manifestSha256 === EXPECTED_MANIFEST.sha256, 'manifest SHA-256 changed');
  let manifest;
  try {
    manifest = JSON.parse(new TextDecoder().decode(manifestPayload));
  } catch {
    fail('manifest is not valid JSON');
  }
  validateStage20ReferenceV2SidecarManifest(manifest);

  options.onProgress?.('binary');
  const binaryPayload = await fetchArrayBuffer(binaryUrl, options.signal, fetchImpl);
  const arrays = await parseAndVerifyArrays(manifest, binaryPayload);
  options.onProgress?.('verified');
  return createDataInterface(manifest, arrays, {
    manifestSha256,
    binarySha256: EXPECTED_BINARY.sha256,
  });
}
