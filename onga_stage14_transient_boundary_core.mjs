import { validateGraph } from './onga_stage14_conservative_flux_core.mjs';

export const STAGE14_TRANSIENT_VERSION = 'stage14-transient-boundary-core-v1';

function assertFinite(value, label) {
  if (!Number.isFinite(value)) throw new TypeError(`${label} must be finite`);
}

function isVector(value) {
  return Array.isArray(value) || ArrayBuffer.isView(value);
}

function normaliseVector(value, length, label, { positive = false } = {}) {
  if (!isVector(value) || value.length !== length) {
    throw new RangeError(`${label} length does not match cellCount`);
  }
  return Float64Array.from(value, (entry, index) => {
    const numeric = Number(entry);
    assertFinite(numeric, `${label}[${index}]`);
    if (positive && numeric <= 0) throw new RangeError(`${label}[${index}] must be positive`);
    return numeric;
  });
}

function resolveScalar(specification, time, context, label) {
  const value = typeof specification === 'function'
    ? specification(time, context)
    : specification;
  const numeric = Number(value);
  assertFinite(numeric, label);
  return numeric;
}

function resolveSources(specification, cellCount, time, context) {
  if (specification === null || specification === undefined) return new Float64Array(cellCount);
  const resolved = typeof specification === 'function'
    ? specification(time, context)
    : specification;
  return normaliseVector(resolved, cellCount, 'sources');
}

function normaliseBoundaries(boundaries, cellCount) {
  if (!Array.isArray(boundaries)) throw new TypeError('boundaries must be an array');
  return boundaries.map((boundary, index) => {
    const cell = Number(boundary.cell);
    if (!Number.isInteger(cell) || cell < 0 || cell >= cellCount) {
      throw new RangeError(`boundary ${index} has an invalid cell`);
    }
    const type = String(boundary.type || '');
    if (type !== 'dirichlet' && type !== 'flux') {
      throw new TypeError(`boundary ${index} type must be dirichlet or flux`);
    }
    if (boundary.value === undefined) throw new TypeError(`boundary ${index} value is required`);
    let conductance = 0;
    if (type === 'dirichlet') {
      conductance = Number(boundary.conductance);
      assertFinite(conductance, `boundary ${index} conductance`);
      if (conductance < 0) throw new RangeError(`boundary ${index} conductance must be nonnegative`);
    }
    return Object.freeze({
      id: boundary.id ?? `boundary-${index}`,
      cell,
      type,
      value: boundary.value,
      conductance,
    });
  });
}

function effectiveGraph({ cellCount, edges, edgeMultipliers, time, context }) {
  const graph = validateGraph({ cellCount, edges });
  if (edgeMultipliers !== null && edgeMultipliers !== undefined
    && (!isVector(edgeMultipliers) || edgeMultipliers.length !== graph.length)) {
    throw new RangeError('edgeMultipliers length does not match edges');
  }
  return graph.map((edge, index) => {
    const multiplierSpec = edgeMultipliers === null || edgeMultipliers === undefined
      ? 1
      : edgeMultipliers[index];
    const multiplier = resolveScalar(multiplierSpec, time, context, `edgeMultipliers[${index}]`);
    if (multiplier < 0) throw new RangeError(`edgeMultipliers[${index}] must be nonnegative`);
    return Object.freeze({
      ...edge,
      multiplier,
      effectiveTransmissibility: edge.transmissibility * multiplier,
    });
  });
}

export function evaluateSemiDiscrete({
  cellCount,
  edges,
  field,
  capacities,
  boundaries = [],
  sources = null,
  edgeMultipliers = null,
  time = 0,
  context = {},
}) {
  assertFinite(Number(time), 'time');
  const values = normaliseVector(field, cellCount, 'field');
  const cellCapacities = normaliseVector(capacities, cellCount, 'capacities', { positive: true });
  const graph = effectiveGraph({ cellCount, edges, edgeMultipliers, time: Number(time), context });
  const boundaryDefinitions = normaliseBoundaries(boundaries, cellCount);
  const sourceValues = resolveSources(sources, cellCount, Number(time), context);
  const netOutwardFlux = new Float64Array(cellCount);

  const internalFluxes = graph.map(edge => {
    const fluxLeftToRight = edge.effectiveTransmissibility
      * (values[edge.left] - values[edge.right]);
    netOutwardFlux[edge.left] += fluxLeftToRight;
    netOutwardFlux[edge.right] -= fluxLeftToRight;
    return Object.freeze({ ...edge, fluxLeftToRight });
  });

  const boundaryFluxes = boundaryDefinitions.map(boundary => {
    const prescribedValue = resolveScalar(
      boundary.value,
      Number(time),
      { ...context, boundary },
      `boundary ${boundary.id} value`,
    );
    const outwardFlux = boundary.type === 'dirichlet'
      ? boundary.conductance * (values[boundary.cell] - prescribedValue)
      : prescribedValue;
    netOutwardFlux[boundary.cell] += outwardFlux;
    return Object.freeze({ ...boundary, prescribedValue, outwardFlux });
  });

  const derivative = new Float64Array(cellCount);
  const conservativeRhs = new Float64Array(cellCount);
  let sourceTotal = 0;
  let boundaryOutwardTotal = 0;
  for (let index = 0; index < cellCount; index += 1) {
    conservativeRhs[index] = sourceValues[index] - netOutwardFlux[index];
    derivative[index] = conservativeRhs[index] / cellCapacities[index];
    sourceTotal += sourceValues[index];
  }
  for (const boundary of boundaryFluxes) boundaryOutwardTotal += boundary.outwardFlux;

  return Object.freeze({
    version: STAGE14_TRANSIENT_VERSION,
    time: Number(time),
    field: values,
    capacities: cellCapacities,
    sourceValues,
    internalFluxes,
    boundaryFluxes,
    netOutwardFlux,
    conservativeRhs,
    derivative,
    sourceTotal,
    boundaryOutwardTotal,
    massRate: sourceTotal - boundaryOutwardTotal,
  });
}

