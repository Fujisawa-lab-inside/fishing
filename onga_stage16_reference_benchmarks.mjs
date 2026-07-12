export const STAGE16_REFERENCE_BENCHMARK_VERSION = 'stage16-reference-benchmarks-v1';

const DEFAULT_GRAVITY = 9.80665;

function assert(condition, message) {
  if (!condition) throw new Error(`[stage16-benchmark] ${message}`);
}

function finite(value, label) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) throw new TypeError(`${label} must be finite`);
  return numeric;
}

function positive(value, label) {
  const numeric = finite(value, label);
  if (numeric <= 0) throw new RangeError(`${label} must be positive`);
  return numeric;
}

function nonnegative(value, label) {
  const numeric = finite(value, label);
  if (numeric < 0) throw new RangeError(`${label} must be nonnegative`);
  return numeric;
}

export function dryBedDamBreakExact({
  x,
  time,
  leftDepth,
  damLocation = 0,
  gravity = DEFAULT_GRAVITY,
}) {
  const coordinate = finite(x, 'x');
  const t = nonnegative(time, 'time');
  const depth0 = positive(leftDepth, 'leftDepth');
  const origin = finite(damLocation, 'damLocation');
  const g = positive(gravity, 'gravity');
  if (t === 0) {
    return Object.freeze({
      depth: coordinate < origin ? depth0 : 0,
      velocity: 0,
      discharge: 0,
      region: coordinate < origin ? 'left_reservoir' : 'dry_bed',
    });
  }
  const c0 = Math.sqrt(g * depth0);
  const similarity = (coordinate - origin) / t;
  if (similarity <= -c0) {
    return Object.freeze({ depth: depth0, velocity: 0, discharge: 0, region: 'left_reservoir' });
  }
  if (similarity >= 2 * c0) {
    return Object.freeze({ depth: 0, velocity: 0, discharge: 0, region: 'dry_bed' });
  }
  const velocity = (2 / 3) * (c0 + similarity);
  const celerity = (1 / 3) * (2 * c0 - similarity);
  const depth = Math.max(0, celerity * celerity / g);
  return Object.freeze({
    depth,
    velocity,
    discharge: depth * velocity,
    region: 'rarefaction_fan',
  });
}

export function dryBedDamBreakFrontSpeed({ leftDepth, gravity = DEFAULT_GRAVITY }) {
  return 2 * Math.sqrt(positive(gravity, 'gravity') * positive(leftDepth, 'leftDepth'));
}

export function linearStandingWaveExact({
  x,
  time,
  length,
  meanDepth,
  amplitude,
  mode = 1,
  gravity = DEFAULT_GRAVITY,
}) {
  const coordinate = finite(x, 'x');
  const t = finite(time, 'time');
  const basinLength = positive(length, 'length');
  const depth = positive(meanDepth, 'meanDepth');
  const waveAmplitude = finite(amplitude, 'amplitude');
  const modeNumber = Number(mode);
  assert(Number.isInteger(modeNumber) && modeNumber > 0, 'mode must be a positive integer');
  const g = positive(gravity, 'gravity');
  assert(Math.abs(waveAmplitude) < depth, 'amplitude magnitude must be smaller than meanDepth');
  const wavenumber = modeNumber * Math.PI / basinLength;
  const angularFrequency = Math.sqrt(g * depth) * wavenumber;
  const phaseX = wavenumber * coordinate;
  const phaseT = angularFrequency * t;
  const surfacePerturbation = waveAmplitude * Math.cos(phaseX) * Math.cos(phaseT);
  const velocity = waveAmplitude * angularFrequency / (depth * wavenumber)
    * Math.sin(phaseX) * Math.sin(phaseT);
  const waterDepth = depth + surfacePerturbation;
  return Object.freeze({
    depth: waterDepth,
    surfacePerturbation,
    velocity,
    discharge: waterDepth * velocity,
    wavenumber,
    angularFrequency,
    wavePeriod: 2 * Math.PI / angularFrequency,
  });
}

export function lakeAtRestState({ bedElevation, freeSurfaceElevation }) {
  const bed = finite(bedElevation, 'bedElevation');
  const surface = finite(freeSurfaceElevation, 'freeSurfaceElevation');
  const depth = Math.max(0, surface - bed);
  return Object.freeze({ depth, momentumX: 0, momentumY: 0, freeSurfaceElevation: surface });
}

export function manningWideChannelDischargePerWidth({
  depth,
  slope,
  roughness,
}) {
  const h = nonnegative(depth, 'depth');
  const bedSlope = nonnegative(slope, 'slope');
  const n = positive(roughness, 'roughness');
  if (h === 0 || bedSlope === 0) return 0;
  return h ** (5 / 3) * Math.sqrt(bedSlope) / n;
}

export function manningWideChannelNormalDepth({
  dischargePerWidth,
  slope,
  roughness,
}) {
  const discharge = nonnegative(dischargePerWidth, 'dischargePerWidth');
  const bedSlope = positive(slope, 'slope');
  const n = positive(roughness, 'roughness');
  if (discharge === 0) return 0;
  return (discharge * n / Math.sqrt(bedSlope)) ** (3 / 5);
}

export function shallowWaterCharacteristicSpeeds({
  depth,
  normalVelocity,
  gravity = DEFAULT_GRAVITY,
}) {
  const h = nonnegative(depth, 'depth');
  const velocity = finite(normalVelocity, 'normalVelocity');
  const g = positive(gravity, 'gravity');
  const celerity = Math.sqrt(g * h);
  return Object.freeze({
    minus: velocity - celerity,
    plus: velocity + celerity,
    spectralRadius: Math.abs(velocity) + celerity,
  });
}

export function integrateMidpoint({ functionValue, start, end, intervals }) {
  const a = finite(start, 'start');
  const b = finite(end, 'end');
  const count = Number(intervals);
  assert(Number.isInteger(count) && count > 0, 'intervals must be a positive integer');
  assert(typeof functionValue === 'function', 'functionValue must be a function');
  const dx = (b - a) / count;
  let total = 0;
  for (let index = 0; index < count; index += 1) {
    total += finite(functionValue(a + (index + 0.5) * dx), `functionValue[${index}]`);
  }
  return total * dx;
}

export const Stage16ReferenceBenchmarks = Object.freeze({
  version: STAGE16_REFERENCE_BENCHMARK_VERSION,
  dryBedDamBreakExact,
  dryBedDamBreakFrontSpeed,
  linearStandingWaveExact,
  lakeAtRestState,
  manningWideChannelDischargePerWidth,
  manningWideChannelNormalDepth,
  shallowWaterCharacteristicSpeeds,
  integrateMidpoint,
});
