import { buildSteadySystem, solvePcg } from './onga_stage14_matrix_free_solver.mjs';

export const STAGE14_IMPLICIT_VERSION = 'stage14-implicit-theta-integrator-v1';

function assert(condition, message) {
  if (!condition) throw new Error(`[stage14-implicit] ${message}`);
}

function assertFinite(value, label) {
  if (!Number.isFinite(value)) throw new TypeError(`${label} must be finite`);
}

function isVector(value) {
  return Array.isArray(value) || ArrayBuffer.isView(value);
}

function vector(value, length, label) {
  assert(isVector(value) && value.length === length, `${label} length mismatch`);
  return Float64Array.from(value, (entry, index) => {
    const numeric = Number(entry);
    assertFinite(numeric, `${label}[${index}]`);
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

function resolveVector(specification, length, time, context, label, defaultValue = 0) {
  if (specification === null || specification === undefined) {
    const output = new Float64Array(length);
    output.fill(defaultValue);
    return output;
  }
  const resolved = typeof specification === 'function'
    ? specification(time, context)
    : specification;
  return vector(resolved, length, label);
}

function resolveBoundaries(boundaries, time, context) {
  assert(Array.isArray(boundaries), 'boundaries must be an array');
  return boundaries.map((boundary, index) => ({
    ...boundary,
    value: resolveScalar(boundary.value, time, { ...context, boundary }, `boundary ${index} value`),
    conductance: boundary.type === 'dirichlet'
      ? resolveScalar(boundary.conductance, time, { ...context, boundary }, `boundary ${index} conductance`)
      : 0,
  }));
}

function resolveEdgeMultipliers(specification, edgeCount, time, context) {
  if (specification === null || specification === undefined) return null;
  const resolved = typeof specification === 'function'
    ? specification(time, context)
    : specification;
  assert(isVector(resolved) && resolved.length === edgeCount, 'edgeMultipliers length mismatch');
  return Float64Array.from(resolved, (entry, index) => {
    const value = typeof entry === 'function' ? entry(time, context) : entry;
    const numeric = Number(value);
    assertFinite(numeric, `edgeMultipliers[${index}]`);
    assert(numeric >= 0, `edgeMultipliers[${index}] must be nonnegative`);
    return numeric;
  });
}

function steadyAt(options, time) {
  return buildSteadySystem({
    cellCount: options.cellCount,
    edges: options.edges,
    edgeMultipliers: resolveEdgeMultipliers(options.edgeMultipliers, options.edges.length, time, options.context || {}),
    boundaries: resolveBoundaries(options.boundaries || [], time, options.context || {}),
    sources: resolveVector(options.sources, options.cellCount, time, options.context || {}, 'sources', 0),
    allowSingular: true,
  });
}

export function advanceTheta(options) {
  const cellCount = Number(options.cellCount);
  assert(Number.isInteger(cellCount) && cellCount > 0, 'cellCount must be a positive integer');
  const dt = Number(options.dt);
  const theta = Number(options.theta);
  const time = Number(options.time ?? 0);
  assertFinite(dt, 'dt');
  assertFinite(theta, 'theta');
  assertFinite(time, 'time');
  assert(dt > 0, 'dt must be positive');
  assert(theta >= 0.5 && theta <= 1, 'theta must be in [0.5, 1]');

  const field = vector(options.field, cellCount, 'field');
  const capacities = vector(options.capacities, cellCount, 'capacities');
  for (let cell = 0; cell < cellCount; cell += 1) assert(capacities[cell] > 0, `capacities[${cell}] must be positive`);

  const oldSystem = steadyAt(options, time);
  const newSystem = steadyAt(options, time + dt);
  const oldApplied = oldSystem.apply(field);
  const massDiagonal = Float64Array.from(capacities, capacity => capacity / dt);
  const diagonal = Float64Array.from(massDiagonal, (value, cell) => value + theta * newSystem.diagonal[cell]);
  const rhs = new Float64Array(cellCount);
  for (let cell = 0; cell < cellCount; cell += 1) {
    rhs[cell] = massDiagonal[cell] * field[cell]
      - (1 - theta) * oldApplied[cell]
      + (1 - theta) * oldSystem.rhs[cell]
      + theta * newSystem.rhs[cell];
  }

  const combined = Object.freeze({
    cellCount,
    diagonal,
    rhs,
    apply(input, output = new Float64Array(cellCount)) {
      const diffusion = newSystem.apply(input);
      for (let cell = 0; cell < cellCount; cell += 1) {
        output[cell] = massDiagonal[cell] * Number(input[cell]) + theta * diffusion[cell];
      }
      return output;
    },
  });

  const solve = solvePcg(combined, {
    initialGuess: options.initialGuess ?? field,
    relativeTolerance: options.relativeTolerance ?? 1e-10,
    absoluteTolerance: options.absoluteTolerance ?? 1e-12,
    maxIterations: options.maxIterations,
  });
  assert(solve.converged, `implicit PCG did not converge in ${solve.iterations} iterations`);

  return Object.freeze({
    version: STAGE14_IMPLICIT_VERSION,
    method: theta === 1 ? 'backward-euler' : theta === 0.5 ? 'crank-nicolson' : 'theta',
    theta,
    time,
    nextTime: time + dt,
    dt,
    nextField: solve.solution,
    solve,
    oldSystem,
    newSystem,
  });
}

export function advanceBackwardEuler(options) {
  return advanceTheta({ ...options, theta: 1 });
}

export function advanceCrankNicolson(options) {
  return advanceTheta({ ...options, theta: 0.5 });
}

export function totalMass(field, capacities) {
  assert(isVector(field) && isVector(capacities) && field.length === capacities.length,
    'field and capacities length mismatch');
  let total = 0;
  for (let cell = 0; cell < field.length; cell += 1) {
    const value = Number(field[cell]);
    const capacity = Number(capacities[cell]);
    assertFinite(value, `field[${cell}]`);
    assertFinite(capacity, `capacities[${cell}]`);
    assert(capacity > 0, `capacities[${cell}] must be positive`);
    total += value * capacity;
  }
  return total;
}

export function integrateImplicit(options) {
  const steps = Number(options.steps);
  assert(Number.isInteger(steps) && steps >= 0, 'steps must be a nonnegative integer');
  let field = vector(options.field, options.cellCount, 'field');
  let time = Number(options.time ?? 0);
  const history = [{ time, field: Float64Array.from(field) }];
  for (let step = 0; step < steps; step += 1) {
    const result = advanceTheta({ ...options, field, time });
    field = result.nextField;
    time = result.nextTime;
    history.push({ time, field: Float64Array.from(field), solve: result.solve });
  }
  return Object.freeze({ time, field, history });
}
