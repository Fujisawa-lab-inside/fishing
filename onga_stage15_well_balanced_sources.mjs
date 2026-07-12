import {
  normaliseConserved,
  reflectiveGhostState,
  rusanovFlux,
} from './onga_stage15_shallow_water_flux_core.mjs';

export const STAGE15_WELL_BALANCED_VERSION = 'stage15-hydrostatic-reconstruction-v1';

function assert(condition, message) {
  if (!condition) throw new Error(`[stage15-well-balanced] ${message}`);
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

function unitNormal(nx, ny, label = 'normal') {
  const x = Number(nx);
  const y = Number(ny);
  assertFinite(x, `${label}.x`);
  assertFinite(y, `${label}.y`);
  const magnitude = Math.hypot(x, y);
  assert(magnitude > 0, `${label} has zero length`);
  return Object.freeze({ nx: x / magnitude, ny: y / magnitude });
}

function rescaleMomentum(state, reconstructedDepth, minimumDepth) {
  const q = normaliseConserved(state, { minimumDepth });
  if (q.h <= minimumDepth || reconstructedDepth <= minimumDepth) {
    return Object.freeze({ h: Math.max(0, reconstructedDepth), hu: 0, hv: 0 });
  }
  const ratio = reconstructedDepth / q.h;
  return Object.freeze({ h: reconstructedDepth, hu: q.hu * ratio, hv: q.hv * ratio });
}

export function hydrostaticReconstruction(leftState, rightState, leftBed, rightBed, options = {}) {
  const minimumDepth = Number(options.minimumDepth ?? 1e-8);
  assertFinite(minimumDepth, 'minimumDepth');
  assert(minimumDepth >= 0, 'minimumDepth must be nonnegative');
  const left = normaliseConserved(leftState, { minimumDepth });
  const right = normaliseConserved(rightState, { minimumDepth });
  const zLeft = Number(leftBed);
  const zRight = Number(rightBed);
  assertFinite(zLeft, 'leftBed');
  assertFinite(zRight, 'rightBed');
  const etaLeft = left.h + zLeft;
  const etaRight = right.h + zRight;
  const interfaceBed = Math.max(zLeft, zRight);
  const leftDepth = Math.max(0, etaLeft - interfaceBed);
  const rightDepth = Math.max(0, etaRight - interfaceBed);
  return Object.freeze({
    left: rescaleMomentum(left, leftDepth, minimumDepth),
    right: rescaleMomentum(right, rightDepth, minimumDepth),
    originalLeft: left,
    originalRight: right,
    leftBed: zLeft,
    rightBed: zRight,
    interfaceBed,
    etaLeft,
    etaRight,
  });
}

export function hydrostaticFaceFlux(leftState, rightState, leftBed, rightBed, nx, ny, options = {}) {
  const gravity = Number(options.gravity ?? 9.80665);
  assertFinite(gravity, 'gravity');
  assert(gravity > 0, 'gravity must be positive');
  const unit = unitNormal(nx, ny);
  const reconstruction = hydrostaticReconstruction(leftState, rightState, leftBed, rightBed, options);
  const flux = rusanovFlux(reconstruction.left, reconstruction.right, unit.nx, unit.ny, options);
  const leftPressureCorrection = 0.5 * gravity
    * (reconstruction.originalLeft.h ** 2 - reconstruction.left.h ** 2);
  const rightPressureCorrection = 0.5 * gravity
    * (reconstruction.originalRight.h ** 2 - reconstruction.right.h ** 2);
  return Object.freeze({
    mass: flux.mass,
    signalSpeed: flux.signalSpeed,
    leftMomentumX: flux.momentumX + leftPressureCorrection * unit.nx,
    leftMomentumY: flux.momentumY + leftPressureCorrection * unit.ny,
    rightMomentumX: flux.momentumX + rightPressureCorrection * unit.nx,
    rightMomentumY: flux.momentumY + rightPressureCorrection * unit.ny,
    leftPressureCorrection,
    rightPressureCorrection,
    reconstruction,
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
    const normal = unitNormal(face.nx, face.ny, `face ${index} normal`);
    return Object.freeze({ left, right, length, ...normal });
  }));
}

function normaliseBoundaryFaces(cellCount, faces) {
  assert(Array.isArray(faces), 'boundaryFaces must be an array');
  return Object.freeze(faces.map((face, index) => {
    const cell = Number(face.cell);
    const length = Number(face.length);
    const type = String(face.type || 'wall');
    assert(Number.isInteger(cell) && cell >= 0 && cell < cellCount, `boundary ${index} cell is invalid`);
    assertFinite(length, `boundary ${index} length`);
    assert(length > 0, `boundary ${index} length must be positive`);
    assert(type === 'wall' || type === 'state', `boundary ${index} type is invalid`);
    const normal = unitNormal(face.nx, face.ny, `boundary ${index} normal`);
    return Object.freeze({ id: face.id ?? `boundary-${index}`, cell, length, type, state: face.state, bed: face.bed, ...normal });
  }));
}

function stateArrays(state, cellCount, minimumDepth) {
  const h = vector(state?.h, cellCount, 'state.h');
  const hu = vector(state?.hu, cellCount, 'state.hu');
  const hv = vector(state?.hv, cellCount, 'state.hv');
  for (let cell = 0; cell < cellCount; cell += 1) {
    const q = normaliseConserved({ h: h[cell], hu: hu[cell], hv: hv[cell] }, { minimumDepth });
    h[cell] = q.h;
    hu[cell] = q.hu;
    hv[cell] = q.hv;
  }
  return Object.freeze({ h, hu, hv });
}

