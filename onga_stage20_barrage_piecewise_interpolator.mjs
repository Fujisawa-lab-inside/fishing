export const STAGE20_BARRAGE_PIECEWISE_PACK_SCHEMA =
  'onga-stage20-barrage-piecewise-anchor-pack-v1';
export const STAGE20_BARRAGE_PIECEWISE_VERSION =
  'stage20-barrage-piecewise-browser-candidate-v1';

const REQUIRED_STATUS =
  'code_only_piecewise_candidate_not_physical_validation_not_public_simulator';
const REQUIRED_PACK_VERSION = 'stage20-barrage-piecewise-anchor-pack-v1';
const REQUIRED_MANIFEST_SHA256 =
  'f5770256962268f2e6e4a1bec2a124fada55568d3e4ab0fe74269bbf3f0eecbc';
const REQUIRED_PACK_SHA256 =
  'd3a0b315d7fb3bf17c04a4715b1595242b501a50dacc163ae8716013ed638047';
const REQUIRED_MESH_SHA256 =
  '09dd7e6b667fcdb334ec6db8daa72851d8cba78b7a823ca828980ec0a5ed7659';
const REQUIRED_ANALYSIS_SHA256 =
  '82ce4ece4dda010b846204266e604c01d26eaffba041bd4b04329a353fc834c2';
const REQUIRED_RESULT_SHA256 =
  'fe4be9be3112eafff9965abc68bf254c78d560344c99cb2d5f31e1e75af519ab';
const EXPECTED_OPENINGS = Object.freeze([0, 0.5, 1]);
const EXPECTED_HOURS = Object.freeze([-12, -11, -10, -9, -8]);
const EXPECTED_COMPONENTS = Object.freeze([
  'waterDepthM',
  'velocityUms',
  'velocityVms',
]);

function assert(condition, message) {
  if (!condition) {
    throw new Error(`[stage20-barrage-piecewise] ${message}`);
  }
}

function product(values) {
  return values.reduce((result, value) => result * value, 1);
}

function hex(bytes) {
  return Array.from(
    new Uint8Array(bytes),
    value => value.toString(16).padStart(2, '0'),
  ).join('');
}

async function sha256(buffer) {
  assert(globalThis.crypto?.subtle, 'Web Crypto SHA-256 is unavailable');
  return hex(await globalThis.crypto.subtle.digest('SHA-256', buffer));
}

function exactArray(actual, expected, label) {
  assert(Array.isArray(actual), `${label} must be an array`);
  assert(
    actual.length === expected.length
      && actual.every((value, index) => value === expected[index]),
    `${label} mismatch`,
  );
}

function parseManifest(manifestText) {
  assert(typeof manifestText === 'string', 'manifest payload must be text');
  try {
    const manifest = JSON.parse(manifestText);
    assert(
      manifest && typeof manifest === 'object' && !Array.isArray(manifest),
      'manifest JSON root must be an object',
    );
    return manifest;
  } catch (error) {
    throw new Error(
      `[stage20-barrage-piecewise] invalid manifest JSON: ${String(error)}`,
    );
  }
}

function openingWeights(openingFraction) {
  assert(
    typeof openingFraction === 'number' && Number.isFinite(openingFraction),
    'opening fraction must be one finite scalar number',
  );
  assert(
    openingFraction >= 0 && openingFraction <= 1,
    'opening fraction extrapolation is forbidden',
  );
  if (openingFraction === 0) {
    return Object.freeze({
      segmentId: 'anchor-0',
      lowerAnchorIndex: 0,
      upperAnchorIndex: 0,
      lowerAnchorFraction: 0,
      upperAnchorFraction: 0,
      lowerWeight: 1,
      upperWeight: 0,
      exactAnchor: true,
    });
  }
  if (openingFraction === 0.5) {
    return Object.freeze({
      segmentId: 'anchor-50',
      lowerAnchorIndex: 1,
      upperAnchorIndex: 1,
      lowerAnchorFraction: 0.5,
      upperAnchorFraction: 0.5,
      lowerWeight: 1,
      upperWeight: 0,
      exactAnchor: true,
    });
  }
  if (openingFraction === 1) {
    return Object.freeze({
      segmentId: 'anchor-100',
      lowerAnchorIndex: 2,
      upperAnchorIndex: 2,
      lowerAnchorFraction: 1,
      upperAnchorFraction: 1,
      lowerWeight: 1,
      upperWeight: 0,
      exactAnchor: true,
    });
  }
  if (openingFraction < 0.5) {
    const upperWeight = openingFraction * 2;
    return Object.freeze({
      segmentId: 'opening-0-to-50',
      lowerAnchorIndex: 0,
      upperAnchorIndex: 1,
      lowerAnchorFraction: 0,
      upperAnchorFraction: 0.5,
      lowerWeight: 1 - upperWeight,
      upperWeight,
      exactAnchor: false,
    });
  }
  const upperWeight = openingFraction * 2 - 1;
  return Object.freeze({
    segmentId: 'opening-50-to-100',
    lowerAnchorIndex: 1,
    upperAnchorIndex: 2,
    lowerAnchorFraction: 0.5,
    upperAnchorFraction: 1,
    lowerWeight: 1 - upperWeight,
    upperWeight,
    exactAnchor: false,
  });
}

