export const STAGE14_LINEAR_SOLVER_VERSION = 'stage14-matrix-free-pcg-v1';

function assert(condition, message) {
  if (!condition) throw new Error(`[stage14-pcg] ${message}`);
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

function normaliseEdges(cellCount, edges, edgeMultipliers = null) {
  assert(Number.isInteger(cellCount) && cellCount > 0, 'cellCount must be a positive integer');
  assert(Array.isArray(edges), 'edges must be an array');
  if (edgeMultipliers !== null) {
    assert(isVector(edgeMultipliers) && edgeMultipliers.length === edges.length, 'edgeMultipliers length mismatch');
  }
  return edges.map((edge, index) => {
    const left = Number(edge.left);
    const right = Number(edge.right);
    const transmissibility = Number(edge.transmissibility);
    assert(Number.isInteger(left) && Number.isInteger(right), `edge ${index} cell ids must be integers`);
    assert(left >= 0 && left < cellCount && right >= 0 && right < cellCount && left !== right,
      `edge ${index} cell ids are invalid`);
    assertFinite(transmissibility, `edge ${index} transmissibility`);
    assert(transmissibility >= 0, `edge ${index} transmissibility must be nonnegative`);
    const multiplier = edgeMultipliers === null ? 1 : Number(edgeMultipliers[index]);
    assertFinite(multiplier, `edgeMultipliers[${index}]`);
    assert(multiplier >= 0, `edgeMultipliers[${index}] must be nonnegative`);
    return Object.freeze({ left, right, conductance: transmissibility * multiplier });
  });
}

function normaliseBoundaries(cellCount, boundaries) {
  assert(Array.isArray(boundaries), 'boundaries must be an array');
  return boundaries.map((boundary, index) => {
    const cell = Number(boundary.cell);
    const type = String(boundary.type || '');
    assert(Number.isInteger(cell) && cell >= 0 && cell < cellCount, `boundary ${index} cell is invalid`);
    assert(type === 'dirichlet' || type === 'flux', `boundary ${index} type is invalid`);
    const value = Number(boundary.value);
    assertFinite(value, `boundary ${index} value`);
    let conductance = 0;
    if (type === 'dirichlet') {
      conductance = Number(boundary.conductance);
      assertFinite(conductance, `boundary ${index} conductance`);
      assert(conductance >= 0, `boundary ${index} conductance must be nonnegative`);
    }
    return Object.freeze({ id: boundary.id ?? `boundary-${index}`, cell, type, value, conductance });
  });
}

export function buildSteadySystem({
  cellCount,
  edges,
  edgeMultipliers = null,
  boundaries = [],
  sources = null,
  anchor = null,
}) {
  const graph = normaliseEdges(cellCount, edges, edgeMultipliers);
  const boundaryDefinitions = normaliseBoundaries(cellCount, boundaries);
  const sourceValues = vector(sources, cellCount, 'sources', 0);
  const diagonal = new Float64Array(cellCount);
  const rhs = Float64Array.from(sourceValues);

  for (const edge of graph) {
    diagonal[edge.left] += edge.conductance;
    diagonal[edge.right] += edge.conductance;
  }
  let dirichletConductance = 0;
  for (const boundary of boundaryDefinitions) {
    if (boundary.type === 'dirichlet') {
      diagonal[boundary.cell] += boundary.conductance;
      rhs[boundary.cell] += boundary.conductance * boundary.value;
      dirichletConductance += boundary.conductance;
    } else {
      rhs[boundary.cell] -= boundary.value;
    }
  }

  let anchorDefinition = null;
  if (anchor !== null) {
    const cell = Number(anchor.cell);
    const value = Number(anchor.value ?? 0);
    assert(Number.isInteger(cell) && cell >= 0 && cell < cellCount, 'anchor cell is invalid');
    assertFinite(value, 'anchor value');
    anchorDefinition = Object.freeze({ cell, value });
    diagonal[cell] = 1;
    rhs[cell] = value;
  } else {
    assert(dirichletConductance > 0, 'a Dirichlet boundary or anchor is required for a unique solution');
  }

  for (let cell = 0; cell < cellCount; cell += 1) {
    assert(Number.isFinite(diagonal[cell]) && diagonal[cell] > 0, `system diagonal is nonpositive at cell ${cell}`);
  }

  function apply(input, output = new Float64Array(cellCount)) {
    assert(isVector(input) && input.length === cellCount, 'operator input length mismatch');
    output.fill(0);
    for (const edge of graph) {
      const difference = Number(input[edge.left]) - Number(input[edge.right]);
      assertFinite(difference, 'operator field difference');
      const flux = edge.conductance * difference;
      output[edge.left] += flux;
      output[edge.right] -= flux;
    }
    for (const boundary of boundaryDefinitions) {
      if (boundary.type === 'dirichlet') output[boundary.cell] += boundary.conductance * Number(input[boundary.cell]);
    }
    if (anchorDefinition) output[anchorDefinition.cell] = Number(input[anchorDefinition.cell]);
    return output;
  }

  return Object.freeze({
    version: STAGE14_LINEAR_SOLVER_VERSION,
    cellCount,
    graph,
    boundaries: boundaryDefinitions,
    diagonal,
    rhs,
    anchor: anchorDefinition,
    apply,
  });
}

function dot(left, right) {
  let total = 0;
  for (let index = 0; index < left.length; index += 1) total += left[index] * right[index];
  return total;
}

function norm2(values) {
  return Math.sqrt(Math.max(0, dot(values, values)));
}

export function solvePcg(system, options = {}) {
  const n = system.cellCount;
  const maxIterations = Number(options.maxIterations ?? Math.max(100, Math.min(10000, n * 2)));
  const relativeTolerance = Number(options.relativeTolerance ?? 1e-10);
  const absoluteTolerance = Number(options.absoluteTolerance ?? 1e-12);
  assert(Number.isInteger(maxIterations) && maxIterations > 0, 'maxIterations must be a positive integer');
  assertFinite(relativeTolerance, 'relativeTolerance');
  assertFinite(absoluteTolerance, 'absoluteTolerance');
  assert(relativeTolerance >= 0 && absoluteTolerance >= 0, 'tolerances must be nonnegative');

  const x = vector(options.initialGuess, n, 'initialGuess', 0);
  const Ax = system.apply(x);
  const residual = new Float64Array(n);
  const preconditioned = new Float64Array(n);
  const direction = new Float64Array(n);
  const product = new Float64Array(n);
  for (let cell = 0; cell < n; cell += 1) {
    residual[cell] = system.rhs[cell] - Ax[cell];
    preconditioned[cell] = residual[cell] / system.diagonal[cell];
    direction[cell] = preconditioned[cell];
  }

  const rhsNorm = norm2(system.rhs);
  const threshold = Math.max(absoluteTolerance, relativeTolerance * Math.max(rhsNorm, 1));
  let residualNorm = norm2(residual);
  const initialResidualNorm = residualNorm;
  if (residualNorm <= threshold) {
    return Object.freeze({ solution: x, converged: true, iterations: 0, residualNorm, initialResidualNorm, threshold });
  }

  let rz = dot(residual, preconditioned);
  assert(rz > 0 && Number.isFinite(rz), 'initial preconditioned residual is invalid');
  let iterations = 0;
  let converged = false;

  for (iterations = 1; iterations <= maxIterations; iterations += 1) {
    system.apply(direction, product);
    const denominator = dot(direction, product);
    assert(denominator > 0 && Number.isFinite(denominator), `PCG lost positive definiteness at iteration ${iterations}`);
    const alpha = rz / denominator;
    for (let cell = 0; cell < n; cell += 1) {
      x[cell] += alpha * direction[cell];
      residual[cell] -= alpha * product[cell];
    }
    residualNorm = norm2(residual);
    if (residualNorm <= threshold) {
      converged = true;
      break;
    }
    for (let cell = 0; cell < n; cell += 1) preconditioned[cell] = residual[cell] / system.diagonal[cell];
    const nextRz = dot(residual, preconditioned);
    assert(nextRz > 0 && Number.isFinite(nextRz), `preconditioned residual is invalid at iteration ${iterations}`);
    const beta = nextRz / rz;
    for (let cell = 0; cell < n; cell += 1) direction[cell] = preconditioned[cell] + beta * direction[cell];
    rz = nextRz;
  }

  return Object.freeze({
    solution: x,
    converged,
    iterations: Math.min(iterations, maxIterations),
    residualNorm,
    initialResidualNorm,
    threshold,
  });
}

export function computeBoundaryFluxes(system, field) {
  assert(isVector(field) && field.length === system.cellCount, 'field length mismatch');
  return system.boundaries.map(boundary => Object.freeze({
    id: boundary.id,
    cell: boundary.cell,
    type: boundary.type,
    outwardFlux: boundary.type === 'dirichlet'
      ? boundary.conductance * (Number(field[boundary.cell]) - boundary.value)
      : boundary.value,
  }));
}

export function residualVector(system, field) {
  const applied = system.apply(field);
  return Float64Array.from(applied, (value, index) => value - system.rhs[index]);
}

export function maxAbs(values) {
  let maximum = 0;
  for (const value of values) maximum = Math.max(maximum, Math.abs(Number(value)));
  return maximum;
}