function boundaryGhost(face, interior, interiorBed, time, context, options) {
  if (face.type === 'wall') {
    return Object.freeze({
      state: reflectiveGhostState(interior, face.nx, face.ny, options),
      bed: interiorBed,
    });
  }
  const specification = typeof face.state === 'function'
    ? face.state(time, { ...context, boundary: face, interior, interiorBed })
    : face.state;
  const bedSpecification = typeof face.bed === 'function'
    ? face.bed(time, { ...context, boundary: face, interior, interiorBed })
    : face.bed;
  const ghostBed = bedSpecification === undefined ? interiorBed : Number(bedSpecification);
  assertFinite(ghostBed, `boundary ${face.id} bed`);
  return Object.freeze({ state: normaliseConserved(specification, options), bed: ghostBed });
}

export function accumulateWellBalancedResidual({
  cellCount,
  faces,
  boundaryFaces = [],
  state,
  bedElevation,
  time = 0,
  context = {},
  gravity = 9.80665,
  minimumDepth = 1e-8,
}) {
  assert(Number.isInteger(cellCount) && cellCount > 0, 'cellCount must be a positive integer');
  const timeValue = Number(time);
  assertFinite(timeValue, 'time');
  const cells = stateArrays(state, cellCount, minimumDepth);
  const bed = vector(bedElevation, cellCount, 'bedElevation');
  const internalFaces = normaliseFaces(cellCount, faces);
  const boundaries = normaliseBoundaryFaces(cellCount, boundaryFaces);
  const mass = new Float64Array(cellCount);
  const momentumX = new Float64Array(cellCount);
  const momentumY = new Float64Array(cellCount);
  const internalFluxes = [];
  const boundaryFluxes = [];
  const options = { gravity, minimumDepth };

  for (const face of internalFaces) {
    const flux = hydrostaticFaceFlux(
      { h: cells.h[face.left], hu: cells.hu[face.left], hv: cells.hv[face.left] },
      { h: cells.h[face.right], hu: cells.hu[face.right], hv: cells.hv[face.right] },
      bed[face.left],
      bed[face.right],
      face.nx,
      face.ny,
      options,
    );
    mass[face.left] += face.length * flux.mass;
    momentumX[face.left] += face.length * flux.leftMomentumX;
    momentumY[face.left] += face.length * flux.leftMomentumY;
    mass[face.right] -= face.length * flux.mass;
    momentumX[face.right] -= face.length * flux.rightMomentumX;
    momentumY[face.right] -= face.length * flux.rightMomentumY;
    internalFluxes.push(Object.freeze({ ...face, ...flux }));
  }

  for (const face of boundaries) {
    const interior = { h: cells.h[face.cell], hu: cells.hu[face.cell], hv: cells.hv[face.cell] };
    const ghost = boundaryGhost(face, interior, bed[face.cell], timeValue, context, options);
    const flux = hydrostaticFaceFlux(
      interior,
      ghost.state,
      bed[face.cell],
      ghost.bed,
      face.nx,
      face.ny,
      options,
    );
    mass[face.cell] += face.length * flux.mass;
    momentumX[face.cell] += face.length * flux.leftMomentumX;
    momentumY[face.cell] += face.length * flux.leftMomentumY;
    boundaryFluxes.push(Object.freeze({ ...face, ghost, ...flux }));
  }

  return Object.freeze({
    version: STAGE15_WELL_BALANCED_VERSION,
    state: cells,
    bedElevation: bed,
    residual: Object.freeze({ mass, momentumX, momentumY }),
    internalFluxes: Object.freeze(internalFluxes),
    boundaryFluxes: Object.freeze(boundaryFluxes),
  });
}

export function applyManningFriction(state, manningN, dt, options = {}) {
  const gravity = Number(options.gravity ?? 9.80665);
  const minimumDepth = Number(options.minimumDepth ?? 1e-8);
  const timeStep = Number(dt);
  assertFinite(gravity, 'gravity');
  assertFinite(minimumDepth, 'minimumDepth');
  assertFinite(timeStep, 'dt');
  assert(gravity > 0, 'gravity must be positive');
  assert(minimumDepth >= 0, 'minimumDepth must be nonnegative');
  assert(timeStep >= 0, 'dt must be nonnegative');
  const length = state?.h?.length;
  assert(Number.isInteger(length), 'state vectors are required');
  const h = vector(state.h, length, 'state.h');
  const hu = vector(state.hu, length, 'state.hu');
  const hv = vector(state.hv, length, 'state.hv');
  const roughness = typeof manningN === 'number'
    ? Float64Array.from({ length }, () => manningN)
    : vector(manningN, length, 'manningN');
  for (let cell = 0; cell < length; cell += 1) {
    assert(roughness[cell] >= 0, `manningN[${cell}] must be nonnegative`);
    if (h[cell] <= minimumDepth) {
      h[cell] = Math.max(0, h[cell]);
      hu[cell] = 0;
      hv[cell] = 0;
      continue;
    }
    const speed = Math.hypot(hu[cell], hv[cell]) / h[cell];
    const damping = 1 + timeStep * gravity * roughness[cell] ** 2 * speed / h[cell] ** (4 / 3);
    hu[cell] /= damping;
    hv[cell] /= damping;
  }
  return Object.freeze({ h, hu, hv });
}

export function totalVolume(state, areas) {
  const length = state?.h?.length;
  const h = vector(state?.h, length, 'state.h');
  const cellAreas = vector(areas, length, 'areas');
  let volume = 0;
  for (let cell = 0; cell < length; cell += 1) {
    assert(h[cell] >= 0, `state.h[${cell}] must be nonnegative`);
    assert(cellAreas[cell] > 0, `areas[${cell}] must be positive`);
    volume += h[cell] * cellAreas[cell];
  }
  return volume;
}