function assertTimeStep(dt) {
  const numeric = Number(dt);
  assertFinite(numeric, 'dt');
  if (numeric <= 0) throw new RangeError('dt must be positive');
  return numeric;
}

export function advanceEuler(options) {
  const dt = assertTimeStep(options.dt);
  const evaluation = evaluateSemiDiscrete(options);
  const nextField = Float64Array.from(
    evaluation.field,
    (value, index) => value + dt * evaluation.derivative[index],
  );
  return Object.freeze({
    method: 'euler',
    time: evaluation.time,
    nextTime: evaluation.time + dt,
    dt,
    nextField,
    stages: Object.freeze([evaluation]),
  });
}

export function advanceHeun(options) {
  const dt = assertTimeStep(options.dt);
  const first = evaluateSemiDiscrete(options);
  const predictor = Float64Array.from(
    first.field,
    (value, index) => value + dt * first.derivative[index],
  );
  const second = evaluateSemiDiscrete({
    ...options,
    field: predictor,
    time: first.time + dt,
  });
  const nextField = Float64Array.from(
    first.field,
    (value, index) => value + 0.5 * dt * (first.derivative[index] + second.derivative[index]),
  );
  return Object.freeze({
    method: 'heun',
    time: first.time,
    nextTime: first.time + dt,
    dt,
    nextField,
    stages: Object.freeze([first, second]),
  });
}

export function totalMass(field, capacities) {
  if (!isVector(field) || !isVector(capacities) || field.length !== capacities.length) {
    throw new RangeError('field and capacities must have equal lengths');
  }
  let total = 0;
  for (let index = 0; index < field.length; index += 1) {
    const value = Number(field[index]);
    const capacity = Number(capacities[index]);
    assertFinite(value, `field[${index}]`);
    assertFinite(capacity, `capacities[${index}]`);
    if (capacity <= 0) throw new RangeError(`capacities[${index}] must be positive`);
    total += value * capacity;
  }
  return total;
}

export function estimateExplicitStableDt({
  cellCount,
  edges,
  capacities,
  boundaries = [],
  edgeMultipliers = null,
  time = 0,
  context = {},
  safety = 0.9,
}) {
  const safetyFactor = Number(safety);
  assertFinite(safetyFactor, 'safety');
  if (!(safetyFactor > 0 && safetyFactor <= 1)) throw new RangeError('safety must be in (0, 1]');
  const cellCapacities = normaliseVector(capacities, cellCount, 'capacities', { positive: true });
  const graph = effectiveGraph({ cellCount, edges, edgeMultipliers, time: Number(time), context });
  const boundaryDefinitions = normaliseBoundaries(boundaries, cellCount);
  const diagonal = new Float64Array(cellCount);
  for (const edge of graph) {
    diagonal[edge.left] += edge.effectiveTransmissibility;
    diagonal[edge.right] += edge.effectiveTransmissibility;
  }
  for (const boundary of boundaryDefinitions) {
    if (boundary.type === 'dirichlet') diagonal[boundary.cell] += boundary.conductance;
  }
  let stableDt = Infinity;
  for (let index = 0; index < cellCount; index += 1) {
    if (diagonal[index] > 0) {
      stableDt = Math.min(stableDt, safetyFactor * cellCapacities[index] / diagonal[index]);
    }
  }
  return stableDt;
}

export const Stage14TransientBoundaryCore = Object.freeze({
  version: STAGE14_TRANSIENT_VERSION,
  evaluateSemiDiscrete,
  advanceEuler,
  advanceHeun,
  totalMass,
  estimateExplicitStableDt,
});
