export const STAGE15_WET_DRY_VERSION = 'stage15-wet-dry-hysteresis-v1';

function assert(condition, message) {
  if (!condition) throw new Error(`[stage15-wet-dry] ${message}`);
}

function assertFinite(value, label) {
  if (!Number.isFinite(value)) throw new TypeError(`${label} must be finite`);
}

function isVector(value) {
  return Array.isArray(value) || ArrayBuffer.isView(value);
}

function vector(value, length, label, defaultValue = null) {
  if (value === null || value === undefined) {
    assert(defaultValue !== null, `${label} is required`);
    const output = new Float64Array(length);
    output.fill(defaultValue);
    return output;
  }
  assert(isVector(value) && value.length === length, `${label} length mismatch`);
  return Float64Array.from(value, (entry, index) => {
    const numeric = Number(entry);
    assertFinite(numeric, `${label}[${index}]`);
    return numeric;
  });
}

function flags(value, length, label, defaultValue = 0) {
  if (value === null || value === undefined) {
    const output = new Uint8Array(length);
    output.fill(defaultValue ? 1 : 0);
    return output;
  }
  assert(isVector(value) && value.length === length, `${label} length mismatch`);
  return Uint8Array.from(value, entry => entry ? 1 : 0);
}

function thresholds(wetThreshold, dryThreshold) {
  const wet = Number(wetThreshold);
  const dry = Number(dryThreshold);
  assertFinite(wet, 'wetThreshold');
  assertFinite(dry, 'dryThreshold');
  assert(dry >= 0, 'dryThreshold must be nonnegative');
  assert(wet > dry, 'wetThreshold must be greater than dryThreshold');
  return Object.freeze({ wet, dry });
}

export function updateWetDryFlags({
  depths,
  previousWet = null,
  wetThreshold = 1e-3,
  dryThreshold = 5e-4,
}) {
  assert(isVector(depths), 'depths must be an Array or typed array');
  const h = vector(depths, depths.length, 'depths');
  const limits = thresholds(wetThreshold, dryThreshold);
  const hadPrevious = previousWet !== null && previousWet !== undefined;
  const previous = flags(previousWet, h.length, 'previousWet');
  const wet = new Uint8Array(h.length);
  const newlyWet = new Uint8Array(h.length);
  const newlyDry = new Uint8Array(h.length);

  for (let cell = 0; cell < h.length; cell += 1) {
    assert(h[cell] >= 0, `depths[${cell}] must be nonnegative`);
    const next = hadPrevious
      ? (previous[cell] ? h[cell] > limits.dry : h[cell] >= limits.wet)
      : h[cell] >= limits.wet;
    wet[cell] = next ? 1 : 0;
    newlyWet[cell] = hadPrevious && !previous[cell] && next ? 1 : 0;
    newlyDry[cell] = hadPrevious && previous[cell] && !next ? 1 : 0;
  }

  return Object.freeze({
    version: STAGE15_WET_DRY_VERSION,
    wet,
    newlyWet,
    newlyDry,
    previous,
    thresholds: limits,
  });
}

export function regulariseWetDryState({
  state,
  previousWet = null,
  areas = null,
  wetThreshold = 1e-3,
  dryThreshold = 5e-4,
  velocityDepth = null,
  maxSpeed = 20,
}) {
  const cellCount = state?.h?.length;
  assert(Number.isInteger(cellCount) && cellCount > 0, 'state.h must be a nonempty vector');
  const h = vector(state.h, cellCount, 'state.h');
  const hu = vector(state.hu, cellCount, 'state.hu');
  const hv = vector(state.hv, cellCount, 'state.hv');
  const cellAreas = vector(areas, cellCount, 'areas', 1);
  const limits = thresholds(wetThreshold, dryThreshold);
  const referenceDepth = Number(velocityDepth ?? limits.wet);
  const speedLimit = Number(maxSpeed);
  assertFinite(referenceDepth, 'velocityDepth');
  assertFinite(speedLimit, 'maxSpeed');
  assert(referenceDepth > 0, 'velocityDepth must be positive');
  assert(speedLimit > 0, 'maxSpeed must be positive');
  for (let cell = 0; cell < cellCount; cell += 1) {
    assert(h[cell] >= 0, `state.h[${cell}] must be nonnegative`);
    assert(cellAreas[cell] > 0, `areas[${cell}] must be positive`);
  }

  const classification = updateWetDryFlags({
    depths: h,
    previousWet,
    wetThreshold: limits.wet,
    dryThreshold: limits.dry,
  });
  const next = {
    h: Float64Array.from(h),
    hu: Float64Array.from(hu),
    hv: Float64Array.from(hv),
  };
  let removedVolume = 0;
  let cappedVelocityCells = 0;
  let maximumSpeedBefore = 0;
  let maximumSpeedAfter = 0;

  for (let cell = 0; cell < cellCount; cell += 1) {
    if (!classification.wet[cell]) {
      removedVolume += next.h[cell] * cellAreas[cell];
      next.h[cell] = 0;
      next.hu[cell] = 0;
      next.hv[cell] = 0;
      continue;
    }

    const denominator = Math.max(next.h[cell], referenceDepth);
    let u = next.hu[cell] / denominator;
    let v = next.hv[cell] / denominator;
    const speedBefore = Math.hypot(u, v);
    maximumSpeedBefore = Math.max(maximumSpeedBefore, speedBefore);
    if (speedBefore > speedLimit) {
      const scale = speedLimit / speedBefore;
      u *= scale;
      v *= scale;
      cappedVelocityCells += 1;
    }
    const speedAfter = Math.hypot(u, v);
    maximumSpeedAfter = Math.max(maximumSpeedAfter, speedAfter);
    next.hu[cell] = next.h[cell] * u;
    next.hv[cell] = next.h[cell] * v;
  }

  return Object.freeze({
    version: STAGE15_WET_DRY_VERSION,
    state: Object.freeze(next),
    classification,
    diagnostics: Object.freeze({
      removedVolume,
      newlyWetCells: classification.newlyWet.reduce((sum, value) => sum + value, 0),
      newlyDryCells: classification.newlyDry.reduce((sum, value) => sum + value, 0),
      wetCells: classification.wet.reduce((sum, value) => sum + value, 0),
      cappedVelocityCells,
      maximumSpeedBefore,
      maximumSpeedAfter,
      maximumPossibleThresholdRemoval: cellAreas.reduce(
        (sum, area, cell) => sum + (classification.wet[cell] ? 0 : limits.wet * area),
        0,
      ),
    }),
  });
}

export function wetCellMaskToIndices(wet) {
  assert(isVector(wet), 'wet must be an Array or typed array');
  const indices = [];
  for (let cell = 0; cell < wet.length; cell += 1) {
    if (wet[cell]) indices.push(cell);
  }
  return Object.freeze(indices);
}
