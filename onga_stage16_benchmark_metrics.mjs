export const STAGE16_BENCHMARK_METRICS_VERSION = 'stage16-benchmark-metrics-v1';

function assert(condition, message) {
  if (!condition) throw new Error(`[stage16-metrics] ${message}`);
}

function vector(value, label) {
  assert(Array.isArray(value) || ArrayBuffer.isView(value), `${label} must be a vector`);
  return Array.from(value, (entry, index) => {
    const numeric = Number(entry);
    if (!Number.isFinite(numeric)) throw new TypeError(`${label}[${index}] must be finite`);
    return numeric;
  });
}

function positiveWeights(weights, length) {
  if (weights === null || weights === undefined) return Array(length).fill(1);
  const values = vector(weights, 'weights');
  assert(values.length === length, 'weights length mismatch');
  values.forEach((weight, index) => assert(weight > 0, `weights[${index}] must be positive`));
  return values;
}

export function weightedErrorNorms({ numerical, reference, weights = null }) {
  const computed = vector(numerical, 'numerical');
  const exact = vector(reference, 'reference');
  assert(computed.length === exact.length && computed.length > 0, 'field lengths must match and be nonzero');
  const cellWeights = positiveWeights(weights, computed.length);
  let weightedAbsolute = 0;
  let weightedSquared = 0;
  let weightSum = 0;
  let maximum = 0;
  for (let index = 0; index < computed.length; index += 1) {
    const error = Math.abs(computed[index] - exact[index]);
    const weight = cellWeights[index];
    weightedAbsolute += weight * error;
    weightedSquared += weight * error * error;
    weightSum += weight;
    maximum = Math.max(maximum, error);
  }
  return Object.freeze({
    l1: weightedAbsolute / weightSum,
    l2: Math.sqrt(weightedSquared / weightSum),
    linf: maximum,
    weightSum,
    sampleCount: computed.length,
  });
}

export function relativeConservationError({ initial, final, expectedChange = 0, scale = null }) {
  const initialValue = Number(initial);
  const finalValue = Number(final);
  const change = Number(expectedChange);
  assert([initialValue, finalValue, change].every(Number.isFinite), 'conservation values must be finite');
  const residual = finalValue - initialValue - change;
  const denominator = scale === null
    ? Math.max(1, Math.abs(initialValue), Math.abs(finalValue), Math.abs(change))
    : Math.abs(Number(scale));
  assert(Number.isFinite(denominator) && denominator > 0, 'conservation scale must be positive');
  return Object.freeze({ residual, relativeError: Math.abs(residual) / denominator, scale: denominator });
}

export function observedConvergenceOrders({ cellSizes, errors }) {
  const h = vector(cellSizes, 'cellSizes');
  const e = vector(errors, 'errors');
  assert(h.length === e.length && h.length >= 2, 'at least two matching resolutions are required');
  for (let index = 0; index < h.length; index += 1) {
    assert(h[index] > 0, `cellSizes[${index}] must be positive`);
    assert(e[index] > 0, `errors[${index}] must be positive`);
    if (index > 0) assert(h[index] < h[index - 1], 'cellSizes must be strictly decreasing');
  }
  return Object.freeze(h.slice(0, -1).map((coarse, index) => (
    Math.log(e[index] / e[index + 1]) / Math.log(coarse / h[index + 1])
  )));
}

export function detectWettingFront({ coordinates, depths, threshold = 1e-8, direction = 'maximum' }) {
  const x = vector(coordinates, 'coordinates');
  const h = vector(depths, 'depths');
  assert(x.length === h.length && x.length > 0, 'coordinate and depth lengths must match');
  const dryThreshold = Number(threshold);
  assert(Number.isFinite(dryThreshold) && dryThreshold >= 0, 'threshold must be nonnegative');
  const wet = x.filter((_, index) => h[index] > dryThreshold);
  if (wet.length === 0) return null;
  if (direction === 'maximum') return Math.max(...wet);
  if (direction === 'minimum') return Math.min(...wet);
  throw new TypeError('direction must be maximum or minimum');
}

export function standingWaveProjection({
  coordinates,
  surfacePerturbation,
  length,
  mode = 1,
  weights = null,
}) {
  const x = vector(coordinates, 'coordinates');
  const eta = vector(surfacePerturbation, 'surfacePerturbation');
  assert(x.length === eta.length && x.length > 0, 'coordinate and field lengths must match');
  const basinLength = Number(length);
  const modeNumber = Number(mode);
  assert(Number.isFinite(basinLength) && basinLength > 0, 'length must be positive');
  assert(Number.isInteger(modeNumber) && modeNumber > 0, 'mode must be a positive integer');
  const cellWeights = positiveWeights(weights, x.length);
  const wavenumber = modeNumber * Math.PI / basinLength;
  let numerator = 0;
  let denominator = 0;
  let meanNumerator = 0;
  let weightSum = 0;
  for (let index = 0; index < x.length; index += 1) {
    const basis = Math.cos(wavenumber * x[index]);
    const weight = cellWeights[index];
    numerator += weight * eta[index] * basis;
    denominator += weight * basis * basis;
    meanNumerator += weight * eta[index];
    weightSum += weight;
  }
  assert(denominator > 0, 'standing-wave basis is unresolved');
  return Object.freeze({
    amplitude: numerator / denominator,
    weightedMean: meanNumerator / weightSum,
    wavenumber,
  });
}

export function compareFrontPosition({ numericalFront, referenceFront, characteristicLength }) {
  const numerical = Number(numericalFront);
  const reference = Number(referenceFront);
  const length = Number(characteristicLength);
  assert([numerical, reference, length].every(Number.isFinite), 'front-position values must be finite');
  assert(length > 0, 'characteristicLength must be positive');
  const absoluteError = Math.abs(numerical - reference);
  return Object.freeze({ absoluteError, normalizedError: absoluteError / length });
}

export function assessBenchmark(checks) {
  assert(Array.isArray(checks) && checks.length > 0, 'checks must be a nonempty array');
  const normalized = checks.map((entry, index) => {
    assert(entry && typeof entry === 'object', `check ${index} must be an object`);
    return Object.freeze({
      name: String(entry.name ?? `check-${index}`),
      value: entry.value,
      criterion: String(entry.criterion ?? ''),
      ok: entry.ok === true,
    });
  });
  return Object.freeze({
    status: normalized.every(entry => entry.ok) ? 'passed' : 'failed',
    passed: normalized.filter(entry => entry.ok).length,
    total: normalized.length,
    checks: Object.freeze(normalized),
  });
}

export const Stage16BenchmarkMetrics = Object.freeze({
  version: STAGE16_BENCHMARK_METRICS_VERSION,
  weightedErrorNorms,
  relativeConservationError,
  observedConvergenceOrders,
  detectWettingFront,
  standingWaveProjection,
  compareFrontPosition,
  assessBenchmark,
});