export function stage20BarragePiecewiseWeights(openingFraction) {
  return openingWeights(openingFraction);
}

export async function decodeStage20BarragePiecewisePack(
  manifestText,
  buffer,
) {
  assert(
    await sha256(new TextEncoder().encode(manifestText))
      === REQUIRED_MANIFEST_SHA256,
    'manifest SHA-256 mismatch',
  );
  const manifest = parseManifest(manifestText);
  assert(
    manifest?.schema === STAGE20_BARRAGE_PIECEWISE_PACK_SCHEMA,
    'manifest schema mismatch',
  );
  assert(manifest.status === REQUIRED_STATUS, 'pack status mismatch');
  assert(manifest.version === REQUIRED_PACK_VERSION, 'pack version mismatch');
  assert(
    manifest.binary?.sha256 === REQUIRED_PACK_SHA256,
    'pack identity mismatch',
  );
  assert(
    manifest.mesh?.binarySha256 === REQUIRED_MESH_SHA256,
    'mesh identity mismatch',
  );
  assert(
    manifest.sourceAnalysis?.sha256 === REQUIRED_ANALYSIS_SHA256,
    'source analysis identity mismatch',
  );
  assert(
    manifest.sourceDecision?.sha256 === REQUIRED_RESULT_SHA256,
    'source decision identity mismatch',
  );
  assert(
    manifest.scope?.supportedUse ===
      'inactive_browser_candidate_consistency_and_visual_review_only',
    'pack use scope mismatch',
  );
  assert(
    manifest.scope?.boundaryInputs?.M ===
      'approved_fixed_relative_tide_trajectory_from_source_runs'
      && manifest.scope?.boundaryInputs?.NDischargeM3S === 2
      && manifest.scope?.boundaryInputs?.ODischargeM3S === 35
      && manifest.scope?.boundaryInputs?.GDischargeM3S === 1,
    'boundary-input identity mismatch',
  );
  assert(buffer instanceof ArrayBuffer, 'payload must be an ArrayBuffer');
  assert(
    buffer.byteLength === manifest.binary?.byteLength,
    'payload byte length mismatch',
  );
  assert(
    await sha256(buffer) === REQUIRED_PACK_SHA256,
    'payload SHA-256 mismatch',
  );
  exactArray(
    manifest.openingContract?.anchorFractions,
    EXPECTED_OPENINGS,
    'opening anchors',
  );
  assert(
    manifest.openingContract?.inputKind ===
      'one_scalar_constant_for_all_five_hours',
    'time-varying opening input is forbidden',
  );
  assert(
    manifest.openingContract?.timeVaryingScheduleAllowed === false,
    'time-varying opening schedule must remain forbidden',
  );
  assert(
    manifest.openingContract?.extrapolationAllowed === false,
    'opening extrapolation must remain forbidden',
  );
  exactArray(
    manifest.timeContract?.anchorHours,
    EXPECTED_HOURS,
    'model-hour anchors',
  );
  assert(
    manifest.timeContract?.timeInterpolationAllowed === false,
    'time interpolation must remain forbidden',
  );
  assert(
    manifest.timeContract?.timeExtrapolationAllowed === false,
    'time extrapolation must remain forbidden',
  );
  exactArray(manifest.componentOrder, EXPECTED_COMPONENTS, 'component order');

  const descriptor = manifest.arrays?.anchors;
  assert(descriptor?.dtype === 'float32-le', 'anchor dtype mismatch');
  assert(
    Array.isArray(descriptor.shape) && descriptor.shape.length === 4,
    'anchor shape must be rank 4',
  );
  const [openingCount, hourCount, componentCount, cellCount] =
    descriptor.shape;
  assert(
    openingCount === EXPECTED_OPENINGS.length
      && hourCount === EXPECTED_HOURS.length
      && componentCount === EXPECTED_COMPONENTS.length,
    'anchor axis inventory mismatch',
  );
  assert(
    cellCount === manifest.mesh?.cellCount && cellCount === 50199,
    'mesh cell count mismatch',
  );
  assert(
    Number.isInteger(descriptor.byteOffset)
      && descriptor.byteOffset >= 0
      && descriptor.byteOffset % Float32Array.BYTES_PER_ELEMENT === 0,
    'anchor byte offset is invalid',
  );
  const length = product(descriptor.shape);
  assert(
    descriptor.byteLength === length * Float32Array.BYTES_PER_ELEMENT,
    'anchor byte length mismatch',
  );
  assert(
    descriptor.sha256 === manifest.binary?.sha256,
    'anchor and payload SHA-256 records differ',
  );
  assert(
    descriptor.byteOffset + descriptor.byteLength <= buffer.byteLength,
    'anchor array exceeds payload',
  );
  return Object.freeze({
    manifest: Object.freeze(manifest),
    buffer,
    anchors: new Float32Array(buffer, descriptor.byteOffset, length),
    openingCount,
    hourCount,
    componentCount,
    cellCount,
    hours: EXPECTED_HOURS,
    openingFractions: EXPECTED_OPENINGS,
  });
}

