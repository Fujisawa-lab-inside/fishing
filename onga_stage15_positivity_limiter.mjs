import { accumulateFluxResidual } from './onga_stage15_shallow_water_flux_core.mjs';

export const STAGE15_POSITIVITY_VERSION = 'stage15-draining-time-ssprk2-v1';

function assert(condition, message) {
  if (!condition) throw new Error(`[stage15-positivity] ${message}`);
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

function normaliseState(state, cellCount, minimumDepth) {
  const h = vector(state?.h, cellCount, 'state.h');
  const hu = vector(state?.hu, cellCount, 'state.hu');
  const hv = vector(state?.hv, cellCount, 'state.hv');
  for (let cell = 0; cell < cellCount; cell += 1) {
    assert(h[cell] >= 0, `state.h[${cell}] must be nonnegative`);
    if (h[cell] <= minimumDepth) {
      h[cell] = Math.max(0, h[cell]);
      hu[cell] = 0;
      hv[cell] = 0;
    }
  }
  return Object.freeze({ h, hu, hv });
}

function normaliseSources(sources, cellCount) {
  if (sources === null || sources === undefined) {
    return Object.freeze({
      mass: new Float64Array(cellCount),
      momentumX: new Float64Array(cellCount),
      momentumY: new Float64Array(cellCount),
    });
  }
  return Object.freeze({
    mass: vector(sources.mass, cellCount, 'sources.mass', 0),
    momentumX: vector(sources.momentumX, cellCount, 'sources.momentumX', 0),
    momentumY: vector(sources.momentumY, cellCount, 'sources.momentumY', 0),
  });
}

export function computeDrainLimiter({
  cellCount,
  state,
  areas,
  dt,
  internalFluxes,
  boundaryFluxes = [],
  sources = null,
  minimumDepth = 1e-10,
}) {
  assert(Number.isInteger(cellCount) && cellCount > 0, 'cellCount must be a positive integer');
  const timeStep = Number(dt);
  assertFinite(timeStep, 'dt');
  assert(timeStep > 0, 'dt must be positive');
  const depthFloor = Number(minimumDepth);
  assertFinite(depthFloor, 'minimumDepth');
  assert(depthFloor >= 0, 'minimumDepth must be nonnegative');
  const cells = normaliseState(state, cellCount, depthFloor);
  const cellAreas = vector(areas, cellCount, 'areas');
  const source = normaliseSources(sources, cellCount);
  const outgoingRate = new Float64Array(cellCount);
  const availableVolume = new Float64Array(cellCount);

  for (let cell = 0; cell < cellCount; cell += 1) {
    assert(cellAreas[cell] > 0, `areas[${cell}] must be positive`);
    availableVolume[cell] = cells.h[cell] * cellAreas[cell]
      + timeStep * Math.max(source.mass[cell], 0);
    outgoingRate[cell] += Math.max(-source.mass[cell], 0);
  }

  assert(Array.isArray(internalFluxes), 'internalFluxes must be an array');
  for (let index = 0; index < internalFluxes.length; index += 1) {
    const face = internalFluxes[index];
    const left = Number(face.left);
    const right = Number(face.right);
    const length = Number(face.length);
    const massFlux = Number(face.mass);
    assert(Number.isInteger(left) && left >= 0 && left < cellCount, `internal face ${index} left is invalid`);
    assert(Number.isInteger(right) && right >= 0 && right < cellCount, `internal face ${index} right is invalid`);
    assertFinite(length, `internal face ${index} length`);
    assertFinite(massFlux, `internal face ${index} mass flux`);
    assert(length > 0, `internal face ${index} length must be positive`);
    if (massFlux > 0) outgoingRate[left] += length * massFlux;
    else if (massFlux < 0) outgoingRate[right] += length * -massFlux;
  }

  assert(Array.isArray(boundaryFluxes), 'boundaryFluxes must be an array');
  for (let index = 0; index < boundaryFluxes.length; index += 1) {
    const face = boundaryFluxes[index];
    const cell = Number(face.cell);
    const length = Number(face.length);
    const massFlux = Number(face.mass);
    assert(Number.isInteger(cell) && cell >= 0 && cell < cellCount, `boundary face ${index} cell is invalid`);
    assertFinite(length, `boundary face ${index} length`);
    assertFinite(massFlux, `boundary face ${index} mass flux`);
    assert(length > 0, `boundary face ${index} length must be positive`);
    if (massFlux > 0) outgoingRate[cell] += length * massFlux;
  }

  const alpha = new Float64Array(cellCount);
  for (let cell = 0; cell < cellCount; cell += 1) {
    const requestedVolume = timeStep * outgoingRate[cell];
    alpha[cell] = requestedVolume > 0
      ? Math.min(1, Math.max(0, availableVolume[cell] / requestedVolume))
      : 1;
  }

  return Object.freeze({
    alpha,
    outgoingRate,
    availableVolume,
    state: cells,
    areas: cellAreas,
    sources: source,
  });
}

function faceScale(face, alpha) {
  if (face.mass > 0) return alpha[face.left];
  if (face.mass < 0) return alpha[face.right];
  return 1;
}

function boundaryScale(face, alpha) {
  return face.mass > 0 ? alpha[face.cell] : 1;
}

export function buildLimitedResidual({
  cellCount,
  state,
  areas,
  dt,
  fluxEvaluation,
  sources = null,
  minimumDepth = 1e-10,
}) {
  const limiter = computeDrainLimiter({
    cellCount,
    state,
    areas,
    dt,
    internalFluxes: fluxEvaluation.internalFluxes,
    boundaryFluxes: fluxEvaluation.boundaryFluxes,
    sources,
    minimumDepth,
  });
  const mass = new Float64Array(cellCount);
  const momentumX = new Float64Array(cellCount);
  const momentumY = new Float64Array(cellCount);
  const internalFluxes = [];
  const boundaryFluxes = [];

  for (const face of fluxEvaluation.internalFluxes) {
    const scale = faceScale(face, limiter.alpha);
    const integratedMass = face.length * face.mass * scale;
    const integratedMomentumX = face.length * face.momentumX * scale;
    const integratedMomentumY = face.length * face.momentumY * scale;
    mass[face.left] += integratedMass;
    momentumX[face.left] += integratedMomentumX;
    momentumY[face.left] += integratedMomentumY;
    mass[face.right] -= integratedMass;
    momentumX[face.right] -= integratedMomentumX;
    momentumY[face.right] -= integratedMomentumY;
    internalFluxes.push(Object.freeze({
      ...face,
      limiterScale: scale,
      integratedMass,
      integratedMomentumX,
      integratedMomentumY,
    }));
  }

  for (const face of fluxEvaluation.boundaryFluxes) {
    const scale = boundaryScale(face, limiter.alpha);
    const integratedMass = face.length * face.mass * scale;
    const integratedMomentumX = face.length * face.momentumX * scale;
    const integratedMomentumY = face.length * face.momentumY * scale;
    mass[face.cell] += integratedMass;
    momentumX[face.cell] += integratedMomentumX;
    momentumY[face.cell] += integratedMomentumY;
    boundaryFluxes.push(Object.freeze({
      ...face,
      limiterScale: scale,
      integratedMass,
      integratedMomentumX,
      integratedMomentumY,
    }));
  }

  const adjustedSources = {
    mass: new Float64Array(cellCount),
    momentumX: new Float64Array(cellCount),
    momentumY: new Float64Array(cellCount),
  };
  for (let cell = 0; cell < cellCount; cell += 1) {
    const scale = limiter.sources.mass[cell] < 0 ? limiter.alpha[cell] : 1;
    adjustedSources.mass[cell] = limiter.sources.mass[cell] * scale;
    adjustedSources.momentumX[cell] = limiter.sources.momentumX[cell] * scale;
    adjustedSources.momentumY[cell] = limiter.sources.momentumY[cell] * scale;
  }

  return Object.freeze({
    limiter,
    residual: Object.freeze({ mass, momentumX, momentumY }),
    adjustedSources: Object.freeze(adjustedSources),
    internalFluxes: Object.freeze(internalFluxes),
    boundaryFluxes: Object.freeze(boundaryFluxes),
  });
}

export function advancePositivityEuler({
  cellCount,
  faces,
  boundaryFaces = [],
  state,
  areas,
  dt,
  sources = null,
  time = 0,
  context = {},
  gravity = 9.80665,
  minimumDepth = 1e-10,
}) {
  const timeStep = Number(dt);
  assertFinite(timeStep, 'dt');
  assert(timeStep > 0, 'dt must be positive');
  const cells = normaliseState(state, cellCount, minimumDepth);
  const fluxEvaluation = accumulateFluxResidual({
    cellCount,
    faces,
    boundaryFaces,
    state: cells,
    time,
    context,
    gravity,
    minimumDepth,
  });
  const limited = buildLimitedResidual({
    cellCount,
    state: cells,
    areas,
    dt: timeStep,
    fluxEvaluation,
    sources,
    minimumDepth,
  });
  const next = {
    h: new Float64Array(cellCount),
    hu: new Float64Array(cellCount),
    hv: new Float64Array(cellCount),
  };
  let minimumRawDepth = Infinity;
  let roundoffMassCorrection = 0;
  for (let cell = 0; cell < cellCount; cell += 1) {
    const area = limited.limiter.areas[cell];
    const nextVolume = cells.h[cell] * area
      - timeStep * limited.residual.mass[cell]
      + timeStep * limited.adjustedSources.mass[cell];
    const rawDepth = nextVolume / area;
    minimumRawDepth = Math.min(minimumRawDepth, rawDepth);
    const tolerance = 1e-12 * Math.max(1, cells.h[cell]);
    assert(rawDepth >= -tolerance, `positivity limiter failed at cell ${cell}: ${rawDepth}`);
    next.h[cell] = Math.max(0, rawDepth);
    next.hu[cell] = cells.hu[cell]
      - timeStep * limited.residual.momentumX[cell] / area
      + timeStep * limited.adjustedSources.momentumX[cell] / area;
    next.hv[cell] = cells.hv[cell]
      - timeStep * limited.residual.momentumY[cell] / area
      + timeStep * limited.adjustedSources.momentumY[cell] / area;
    if (rawDepth < 0) roundoffMassCorrection += -rawDepth * area;
    if (next.h[cell] <= minimumDepth) {
      next.h[cell] = 0;
      next.hu[cell] = 0;
      next.hv[cell] = 0;
    }
  }

  return Object.freeze({
    version: STAGE15_POSITIVITY_VERSION,
    method: 'positivity-euler',
    time: Number(time),
    nextTime: Number(time) + timeStep,
    dt: timeStep,
    nextState: Object.freeze(next),
    fluxEvaluation,
    limited,
    diagnostics: Object.freeze({ minimumRawDepth, roundoffMassCorrection }),
  });
}

export function advanceSspRk2(options) {
  const first = advancePositivityEuler(options);
  const second = advancePositivityEuler({
    ...options,
    state: first.nextState,
    time: first.nextTime,
  });
  const cellCount = Number(options.cellCount);
  const original = normaliseState(options.state, cellCount, options.minimumDepth ?? 1e-10);
  const next = {
    h: new Float64Array(cellCount),
    hu: new Float64Array(cellCount),
    hv: new Float64Array(cellCount),
  };
  for (let cell = 0; cell < cellCount; cell += 1) {
    next.h[cell] = 0.5 * (original.h[cell] + second.nextState.h[cell]);
    next.hu[cell] = 0.5 * (original.hu[cell] + second.nextState.hu[cell]);
    next.hv[cell] = 0.5 * (original.hv[cell] + second.nextState.hv[cell]);
    assert(next.h[cell] >= 0, `SSP-RK2 produced negative depth at cell ${cell}`);
  }
  return Object.freeze({
    version: STAGE15_POSITIVITY_VERSION,
    method: 'ssprk2',
    time: Number(options.time ?? 0),
    nextTime: Number(options.time ?? 0) + Number(options.dt),
    dt: Number(options.dt),
    nextState: Object.freeze(next),
    stages: Object.freeze([first, second]),
  });
}

export function totalVolume(state, areas) {
  const length = state?.h?.length;
  const h = vector(state?.h, length, 'state.h');
  const cellAreas = vector(areas, length, 'areas');
  let total = 0;
  for (let cell = 0; cell < length; cell += 1) {
    assert(h[cell] >= 0, `state.h[${cell}] must be nonnegative`);
    assert(cellAreas[cell] > 0, `areas[${cell}] must be positive`);
    total += h[cell] * cellAreas[cell];
  }
  return total;
}
