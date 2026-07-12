export const STAGE15_SWE_FLUX_VERSION = 'stage15-shallow-water-rusanov-v1';

function assert(condition, message) {
  if (!condition) throw new Error(`[stage15-swe] ${message}`);
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

function normal(nx, ny, label = 'normal') {
  const x = Number(nx);
  const y = Number(ny);
  assertFinite(x, `${label}.x`);
  assertFinite(y, `${label}.y`);
  const magnitude = Math.hypot(x, y);
  assert(magnitude > 0, `${label} has zero length`);
  return Object.freeze({ nx: x / magnitude, ny: y / magnitude });
}

export function normaliseConserved(state, options = {}) {
  const minimumDepth = Number(options.minimumDepth ?? 1e-8);
  assertFinite(minimumDepth, 'minimumDepth');
  assert(minimumDepth >= 0, 'minimumDepth must be nonnegative');
  const h = Number(state?.h);
  const hu = Number(state?.hu ?? 0);
  const hv = Number(state?.hv ?? 0);
  assertFinite(h, 'state.h');
  assertFinite(hu, 'state.hu');
  assertFinite(hv, 'state.hv');
  assert(h >= 0, 'state.h must be nonnegative');
  if (h <= minimumDepth) return Object.freeze({ h: 0, hu: 0, hv: 0 });
  return Object.freeze({ h, hu, hv });
}

export function primitive(state, options = {}) {
  const conserved = normaliseConserved(state, options);
  if (conserved.h === 0) return Object.freeze({ ...conserved, u: 0, v: 0 });
  return Object.freeze({
    ...conserved,
    u: conserved.hu / conserved.h,
    v: conserved.hv / conserved.h,
  });
}

export function physicalNormalFlux(state, nx, ny, options = {}) {
  const gravity = Number(options.gravity ?? 9.80665);
  assertFinite(gravity, 'gravity');
  assert(gravity > 0, 'gravity must be positive');
  const unit = normal(nx, ny);
  const q = primitive(state, options);
  if (q.h === 0) return Object.freeze({ mass: 0, momentumX: 0, momentumY: 0, waveSpeed: 0 });
  const normalVelocity = q.u * unit.nx + q.v * unit.ny;
  const pressure = 0.5 * gravity * q.h * q.h;
  const mass = q.h * normalVelocity;
  const momentumX = q.hu * normalVelocity + pressure * unit.nx;
  const momentumY = q.hv * normalVelocity + pressure * unit.ny;
  return Object.freeze({
    mass,
    momentumX,
    momentumY,
    waveSpeed: Math.abs(normalVelocity) + Math.sqrt(gravity * q.h),
    normalVelocity,
  });
}

export function rusanovFlux(leftState, rightState, nx, ny, options = {}) {
  const unit = normal(nx, ny);
  const left = normaliseConserved(leftState, options);
  const right = normaliseConserved(rightState, options);
  const leftFlux = physicalNormalFlux(left, unit.nx, unit.ny, options);
  const rightFlux = physicalNormalFlux(right, unit.nx, unit.ny, options);
  const signalSpeed = Math.max(leftFlux.waveSpeed, rightFlux.waveSpeed);
  return Object.freeze({
    mass: 0.5 * (leftFlux.mass + rightFlux.mass) - 0.5 * signalSpeed * (right.h - left.h),
    momentumX: 0.5 * (leftFlux.momentumX + rightFlux.momentumX)
      - 0.5 * signalSpeed * (right.hu - left.hu),
    momentumY: 0.5 * (leftFlux.momentumY + rightFlux.momentumY)
      - 0.5 * signalSpeed * (right.hv - left.hv),
    signalSpeed,
  });
}

export function reflectiveGhostState(state, nx, ny, options = {}) {
  const unit = normal(nx, ny);
  const q = normaliseConserved(state, options);
  const normalMomentum = q.hu * unit.nx + q.hv * unit.ny;
  return Object.freeze({
    h: q.h,
    hu: q.hu - 2 * normalMomentum * unit.nx,
    hv: q.hv - 2 * normalMomentum * unit.ny,
  });
}

function normaliseFaces(cellCount, faces) {
  assert(Array.isArray(faces), 'faces must be an array');
  return Object.freeze(faces.map((face, index) => {
    const left = Number(face.left);
    const right = Number(face.right);
    const length = Number(face.length);
    assert(Number.isInteger(left) && Number.isInteger(right), `face ${index} cell ids must be integers`);
    assert(left >= 0 && left < cellCount && right >= 0 && right < cellCount && left !== right,
      `face ${index} cell ids are invalid`);
    assertFinite(length, `face ${index} length`);
    assert(length > 0, `face ${index} length must be positive`);
    const unit = normal(face.nx, face.ny, `face ${index} normal`);
    return Object.freeze({ left, right, length, ...unit });
  }));
}

function normaliseBoundaryFaces(cellCount, boundaries) {
  assert(Array.isArray(boundaries), 'boundaryFaces must be an array');
  return Object.freeze(boundaries.map((face, index) => {
    const cell = Number(face.cell);
    const length = Number(face.length);
    const type = String(face.type || 'wall');
    assert(Number.isInteger(cell) && cell >= 0 && cell < cellCount, `boundary ${index} cell is invalid`);
    assertFinite(length, `boundary ${index} length`);
    assert(length > 0, `boundary ${index} length must be positive`);
    assert(type === 'wall' || type === 'state', `boundary ${index} type is invalid`);
    const unit = normal(face.nx, face.ny, `boundary ${index} normal`);
    return Object.freeze({ id: face.id ?? `boundary-${index}`, cell, length, type, state: face.state, ...unit });
  }));
}

function stateArrays(state, cellCount, options) {
  const h = vector(state?.h, cellCount, 'state.h');
  const hu = vector(state?.hu, cellCount, 'state.hu');
  const hv = vector(state?.hv, cellCount, 'state.hv');
  for (let cell = 0; cell < cellCount; cell += 1) {
    const q = normaliseConserved({ h: h[cell], hu: hu[cell], hv: hv[cell] }, options);
    h[cell] = q.h;
    hu[cell] = q.hu;
    hv[cell] = q.hv;
  }
  return Object.freeze({ h, hu, hv });
}

function boundaryGhost(face, interior, time, context, options) {
  if (face.type === 'wall') return reflectiveGhostState(interior, face.nx, face.ny, options);
  const specification = typeof face.state === 'function'
    ? face.state(time, { ...context, boundary: face, interior })
    : face.state;
  return normaliseConserved(specification, options);
}

export function accumulateFluxResidual({
  cellCount,
  faces,
  boundaryFaces = [],
  state,
  time = 0,
  context = {},
  gravity = 9.80665,
  minimumDepth = 1e-8,
}) {
  assert(Number.isInteger(cellCount) && cellCount > 0, 'cellCount must be a positive integer');
  assertFinite(Number(time), 'time');
  const options = { gravity, minimumDepth };
  const cells = stateArrays(state, cellCount, options);
  const internal = normaliseFaces(cellCount, faces);
  const boundaries = normaliseBoundaryFaces(cellCount, boundaryFaces);
  const mass = new Float64Array(cellCount);
  const momentumX = new Float64Array(cellCount);
  const momentumY = new Float64Array(cellCount);
  const internalFluxes = [];
  const boundaryFluxes = [];

  for (const face of internal) {
    const flux = rusanovFlux(
      { h: cells.h[face.left], hu: cells.hu[face.left], hv: cells.hv[face.left] },
      { h: cells.h[face.right], hu: cells.hu[face.right], hv: cells.hv[face.right] },
      face.nx,
      face.ny,
      options,
    );
    const scale = face.length;
    mass[face.left] += scale * flux.mass;
    momentumX[face.left] += scale * flux.momentumX;
    momentumY[face.left] += scale * flux.momentumY;
    mass[face.right] -= scale * flux.mass;
    momentumX[face.right] -= scale * flux.momentumX;
    momentumY[face.right] -= scale * flux.momentumY;
    internalFluxes.push(Object.freeze({ ...face, ...flux }));
  }

  for (const face of boundaries) {
    const interior = { h: cells.h[face.cell], hu: cells.hu[face.cell], hv: cells.hv[face.cell] };
    const ghost = boundaryGhost(face, interior, Number(time), context, options);
    const flux = rusanovFlux(interior, ghost, face.nx, face.ny, options);
    const scale = face.length;
    mass[face.cell] += scale * flux.mass;
    momentumX[face.cell] += scale * flux.momentumX;
    momentumY[face.cell] += scale * flux.momentumY;
    boundaryFluxes.push(Object.freeze({ ...face, ghost, ...flux }));
  }

  return Object.freeze({
    version: STAGE15_SWE_FLUX_VERSION,
    state: cells,
    residual: Object.freeze({ mass, momentumX, momentumY }),
    internalFluxes: Object.freeze(internalFluxes),
    boundaryFluxes: Object.freeze(boundaryFluxes),
  });
}

export function estimateCflDt({
  cellCount,
  faces,
  boundaryFaces = [],
  state,
  areas,
  cfl = 0.45,
  gravity = 9.80665,
  minimumDepth = 1e-8,
}) {
  const cellAreas = vector(areas, cellCount, 'areas');
  const factor = Number(cfl);
  assertFinite(factor, 'cfl');
  assert(factor > 0 && factor <= 1, 'cfl must be in (0, 1]');
  for (let cell = 0; cell < cellCount; cell += 1) assert(cellAreas[cell] > 0, `areas[${cell}] must be positive`);
  const cells = stateArrays(state, cellCount, { gravity, minimumDepth });
  const denominator = new Float64Array(cellCount);
  for (const face of normaliseFaces(cellCount, faces)) {
    const leftWave = physicalNormalFlux(
      { h: cells.h[face.left], hu: cells.hu[face.left], hv: cells.hv[face.left] },
      face.nx, face.ny, { gravity, minimumDepth },
    ).waveSpeed;
    const rightWave = physicalNormalFlux(
      { h: cells.h[face.right], hu: cells.hu[face.right], hv: cells.hv[face.right] },
      face.nx, face.ny, { gravity, minimumDepth },
    ).waveSpeed;
    const speed = Math.max(leftWave, rightWave);
    denominator[face.left] += face.length * speed;
    denominator[face.right] += face.length * speed;
  }
  for (const face of normaliseBoundaryFaces(cellCount, boundaryFaces)) {
    const speed = physicalNormalFlux(
      { h: cells.h[face.cell], hu: cells.hu[face.cell], hv: cells.hv[face.cell] },
      face.nx, face.ny, { gravity, minimumDepth },
    ).waveSpeed;
    denominator[face.cell] += face.length * speed;
  }
  let dt = Infinity;
  for (let cell = 0; cell < cellCount; cell += 1) {
    if (denominator[cell] > 0) dt = Math.min(dt, factor * cellAreas[cell] / denominator[cell]);
  }
  return dt;
}

export function advanceEuler({ state, areas, dt, ...options }) {
  const cellCount = Number(options.cellCount);
  const timeStep = Number(dt);
  assertFinite(timeStep, 'dt');
  assert(timeStep > 0, 'dt must be positive');
  const cellAreas = vector(areas, cellCount, 'areas');
  const result = accumulateFluxResidual({ state, ...options, cellCount });
  const next = {
    h: Float64Array.from(result.state.h),
    hu: Float64Array.from(result.state.hu),
    hv: Float64Array.from(result.state.hv),
  };
  for (let cell = 0; cell < cellCount; cell += 1) {
    assert(cellAreas[cell] > 0, `areas[${cell}] must be positive`);
    const scale = timeStep / cellAreas[cell];
    next.h[cell] -= scale * result.residual.mass[cell];
    next.hu[cell] -= scale * result.residual.momentumX[cell];
    next.hv[cell] -= scale * result.residual.momentumY[cell];
  }
  return Object.freeze({ nextState: Object.freeze(next), fluxEvaluation: result, dt: timeStep });
}

export function sum(values) {
  let total = 0;
  for (const value of values) total += Number(value);
  return total;
}
