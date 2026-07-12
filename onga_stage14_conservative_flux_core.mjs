export const STAGE14_CORE_VERSION = 'stage14-conservative-flux-core-v1';

function assertFinite(value, label) {
  if (!Number.isFinite(value)) throw new TypeError(`${label} must be finite`);
}

export function validateGraph({ cellCount, edges }) {
  if (!Number.isInteger(cellCount) || cellCount <= 0) {
    throw new TypeError('cellCount must be a positive integer');
  }
  if (!Array.isArray(edges)) throw new TypeError('edges must be an array');
  return edges.map((edge, index) => {
    const left = Number(edge.left);
    const right = Number(edge.right);
    const transmissibility = Number(edge.transmissibility);
    if (!Number.isInteger(left) || !Number.isInteger(right)) {
      throw new TypeError(`edge ${index} cell ids must be integers`);
    }
    if (left < 0 || left >= cellCount || right < 0 || right >= cellCount || left === right) {
      throw new RangeError(`edge ${index} has invalid cell ids`);
    }
    assertFinite(transmissibility, `edge ${index} transmissibility`);
    if (transmissibility < 0) throw new RangeError(`edge ${index} transmissibility must be nonnegative`);
    return Object.freeze({ left, right, transmissibility });
  });
}

export function computeInternalFluxes({ cellCount, edges, field }) {
  const graph = validateGraph({ cellCount, edges });
  if (!Array.isArray(field) && !(field instanceof Float64Array)) {
    throw new TypeError('field must be an Array or Float64Array');
  }
  if (field.length !== cellCount) throw new RangeError('field length does not match cellCount');
  const values = Float64Array.from(field, (value, index) => {
    const numeric = Number(value);
    assertFinite(numeric, `field[${index}]`);
    return numeric;
  });
  return graph.map(edge => ({
    ...edge,
    fluxLeftToRight: edge.transmissibility * (values[edge.left] - values[edge.right]),
  }));
}

export function accumulateCellResidual({ cellCount, edges, field, sources = null }) {
  const fluxes = computeInternalFluxes({ cellCount, edges, field });
  const residual = new Float64Array(cellCount);
  for (const edge of fluxes) {
    residual[edge.left] += edge.fluxLeftToRight;
    residual[edge.right] -= edge.fluxLeftToRight;
  }
  if (sources !== null) {
    if ((!Array.isArray(sources) && !(sources instanceof Float64Array)) || sources.length !== cellCount) {
      throw new RangeError('sources length does not match cellCount');
    }
    for (let index = 0; index < cellCount; index += 1) {
      const source = Number(sources[index]);
      assertFinite(source, `sources[${index}]`);
      residual[index] -= source;
    }
  }
  return residual;
}

export function sum(values) {
  let total = 0;
  for (const value of values) {
    assertFinite(Number(value), 'summand');
    total += Number(value);
  }
  return total;
}

export function maxAbs(values) {
  let maximum = 0;
  for (const value of values) maximum = Math.max(maximum, Math.abs(Number(value)));
  return maximum;
}

export function reverseField(field, constant = 1) {
  assertFinite(Number(constant), 'constant');
  return Array.from(field, value => Number(constant) - Number(value));
}

export const Stage14ConservativeFluxCore = Object.freeze({
  version: STAGE14_CORE_VERSION,
  validateGraph,
  computeInternalFluxes,
  accumulateCellResidual,
  sum,
  maxAbs,
  reverseField,
});