export async function loadStage20BarragePiecewisePack(
  manifestUrl,
  options = {},
) {
  const fetchImpl = options.fetchImpl ?? globalThis.fetch;
  assert(typeof fetchImpl === 'function', 'fetch is unavailable');
  const manifestResponse = await fetchImpl(manifestUrl, { cache: 'no-store' });
  assert(
    manifestResponse.ok,
    `manifest fetch failed with HTTP ${manifestResponse.status}`,
  );
  const manifestText = await manifestResponse.text();
  assert(
    await sha256(new TextEncoder().encode(manifestText))
      === REQUIRED_MANIFEST_SHA256,
    'manifest SHA-256 mismatch',
  );
  const manifest = parseManifest(manifestText);
  const base = manifestResponse.url || String(manifestUrl);
  const binaryUrl = new URL(manifest.binary.url, base).href;
  const binaryResponse = await fetchImpl(binaryUrl, { cache: 'no-store' });
  assert(
    binaryResponse.ok,
    `binary fetch failed with HTTP ${binaryResponse.status}`,
  );
  const buffer = await binaryResponse.arrayBuffer();
  return await decodeStage20BarragePiecewisePack(manifestText, buffer);
}

export function interpolateStage20BarrageFiveHourFields(
  pack,
  openingFraction,
) {
  assert(
    pack?.anchors instanceof Float32Array,
    'decoded anchor pack is required',
  );
  const weights = openingWeights(openingFraction);
  const anchorStride = pack.hourCount * pack.componentCount * pack.cellCount;
  const lowerOffset = weights.lowerAnchorIndex * anchorStride;
  const upperOffset = weights.upperAnchorIndex * anchorStride;
  let fields;
  if (weights.exactAnchor) {
    fields = pack.anchors.slice(lowerOffset, lowerOffset + anchorStride);
  } else {
    fields = new Float32Array(anchorStride);
    for (let index = 0; index < anchorStride; index += 1) {
      fields[index] =
        pack.anchors[lowerOffset + index] * weights.lowerWeight
        + pack.anchors[upperOffset + index] * weights.upperWeight;
    }
  }

  let minimumDepthM = Infinity;
  let maximumDepthM = -Infinity;
  let maximumSpeedMPS = 0;
  let nonFiniteValueCount = 0;
  let negativeDepthCount = 0;
  const snapshotStride = pack.componentCount * pack.cellCount;
  for (let hourIndex = 0; hourIndex < pack.hourCount; hourIndex += 1) {
    const snapshotOffset = hourIndex * snapshotStride;
    const depthOffset = snapshotOffset;
    const eastOffset = snapshotOffset + pack.cellCount;
    const northOffset = snapshotOffset + 2 * pack.cellCount;
    for (let cell = 0; cell < pack.cellCount; cell += 1) {
      const depth = fields[depthOffset + cell];
      const east = fields[eastOffset + cell];
      const north = fields[northOffset + cell];
      if (
        !Number.isFinite(depth)
        || !Number.isFinite(east)
        || !Number.isFinite(north)
      ) {
        nonFiniteValueCount += 1;
        continue;
      }
      if (depth < 0) negativeDepthCount += 1;
      minimumDepthM = Math.min(minimumDepthM, depth);
      maximumDepthM = Math.max(maximumDepthM, depth);
      maximumSpeedMPS = Math.max(
        maximumSpeedMPS,
        Math.hypot(east, north),
      );
    }
  }
  assert(nonFiniteValueCount === 0, 'interpolation produced non-finite values');
  assert(negativeDepthCount === 0, 'interpolation produced negative depth');
  return Object.freeze({
    version: STAGE20_BARRAGE_PIECEWISE_VERSION,
    openingFraction,
    ...weights,
    hours: pack.hours,
    snapshotCount: pack.hourCount,
    componentCount: pack.componentCount,
    componentOrder: Object.freeze([...EXPECTED_COMPONENTS]),
    cellCount: pack.cellCount,
    fields,
    diagnostics: Object.freeze({
      minimumDepthM,
      maximumDepthM,
      maximumSpeedMPS,
      nonFiniteValueCount,
      negativeDepthCount,
    }),
    interpretation:
      'code_only_piecewise_candidate_not_physical_or_forecast_validation',
  });
}

export function stage20BarrageSnapshotViews(result, hourIndex) {
  assert(
    Number.isInteger(hourIndex)
      && hourIndex >= 0
      && hourIndex < result.snapshotCount,
    'hour index is invalid',
  );
  const snapshotStride = result.componentCount * result.cellCount;
  const start = hourIndex * snapshotStride;
  return Object.freeze({
    hour: result.hours[hourIndex],
    waterDepthM: result.fields.subarray(start, start + result.cellCount),
    velocityUms: result.fields.subarray(
      start + result.cellCount,
      start + 2 * result.cellCount,
    ),
    velocityVms: result.fields.subarray(
      start + 2 * result.cellCount,
      start + 3 * result.cellCount,
    ),
  });
}
